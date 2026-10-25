"""Durable, integer-only sandbox payout preparation and submission.

Reservation is committed before PayPal is contacted. An uncertain HTTP outcome
keeps funds pending and reuses the persisted batch UUID on retry. Only authenticated
PayPal responses reconcile balances; a successful submission is never called paid.
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.ledger_service import LedgerService, calculate_subcent_split, micros_to_usd_str, usd_to_micros

SANDBOX_ORIGIN = "https://api-m.sandbox.paypal.com"
FAILED_ITEM_STATUSES = {"FAILED", "RETURNED", "REFUNDED", "REVERSED", "DENIED", "CANCELED"}


def payout_payload(batch_id: uuid.UUID, items: list[dict]) -> dict:
    return {
        "sender_batch_header": {"sender_batch_id": str(batch_id), "email_subject": "ApexMarket verified compute payout"},
        "items": [{"recipient_type": "EMAIL", "receiver": i["receiver"],
                   "sender_item_id": str(i["item_id"]),
                   "amount": {"currency": "USD", "value": micros_to_usd_str(i["amount_paid_micros"])}}
                  for i in items],
    }


def require_sandbox(settings: Settings) -> None:
    if settings.PAYPAL_MODE != "sandbox" or settings.PAYPAL_BASE_URL.rstrip("/") != SANDBOX_ORIGIN:
        raise ValueError("This admin action requires the PayPal Sandbox environment.")
    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
        raise ValueError("Configure PayPal Sandbox credentials before submitting a payout.")


async def prepare_batch(db: AsyncSession, batch_id: uuid.UUID) -> dict:
    # Same idempotency key serializes even before its batch row exists.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(batch_id)})
    existing = (await db.execute(text("SELECT * FROM payout_batches WHERE batch_id = :id"), {"id": batch_id})).mappings().first()
    if existing:
        return dict(existing)
    nodes = (await db.execute(text("""
        SELECT node_id, withdrawable_micros, paypal_receiver_email
        FROM compute_nodes WHERE is_active AND withdrawable_micros >= 10000
        ORDER BY node_id LIMIT 1000 FOR UPDATE SKIP LOCKED
    """))).mappings().all()
    if not nodes:
        return {"batch_id": str(batch_id), "status": "NO_PAYABLE_BALANCE", "total_amount_micros": 0}
    total = sum(calculate_subcent_split(n["withdrawable_micros"])[0] for n in nodes)
    await db.execute(text("INSERT INTO payout_batches (batch_id, total_amount_micros) VALUES (:id, :total)"), {"id": batch_id, "total": total})
    for node in nodes:
        payable, remainder = calculate_subcent_split(node["withdrawable_micros"])
        item_id = uuid.uuid5(batch_id, node["node_id"])
        await db.execute(text("""
            INSERT INTO payout_items (item_id, batch_id, node_id, amount_paid_micros, remainder_carried_micros, payout_receiver_email)
            VALUES (:item, :batch, :node, :amount, :remainder, :receiver)
        """), {"item": item_id, "batch": batch_id, "node": node["node_id"], "amount": payable, "remainder": remainder, "receiver": node["paypal_receiver_email"]})
        await db.execute(text("""
            UPDATE compute_nodes SET withdrawable_micros = withdrawable_micros - :amount,
                payout_pending_micros = payout_pending_micros + :amount WHERE node_id = :node
        """), {"amount": payable, "node": node["node_id"]})
        await LedgerService.record_entry(db, f"payout_reserve:{item_id}", f"node_withdrawable:{node['node_id']}",
                                         f"node_payout_pending:{node['node_id']}", payable, "Sandbox payout reservation")
    return {"batch_id": str(batch_id), "status": "CREATED", "total_amount_micros": total}


async def access_token(client: httpx.AsyncClient, settings: Settings) -> str:
    response = await client.post(f"{SANDBOX_ORIGIN}/v1/oauth2/token", auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET), data={"grant_type": "client_credentials"})
    response.raise_for_status()
    return response.json()["access_token"]


async def submit_batch(db: AsyncSession, batch_id: uuid.UUID, settings: Settings, client: httpx.AsyncClient) -> dict:
    require_sandbox(settings)
    receipt = await prepare_batch(db, batch_id)
    await db.commit()  # Reservation survives timeouts, retries, and process restarts.
    if receipt["status"] == "NO_PAYABLE_BALANCE":
        return receipt
    batch = dict((await db.execute(text("SELECT * FROM payout_batches WHERE batch_id = :id FOR UPDATE"), {"id": batch_id})).mappings().one())
    if batch["status"] != "CREATED":
        await db.commit()
        return batch
    # PayPal's duplicate protection expires after 30 days. Never resubmit an old ambiguous batch.
    if batch["created_at"] < datetime.now(timezone.utc) - timedelta(days=29):
        raise ValueError("This reserved batch requires reconciliation before another submission.")
    items = (await db.execute(text("""
        SELECT p.*, p.payout_receiver_email AS receiver FROM payout_items p
        WHERE p.batch_id = :id ORDER BY p.item_id
    """), {"id": batch_id})).mappings().all()
    if any(not item["receiver"] for item in items):
        raise ValueError("A legacy payout requires its original recipient snapshot before retrying.")
    headers = {"Authorization": f"Bearer {await access_token(client, settings)}", "PayPal-Request-Id": str(batch_id)}
    response = await client.post(f"{SANDBOX_ORIGIN}/v1/payments/payouts", headers=headers, json=payout_payload(batch_id, items))
    if response.status_code == 400:
        error = response.json()
        # PayPal includes the original payout link for duplicate sender_batch_id.
        links = list(error.get("links", []))
        for detail in error.get("details", []):
            links.extend(detail.get("links", []))
        for link in links:
            parsed = urlparse(link.get("href", ""))
            if parsed.scheme == "https" and parsed.netloc == "api-m.sandbox.paypal.com" and parsed.path.startswith("/v1/payments/payouts/"):
                response = await client.get(f"{SANDBOX_ORIGIN}{parsed.path}", headers=headers)
                break
    response.raise_for_status()
    paypal_id = response.json()["batch_header"]["payout_batch_id"]
    await db.execute(text("""
        UPDATE payout_batches SET paypal_batch_id = :paypal, status = 'SUBMITTED_PENDING', updated_at = NOW()
        WHERE batch_id = :id
    """), {"paypal": paypal_id, "id": batch_id})
    await db.commit()
    return {**receipt, "paypal_batch_id": paypal_id, "status": "SUBMITTED_PENDING"}


async def reconcile_batch(db: AsyncSession, batch_id: uuid.UUID, settings: Settings, client: httpx.AsyncClient) -> dict:
    require_sandbox(settings)
    batch_row = (await db.execute(text("SELECT * FROM payout_batches WHERE batch_id = :id FOR UPDATE"), {"id": batch_id})).mappings().first()
    if not batch_row or not batch_row["paypal_batch_id"]:
        raise ValueError("Submit this batch before reconciling it.")
    batch = dict(batch_row)
    headers = {"Authorization": f"Bearer {await access_token(client, settings)}"}
    remote_items = []
    page = 1
    fee_micros = None
    while True:
        response = await client.get(f"{SANDBOX_ORIGIN}/v1/payments/payouts/{batch['paypal_batch_id']}", headers=headers, params={"page": page, "page_size": 1000})
        response.raise_for_status()
        data = response.json()
        fee_value = ((data.get("batch_header") or {}).get("fees") or {}).get("value")
        if fee_micros is None and fee_value is not None:
            fee_micros = usd_to_micros(fee_value)  # PayPal's payout fee, paid by the platform
        remote_items.extend(data.get("items", []))
        if page >= int(data.get("total_pages", 1)):
            break
        page += 1
    for remote in remote_items:
        sender_id = remote.get("payout_item", {}).get("sender_item_id")
        try:
            item_id = uuid.UUID(sender_id)
        except (ValueError, TypeError, AttributeError):
            continue
        item_row = (await db.execute(text("SELECT * FROM payout_items WHERE batch_id = :batch AND item_id = :item FOR UPDATE"), {"batch": batch_id, "item": item_id})).mappings().first()
        if not item_row:
            continue
        item = dict(item_row)
        remote_status = remote.get("transaction_status")
        previous = item["item_status"]
        outcome = "SUCCESS" if remote_status == "SUCCESS" else "FAILED" if remote_status in FAILED_ITEM_STATUSES else "PENDING"
        if outcome == "PENDING" or outcome == previous or previous == "FAILED":
            continue
        amount, node = item["amount_paid_micros"], item["node_id"]
        # A previously successful payout can subsequently be returned/reversed.
        if previous == "SUCCESS" and outcome != "FAILED":
            continue
        debit = "paypal_disbursed" if previous == "SUCCESS" else f"node_payout_pending:{node}"
        credit = "paypal_disbursed" if outcome == "SUCCESS" else f"node_withdrawable:{node}"
        entry = await LedgerService.insert_entry_if_new(db, f"payout_reconcile:{item_id}:{outcome}", debit, credit, amount, f"PayPal Sandbox {remote_status}")
        if entry is not None:
            await db.execute(text("""
                UPDATE compute_nodes SET payout_pending_micros = payout_pending_micros - :pending,
                    withdrawable_micros = withdrawable_micros + :refund WHERE node_id = :node
            """), {"pending": 0 if previous == "SUCCESS" else amount, "refund": amount if outcome == "FAILED" else 0, "node": node})
        await db.execute(text("UPDATE payout_items SET item_status = :status, paypal_item_id = :paypal WHERE item_id = :item"), {"status": outcome, "paypal": remote.get("payout_item_id"), "item": item_id})
    statuses = (await db.execute(text("SELECT item_status FROM payout_items WHERE batch_id = :id"), {"id": batch_id})).scalars().all()
    state = "SUBMITTED_PENDING" if "PENDING" in statuses else "FAILED_REVERSED" if "FAILED" in statuses else "COMPLETED"
    await db.execute(text("""
        UPDATE payout_batches SET status = CAST(:status AS payout_batch_status),
            total_fee_micros = COALESCE(:fee, total_fee_micros), updated_at = NOW()
        WHERE batch_id = :id
    """), {"status": state, "fee": fee_micros, "id": batch_id})
    await db.commit()
    return {**batch, "status": state}
