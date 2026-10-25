"""Real PostgreSQL payout reservation and reconciliation with mocked PayPal HTTP."""
import json
import uuid
import httpx
import pytest
from sqlalchemy import text
from app.config import Settings
from app.services.sandbox_payout_service import prepare_batch, submit_batch, reconcile_batch


def sandbox():
    return Settings(PAYPAL_MODE="sandbox", PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com", PAYPAL_CLIENT_ID="test", PAYPAL_CLIENT_SECRET="test")


async def fund(db, node):
    await db.execute(text("UPDATE compute_nodes SET withdrawable_micros = 1234567 WHERE node_id = :node"), {"node": node})
    await db.commit()


@pytest.mark.asyncio
async def test_reserve_retry_conserves_balance_and_snapshots_receiver(db, make_node):
    node = await make_node()
    await fund(db, node)
    batch = uuid.uuid4()
    first = await prepare_batch(db, batch)
    await db.commit()
    second = await prepare_batch(db, batch)
    await db.commit()
    assert first["total_amount_micros"] == second["total_amount_micros"] == 1230000
    balance = (await db.execute(text("SELECT withdrawable_micros, payout_pending_micros FROM compute_nodes WHERE node_id=:node"), {"node": node})).one()
    assert tuple(balance) == (4567, 1230000)
    assert (await db.execute(text("SELECT COUNT(*) FROM ledger_entries WHERE idempotency_key LIKE 'payout_reserve:%'"))).scalar_one() == 1
    assert (await db.execute(text("SELECT payout_receiver_email FROM payout_items WHERE batch_id=:id"), {"id": batch})).scalar_one() == "node@example.invalid"


@pytest.mark.asyncio
async def test_timeout_retry_uses_same_uuid_payload_and_only_reserves_once(db, make_node):
    node = await make_node()
    await fund(db, node)
    batch = uuid.uuid4()
    payloads = []
    async def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        payloads.append(json.loads(request.content))
        assert request.headers["PayPal-Request-Id"] == str(batch)
        if len(payloads) == 1:
            raise httpx.ReadTimeout("ambiguous response", request=request)
        return httpx.Response(201, json={"batch_header": {"payout_batch_id": "PAYPAL-1"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):
            await submit_batch(db, batch, sandbox(), client)
        await db.rollback()
        await db.execute(text("UPDATE compute_nodes SET paypal_receiver_email='changed@example.invalid' WHERE node_id=:node"), {"node": node})
        await db.commit()
        receipt = await submit_batch(db, batch, sandbox(), client)
        assert receipt["status"] == "SUBMITTED_PENDING"
        await submit_batch(db, batch, sandbox(), client)
    assert len(payloads) == 2 and payloads[0] == payloads[1]
    assert payloads[1]["items"][0]["receiver"] == "node@example.invalid"
    balance = (await db.execute(text("SELECT withdrawable_micros, payout_pending_micros FROM compute_nodes WHERE node_id=:node"), {"node": node})).one()
    assert tuple(balance) == (4567, 1230000)


@pytest.mark.asyncio
@pytest.mark.parametrize("remote_status,expected_status,withdrawable", [("SUCCESS", "COMPLETED", 4567), ("FAILED", "FAILED_REVERSED", 1234567)])
async def test_remote_outcome_reconciles_exactly_once(db, make_node, remote_status, expected_status, withdrawable):
    node = await make_node()
    await fund(db, node)
    batch = uuid.uuid4()
    await prepare_batch(db, batch)
    await db.execute(text("UPDATE payout_batches SET paypal_batch_id='REMOTE-1',status='SUBMITTED_PENDING' WHERE batch_id=:id"), {"id": batch})
    await db.commit()
    item = (await db.execute(text("SELECT item_id FROM payout_items WHERE batch_id=:id"), {"id": batch})).scalar_one()
    async def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, json={"total_pages": 1, "items": [{"payout_item_id": "REMOTE-ITEM", "payout_item": {"sender_item_id": str(item)}, "transaction_status": remote_status}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for _ in range(2):
            receipt = await reconcile_batch(db, batch, sandbox(), client)
            assert receipt["status"] == expected_status
    balance = (await db.execute(text("SELECT withdrawable_micros,payout_pending_micros FROM compute_nodes WHERE node_id=:node"), {"node": node})).one()
    assert tuple(balance) == (withdrawable, 0)


@pytest.mark.asyncio
async def test_competing_batches_do_not_reserve_same_node(session_factory, make_node):
    node = await make_node()
    async with session_factory() as session:
        await fund(session, node)
    async with session_factory() as first, session_factory() as second:
        reserved = await prepare_batch(first, uuid.uuid4())
        competing = await prepare_batch(second, uuid.uuid4())
        await second.commit()
        await first.commit()
    assert reserved["total_amount_micros"] == 1230000
    assert competing["status"] == "NO_PAYABLE_BALANCE"
