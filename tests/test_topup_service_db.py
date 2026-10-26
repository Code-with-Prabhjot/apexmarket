"""
ApexMarket Test Suite: Prepaid Top-Ups (PostgreSQL + mocked PayPal)
Asserts top-up orders are recorded before PayPal is called, captures credit the client
exactly once and only for the recorded client and amount, the vault id is saved, and
vaulted auto top-ups are idempotent. Skipped unless TEST_DATABASE_URL is set.
"""

import json
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.config import Settings
from app.services.paypal_client import PayPalClient, clear_token_cache
from app.services.topup_service import (
    TopUpError,
    capture_topup,
    charge_vaulted_topup,
    create_topup_order,
)

pytestmark = pytest.mark.asyncio

TWENTY_DOLLARS = 20_000_000


def sandbox() -> Settings:
    return Settings(
        PAYPAL_MODE="sandbox",
        PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com",
        PAYPAL_CLIENT_ID="test",
        PAYPAL_CLIENT_SECRET="test",
    )


@pytest.fixture(autouse=True)
def fresh_token_cache():
    clear_token_cache()
    yield
    clear_token_cache()


def completed_order(order_id: str, topup_id: str, value: str, capture_status: str = "COMPLETED", vault: bool = True) -> dict:
    order = {
        "id": order_id,
        "status": "COMPLETED" if capture_status == "COMPLETED" else "PAYER_ACTION_REQUIRED",
        "purchase_units": [{
            "reference_id": topup_id,
            "payments": {"captures": [{
                "id": f"CAPTURE-{order_id}",
                "status": capture_status,
                "custom_id": topup_id,
                "amount": {"currency_code": "USD", "value": value},
            }]},
        }],
        "payment_source": {"paypal": {"account_id": "PAYER-1"}},
    }
    if vault:
        order["payment_source"]["paypal"]["attributes"] = {"vault": {"id": "VAULT-1", "status": "VAULTED"}}
    return order


class FakePayPal:
    """Minimal Orders v2 sandbox. capture_override lets a test replace the capture response."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict, str | None]] = []
        self.orders: dict[str, dict] = {}
        self.capture_override = None
        self.vault_capture_status = "COMPLETED"

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 32400})
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, request.url.path, body, request.headers.get("PayPal-Request-Id")))

        if request.method == "POST" and request.url.path == "/v2/checkout/orders":
            unit = body["purchase_units"][0]
            order_id = f"ORDER-{len(self.orders) + 1}"
            self.orders[order_id] = {"topup_id": unit["custom_id"], "value": unit["amount"]["value"]}
            if "vault_id" in body["payment_source"]["paypal"]:
                return httpx.Response(201, json=completed_order(
                    order_id, unit["custom_id"], unit["amount"]["value"], self.vault_capture_status, vault=False))
            return httpx.Response(200, json={
                "id": order_id,
                "status": "PAYER_ACTION_REQUIRED",
                "links": [{"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"}],
            })

        order_id = request.url.path.split("/")[4]
        if request.url.path.endswith("/capture"):
            if self.capture_override is not None:
                return self.capture_override(request, order_id)
            order = self.orders[order_id]
            return httpx.Response(201, json=completed_order(order_id, order["topup_id"], order["value"]))
        order = self.orders[order_id]
        return httpx.Response(200, json=completed_order(order_id, order["topup_id"], order["value"]))


async def client_balance(db, client_id) -> int:
    return (await db.execute(
        text("SELECT available_balance_micros FROM clients WHERE client_id = :id"), {"id": client_id}
    )).scalar_one()


async def topup_row(db, topup_id) -> dict:
    return dict((await db.execute(
        text("SELECT * FROM paypal_topups WHERE topup_id = :id"), {"id": topup_id}
    )).mappings().one())


async def credit_entries(db) -> int:
    return (await db.execute(
        text("SELECT COUNT(*) FROM ledger_entries WHERE idempotency_key LIKE 'topup_credit:%'")
    )).scalar_one()


async def create_approved_topup(db, http, client_id) -> uuid.UUID:
    created = await create_topup_order(db, PayPalClient(sandbox(), http), client_id, TWENTY_DOLLARS, sandbox())
    return created["topup_id"]


# -----------------------------------------------------------------------------
# CREATE ORDER
# -----------------------------------------------------------------------------

async def test_create_order_records_topup_and_requests_vaulting(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        created = await create_topup_order(db, PayPalClient(sandbox(), http), client_id, TWENTY_DOLLARS, sandbox())

    topup_id = created["topup_id"]
    assert created["approve_url"].endswith("token=ORDER-1")
    row = await topup_row(db, topup_id)
    assert (row["status"], row["paypal_order_id"], row["amount_micros"]) == ("CREATED", "ORDER-1", TWENTY_DOLLARS)

    _, _, body, request_id = fake.calls[0]
    assert request_id == f"topup-order:{topup_id}"
    assert body["purchase_units"][0]["custom_id"] == str(topup_id)
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "20.00"}
    assert body["payment_source"]["paypal"]["attributes"]["vault"]["store_in_vault"] == "ON_SUCCESS"
    assert await client_balance(db, client_id) == 0


@pytest.mark.parametrize("amount", [19_990_000, 500_010_000, 20_000_001])
async def test_create_order_rejects_out_of_range_or_sub_cent_amounts(db, make_client, amount):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        with pytest.raises(TopUpError):
            await create_topup_order(db, PayPalClient(sandbox(), http), client_id, amount, sandbox())

    assert fake.calls == []
    assert (await db.execute(text("SELECT COUNT(*) FROM paypal_topups"))).scalar_one() == 0


# -----------------------------------------------------------------------------
# CAPTURE
# -----------------------------------------------------------------------------

async def test_capture_credits_once_and_stores_vault(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        topup_id = await create_approved_topup(db, http, client_id)
        paypal = PayPalClient(sandbox(), http)
        first = await capture_topup(db, paypal, client_id, topup_id, sandbox())
        calls_after_first = len(fake.calls)
        second = await capture_topup(db, paypal, client_id, topup_id, sandbox())

    assert first["status"] == second["status"] == "CAPTURED"
    assert len(fake.calls) == calls_after_first  # repeat capture does not call PayPal
    assert fake.calls[-1][3] == f"topup-capture:{topup_id}"
    assert await client_balance(db, client_id) == TWENTY_DOLLARS
    assert await credit_entries(db) == 1
    row = await topup_row(db, topup_id)
    assert (row["status"], row["paypal_capture_id"]) == ("CAPTURED", "CAPTURE-ORDER-1")
    vault = (await db.execute(
        text("SELECT paypal_vault_id, paypal_payer_id FROM clients WHERE client_id = :id"), {"id": client_id}
    )).one()
    assert tuple(vault) == ("VAULT-1", "PAYER-1")


async def test_capture_by_another_client_is_refused(db, make_client):
    owner = await make_client(available_balance_micros=0)
    intruder = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        topup_id = await create_approved_topup(db, http, owner)
        with pytest.raises(TopUpError, match="not found"):
            await capture_topup(db, PayPalClient(sandbox(), http), intruder, topup_id, sandbox())

    assert await client_balance(db, owner) == 0
    assert await client_balance(db, intruder) == 0


async def test_capture_with_mismatched_amount_is_not_credited(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    fake.capture_override = lambda request, order_id: httpx.Response(
        201, json=completed_order(order_id, fake.orders[order_id]["topup_id"], "2000.00"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        topup_id = await create_approved_topup(db, http, client_id)
        with pytest.raises(TopUpError, match="amount"):
            await capture_topup(db, PayPalClient(sandbox(), http), client_id, topup_id, sandbox())
    await db.rollback()

    assert await client_balance(db, client_id) == 0
    assert (await topup_row(db, topup_id))["status"] == "CREATED"


async def test_capture_before_buyer_approval_is_refused(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    fake.capture_override = lambda request, order_id: httpx.Response(422, json={
        "name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_NOT_APPROVED"}], "debug_id": "d1"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        topup_id = await create_approved_topup(db, http, client_id)
        with pytest.raises(TopUpError, match="not approved"):
            await capture_topup(db, PayPalClient(sandbox(), http), client_id, topup_id, sandbox())
    await db.rollback()

    assert await client_balance(db, client_id) == 0


async def test_capture_timeout_then_retry_credits_once(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    attempts = []

    def flaky_capture(request, order_id):
        attempts.append(request.headers["PayPal-Request-Id"])
        if len(attempts) == 1:
            raise httpx.ReadTimeout("lost response", request=request)
        return httpx.Response(201, json=completed_order(order_id, fake.orders[order_id]["topup_id"], "20.00"))

    fake.capture_override = flaky_capture
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        topup_id = await create_approved_topup(db, http, client_id)
        paypal = PayPalClient(sandbox(), http)
        with pytest.raises(httpx.ReadTimeout):
            await capture_topup(db, paypal, client_id, topup_id, sandbox())
        await db.rollback()
        await capture_topup(db, paypal, client_id, topup_id, sandbox())

    assert attempts == [f"topup-capture:{topup_id}"] * 2
    assert await client_balance(db, client_id) == TWENTY_DOLLARS
    assert await credit_entries(db) == 1


async def test_already_captured_order_is_fetched_and_credited(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    fake.capture_override = lambda request, order_id: httpx.Response(422, json={
        "name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        topup_id = await create_approved_topup(db, http, client_id)
        await capture_topup(db, PayPalClient(sandbox(), http), client_id, topup_id, sandbox())

    assert fake.calls[-1][0] == "GET"
    assert await client_balance(db, client_id) == TWENTY_DOLLARS


# -----------------------------------------------------------------------------
# VAULTED AUTO TOP-UPS
# -----------------------------------------------------------------------------

async def vaulted_client(db, make_client) -> uuid.UUID:
    client_id = await make_client(available_balance_micros=0)
    await db.execute(text("UPDATE clients SET paypal_vault_id = 'VAULT-1' WHERE client_id = :id"), {"id": client_id})
    await db.commit()
    return client_id


async def test_vaulted_charge_credits_once_per_idempotency_key(db, make_client):
    client_id = await vaulted_client(db, make_client)
    key = uuid.uuid4()
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        paypal = PayPalClient(sandbox(), http)
        first = await charge_vaulted_topup(db, paypal, client_id, TWENTY_DOLLARS, key, sandbox())
        second = await charge_vaulted_topup(db, paypal, client_id, TWENTY_DOLLARS, key, sandbox())

    assert first["status"] == second["status"] == "CAPTURED"
    assert len([c for c in fake.calls if c[1] == "/v2/checkout/orders"]) == 1
    assert fake.calls[0][2]["payment_source"] == {"paypal": {"vault_id": "VAULT-1"}}
    assert fake.calls[0][3] == f"topup-order:{key}"
    assert await client_balance(db, client_id) == TWENTY_DOLLARS
    assert (await topup_row(db, key))["is_vaulted_charge"] is True


async def test_vaulted_charge_requires_saved_account(db, make_client):
    client_id = await make_client(available_balance_micros=0)
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        with pytest.raises(TopUpError, match="No saved PayPal account"):
            await charge_vaulted_topup(db, PayPalClient(sandbox(), http), client_id, TWENTY_DOLLARS, uuid.uuid4(), sandbox())

    assert fake.calls == []


async def test_vaulted_charge_rejects_reused_key_with_different_amount(db, make_client):
    client_id = await vaulted_client(db, make_client)
    key = uuid.uuid4()
    fake = FakePayPal()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        paypal = PayPalClient(sandbox(), http)
        await charge_vaulted_topup(db, paypal, client_id, TWENTY_DOLLARS, key, sandbox())
        with pytest.raises(TopUpError, match="different top-up"):
            await charge_vaulted_topup(db, paypal, client_id, 30_000_000, key, sandbox())
    await db.rollback()

    assert await client_balance(db, client_id) == TWENTY_DOLLARS


@pytest.mark.parametrize("paypal_status,stored_status", [("DECLINED", "FAILED"), ("PENDING", "CREATED")])
async def test_vaulted_charge_not_completed_is_not_credited(db, make_client, paypal_status, stored_status):
    client_id = await vaulted_client(db, make_client)
    key = uuid.uuid4()
    fake = FakePayPal()
    fake.vault_capture_status = paypal_status
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
        with pytest.raises(TopUpError):
            await charge_vaulted_topup(db, PayPalClient(sandbox(), http), client_id, TWENTY_DOLLARS, key, sandbox())

    assert await client_balance(db, client_id) == 0
    assert (await topup_row(db, key))["status"] == stored_status
