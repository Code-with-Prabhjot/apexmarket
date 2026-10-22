"""Admin boundary and PayPal request contracts; HTTP stays on a mock transport."""
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import Settings, get_settings
from app.services.sandbox_payout_service import payout_payload, require_sandbox, access_token


def test_admin_actions_fail_closed(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADMIN_API_KEY", "")
    with TestClient(app) as client:
        assert client.post("/api/v1/demo/drift", json={"degraded": True}).status_code == 403
        assert client.post("/api/v1/ledger/settle-now", headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 403


def test_chaos_only_targets_opted_in_loopback(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-key")
    monkeypatch.setattr(settings, "DEMO_CHAOS_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MOCK_PROVIDER_URL", "https://example.com")
    with TestClient(app) as client:
        assert client.post("/api/v1/demo/drift", headers={"X-Admin-Key": "wrong"}, json={"degraded": True}).status_code == 403
        assert client.post("/api/v1/demo/drift", headers={"X-Admin-Key": "test-key"}, json={"degraded": True}).status_code == 403


def test_chaos_disabled_in_production(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-key")
    monkeypatch.setattr(settings, "DEMO_CHAOS_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with TestClient(app) as client:
        assert client.post("/api/v1/demo/drift", headers={"X-Admin-Key": "test-key"}, json={"degraded": True}).status_code == 403


def test_sandbox_cannot_send_to_live_paypal():
    for change in [{"PAYPAL_MODE": "live"}, {"PAYPAL_BASE_URL": "https://api-m.paypal.com"}, {"PAYPAL_CLIENT_SECRET": ""}]:
        settings = Settings(PAYPAL_CLIENT_ID="id", PAYPAL_CLIENT_SECRET="secret")
        for key, value in change.items():
            setattr(settings, key, value)
        with pytest.raises(ValueError):
            require_sandbox(settings)


def test_payout_payload_preserves_uuid_and_whole_cent_math():
    batch, item = uuid.uuid4(), uuid.uuid4()
    payload = payout_payload(batch, [{"item_id": item, "receiver": "receiver@example.invalid", "amount_paid_micros": 1230000}])
    assert payload["sender_batch_header"]["sender_batch_id"] == str(batch)
    assert payload["items"][0]["sender_item_id"] == str(item)
    assert payload["items"][0]["amount"] == {"currency": "USD", "value": "1.23"}


@pytest.mark.asyncio
async def test_oauth_uses_client_credentials():
    async def handler(request):
        assert request.url.path == "/v1/oauth2/token"
        assert request.headers["authorization"].startswith("Basic ")
        assert b"grant_type=client_credentials" in request.content
        return httpx.Response(200, json={"access_token": "sandbox-token"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await access_token(client, Settings(PAYPAL_CLIENT_ID="id", PAYPAL_CLIENT_SECRET="secret")) == "sandbox-token"
