"""
ApexMarket Test Suite: Billing API (PostgreSQL + mocked PayPal)
Drives the /api/v1/billing endpoints through FastAPI and checks status codes,
balance changes, and error mapping. Skipped unless TEST_DATABASE_URL is set.
"""

import hashlib
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text

from app.api import routes_billing
from app.config import Settings
from app.database import get_db
from tests.test_topup_service_db import FakePayPal, sandbox

pytestmark = pytest.mark.asyncio

API_KEY = {"X-API-Key": "billing-api-test-key"}


@pytest.fixture
def fake_paypal(monkeypatch):
    """Routes PayPal traffic from the billing routes to a FakePayPal instance."""
    fake = FakePayPal()
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        routes_billing.httpx, "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(fake.handler)),
    )
    monkeypatch.setattr(routes_billing, "get_settings", sandbox)
    return fake


@pytest_asyncio.fixture
async def api(session_factory):
    # Register the test client up front so these tests don't rely on auto-provisioning.
    async with session_factory() as session:
        await session.execute(
            text("""
                INSERT INTO clients (organization_name, api_key_hash, available_balance_micros)
                VALUES ('Billing API Test', :key_hash, 0)
            """),
            {"key_hash": hashlib.sha256(API_KEY["X-API-Key"].encode("utf-8")).hexdigest()},
        )
        await session.commit()

    app = FastAPI()
    app.include_router(routes_billing.router, prefix="/api/v1")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def balance(api) -> int:
    response = await api.get("/api/v1/billing/balance", headers=API_KEY)
    assert response.status_code == 200, response.text
    return response.json()["available_balance_micros"]


async def test_topup_approve_and_capture_flow_credits_balance(api, fake_paypal):
    before = await balance(api)

    created = await api.post("/api/v1/billing/topups", json={"amount_micros": 20_000_000}, headers=API_KEY)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "CREATED" and body["approve_url"]

    captured = await api.post(f"/api/v1/billing/topups/{body['topup_id']}/capture", headers=API_KEY)
    assert captured.status_code == 200, captured.text
    assert captured.json()["status"] == "CAPTURED"

    repeat = await api.post(f"/api/v1/billing/topups/{body['topup_id']}/capture", headers=API_KEY)
    assert repeat.status_code == 200

    assert await balance(api) == before + 20_000_000
    balance_body = (await api.get("/api/v1/billing/balance", headers=API_KEY)).json()
    assert balance_body["available_balance_usd"] == f"{(before + 20_000_000) / 1_000_000:.2f}"


async def test_capture_unknown_topup_returns_404(api, fake_paypal):
    response = await api.post(f"/api/v1/billing/topups/{uuid.uuid4()}/capture", headers=API_KEY)
    assert response.status_code == 404


async def test_topup_below_minimum_returns_400(api, fake_paypal):
    response = await api.post("/api/v1/billing/topups", json={"amount_micros": 1_000_000}, headers=API_KEY)
    assert response.status_code == 400
    assert fake_paypal.calls == []


async def test_auto_topup_needs_idempotency_key_and_saved_account(api, fake_paypal):
    missing_key = await api.post("/api/v1/billing/topups/auto", json={"amount_micros": 20_000_000}, headers=API_KEY)
    assert missing_key.status_code == 422

    no_vault = await api.post(
        "/api/v1/billing/topups/auto",
        json={"amount_micros": 20_000_000},
        headers={**API_KEY, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert no_vault.status_code == 400


async def test_auto_topup_after_first_capture_uses_saved_account(api, fake_paypal):
    created = (await api.post("/api/v1/billing/topups", json={"amount_micros": 20_000_000}, headers=API_KEY)).json()
    await api.post(f"/api/v1/billing/topups/{created['topup_id']}/capture", headers=API_KEY)
    before = await balance(api)

    key = str(uuid.uuid4())
    for _ in range(2):
        response = await api.post(
            "/api/v1/billing/topups/auto",
            json={"amount_micros": 25_000_000},
            headers={**API_KEY, "Idempotency-Key": key},
        )
        assert response.status_code == 200, response.text

    assert await balance(api) == before + 25_000_000


async def test_paypal_timeout_returns_502_with_retry_guidance(api, fake_paypal):
    def timeout(request, order_id):
        raise httpx.ReadTimeout("lost", request=request)

    created = (await api.post("/api/v1/billing/topups", json={"amount_micros": 20_000_000}, headers=API_KEY)).json()
    fake_paypal.capture_override = timeout
    response = await api.post(f"/api/v1/billing/topups/{created['topup_id']}/capture", headers=API_KEY)

    assert response.status_code == 502
    assert "Retry the same request" in response.json()["detail"]


async def test_paypal_not_configured_returns_409(api, fake_paypal, monkeypatch):
    monkeypatch.setattr(routes_billing, "get_settings", lambda: Settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET=""))
    response = await api.post("/api/v1/billing/topups", json={"amount_micros": 20_000_000}, headers=API_KEY)
    assert response.status_code == 409
