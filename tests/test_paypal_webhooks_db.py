"""
ApexMarket Test Suite: PayPal Webhooks (PostgreSQL + mocked PayPal)
Asserts events are rejected unless PayPal verifies the signature, capture events credit a
top-up exactly once from PayPal's fetched order state, payout events reconcile the batch
and record PayPal's fee, and replayed events change nothing. Skipped unless
TEST_DATABASE_URL is set.
"""

import json
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text

from app.api import routes_settlement
from app.config import Settings
from app.database import get_db
from app.services.paypal_client import clear_token_cache
from app.services.sandbox_payout_service import prepare_batch
from tests.test_topup_service_db import completed_order

pytestmark = pytest.mark.asyncio

SIGNATURE_HEADERS = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api-m.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "paypal-transmission-id": "transmission-1",
    "paypal-transmission-sig": "signature",
    "paypal-transmission-time": "2026-10-25T00:00:00Z",
}


def webhook_settings(webhook_id: str = "WH-1") -> Settings:
    return Settings(
        PAYPAL_MODE="sandbox",
        PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com",
        PAYPAL_CLIENT_ID="test",
        PAYPAL_CLIENT_SECRET="test",
        PAYPAL_WEBHOOK_ID=webhook_id,
    )


class FakeWebhookPayPal:
    def __init__(self):
        self.verification_status = "SUCCESS"
        self.orders: dict[str, tuple[str, str]] = {}  # order_id -> (topup_id, value)
        self.payout_status = "SUCCESS"
        self.payout_items: list[str] = []
        self.requests: list[tuple[str, str]] = []
        self.verify_bodies: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 32400})
        self.requests.append((request.method, path))
        if path == "/v1/notifications/verify-webhook-signature":
            self.verify_bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"verification_status": self.verification_status})
        if path.startswith("/v2/checkout/orders/"):
            order_id = path.rsplit("/", 1)[1]
            topup_id, value = self.orders[order_id]
            return httpx.Response(200, json=completed_order(order_id, topup_id, value))
        if path.startswith("/v1/payments/payouts/"):
            return httpx.Response(200, json={
                "batch_header": {"payout_batch_id": path.rsplit("/", 1)[1], "fees": {"currency": "USD", "value": "0.25"}},
                "total_pages": 1,
                "items": [
                    {"payout_item_id": f"ITEM-{i}", "payout_item": {"sender_item_id": item}, "transaction_status": self.payout_status}
                    for i, item in enumerate(self.payout_items)
                ],
            })
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})


@pytest.fixture
def fake(monkeypatch):
    clear_token_cache()
    fake = FakeWebhookPayPal()
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        routes_settlement.httpx, "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(fake.handler)),
    )
    monkeypatch.setattr(routes_settlement, "get_settings", webhook_settings)
    yield fake
    clear_token_cache()


@pytest_asyncio.fixture
async def api(session_factory):
    app = FastAPI()
    app.include_router(routes_settlement.router, prefix="/api/v1")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def post_event(api, event: dict, headers: dict = SIGNATURE_HEADERS) -> httpx.Response:
    return await api.post("/api/v1/webhooks/paypal", json=event, headers=headers)


async def pending_topup(db, make_client, fake, order_id: str = "ORDER-9") -> uuid.UUID:
    client_id = await make_client(available_balance_micros=0)
    topup_id = uuid.uuid4()
    await db.execute(
        text("INSERT INTO paypal_topups (topup_id, client_id, paypal_order_id, amount_micros) VALUES (:t, :c, :o, 20000000)"),
        {"t": topup_id, "c": client_id, "o": order_id},
    )
    await db.commit()
    fake.orders[order_id] = (str(topup_id), "20.00")
    return client_id


def capture_completed_event(order_id: str = "ORDER-9") -> dict:
    return {
        "id": f"WH-EVENT-{uuid.uuid4().hex[:6]}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAPTURE-1", "status": "COMPLETED", "supplementary_data": {"related_ids": {"order_id": order_id}}},
    }


async def available(db, client_id) -> int:
    return (await db.execute(
        text("SELECT available_balance_micros FROM clients WHERE client_id = :id"), {"id": client_id}
    )).scalar_one()


async def test_event_with_failed_verification_is_rejected(api, fake, db, make_client):
    client_id = await pending_topup(db, make_client, fake)
    fake.verification_status = "FAILURE"

    response = await post_event(api, capture_completed_event())

    assert response.status_code == 400
    assert await available(db, client_id) == 0
    assert ("GET", "/v2/checkout/orders/ORDER-9") not in fake.requests


async def test_event_without_signature_headers_is_rejected_before_calling_paypal(api, fake):
    response = await post_event(api, capture_completed_event(), headers={})

    assert response.status_code == 400
    assert fake.requests == []


async def test_verification_sends_our_webhook_id_and_the_event(api, fake):
    event = {"id": "WH-EVENT-1", "event_type": "CUSTOMER.DISPUTE.CREATED", "resource": {}}
    response = await post_event(api, event)

    assert response.json() == {"event_type": "CUSTOMER.DISPUTE.CREATED", "action": "IGNORED"}
    body = fake.verify_bodies[0]
    assert body["webhook_id"] == "WH-1" and body["webhook_event"] == event
    assert body["transmission_sig"] == "signature"


async def test_capture_completed_credits_once_even_when_replayed(api, fake, db, make_client):
    client_id = await pending_topup(db, make_client, fake)

    first = await post_event(api, capture_completed_event())
    replay = await post_event(api, capture_completed_event())

    assert first.status_code == 200 and first.json()["action"] == "CREDITED"
    assert replay.json()["action"] == "ALREADY_CREDITED"
    assert await available(db, client_id) == 20_000_000
    assert (await db.execute(text("SELECT paypal_vault_id FROM clients WHERE client_id = :id"), {"id": client_id})).scalar_one() == "VAULT-1"


async def test_capture_for_unknown_order_is_ignored(api, fake):
    response = await post_event(api, capture_completed_event("ORDER-UNKNOWN"))
    assert response.status_code == 200
    assert response.json()["action"] == "IGNORED_UNKNOWN_ORDER"


async def test_payout_item_event_reconciles_batch_and_records_fee(api, fake, db, make_node):
    node_id = await make_node()
    await db.execute(text("UPDATE compute_nodes SET withdrawable_micros = 1234567 WHERE node_id = :n"), {"n": node_id})
    await db.commit()
    batch_id = uuid.uuid4()
    await prepare_batch(db, batch_id)
    await db.execute(
        text("UPDATE payout_batches SET paypal_batch_id = 'PAYOUT-1', status = 'SUBMITTED_PENDING' WHERE batch_id = :id"),
        {"id": batch_id},
    )
    await db.commit()
    item_id = (await db.execute(text("SELECT item_id FROM payout_items WHERE batch_id = :id"), {"id": batch_id})).scalar_one()
    fake.payout_items = [str(item_id)]

    event = {"event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", "resource": {"payout_batch_id": "PAYOUT-1", "payout_item": {"sender_item_id": str(item_id)}}}
    for _ in range(2):
        response = await post_event(api, event)
        assert response.status_code == 200 and response.json()["action"] == "RECONCILED"

    batch = (await db.execute(text("SELECT status, total_fee_micros FROM payout_batches WHERE batch_id = :id"), {"id": batch_id})).one()
    assert tuple(batch) == ("COMPLETED", 250_000)
    node = (await db.execute(text("SELECT withdrawable_micros, payout_pending_micros FROM compute_nodes WHERE node_id = :n"), {"n": node_id})).one()
    assert tuple(node) == (4567, 0)


async def test_unconfigured_webhook_id_returns_503(api, fake, monkeypatch):
    monkeypatch.setattr(routes_settlement, "get_settings", lambda: webhook_settings(webhook_id=""))
    response = await post_event(api, capture_completed_event())
    assert response.status_code == 503
