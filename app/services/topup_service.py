"""
ApexMarket: Prepaid Client Balance Top-Ups (PayPal Orders v2 + Vaulting)
Clients add credit in chunks (e.g. $20) instead of paying per job, so PayPal's fixed
checkout fee stays small. Each top-up is a row in paypal_topups whose topup_id is both
the PayPal-Request-Id and the order's custom_id; a capture can only ever credit the
client and amount recorded on that row.
"""

from typing import Any, Dict, Optional
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.ledger_service import MICROS_PER_CENT, LedgerService, micros_to_usd_str
from app.services.paypal_client import PayPalClient, PayPalError
from app.services.sandbox_payout_service import require_sandbox


class TopUpError(ValueError):
    """A top-up request we refuse (bad amount, wrong client, not approved, mismatch)."""


def validate_topup_amount(amount_micros: int, settings: Settings) -> None:
    if amount_micros % MICROS_PER_CENT != 0:
        raise TopUpError("Top-up amounts must be whole cents.")
    if not settings.MIN_TOPUP_MICROS <= amount_micros <= settings.MAX_TOPUP_MICROS:
        raise TopUpError(
            f"Top-up must be between ${micros_to_usd_str(settings.MIN_TOPUP_MICROS)} "
            f"and ${micros_to_usd_str(settings.MAX_TOPUP_MICROS)}."
        )


def build_topup_order(topup_id: uuid.UUID, amount_micros: int, settings: Settings) -> Dict[str, Any]:
    """Orders v2 payload that asks PayPal to vault the buyer's account on a successful capture."""
    return {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": str(topup_id),
                "custom_id": str(topup_id),
                "description": "ApexMarket prepaid inference credit",
                "amount": {"currency_code": "USD", "value": micros_to_usd_str(amount_micros)},
            }
        ],
        "payment_source": {
            "paypal": {
                "attributes": {"vault": {"store_in_vault": "ON_SUCCESS", "usage_type": "MERCHANT"}},
                "experience_context": {
                    "return_url": settings.TOPUP_RETURN_URL,
                    "cancel_url": settings.TOPUP_CANCEL_URL,
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                },
            }
        },
    }


def approval_url(order: Dict[str, Any]) -> Optional[str]:
    """The link the buyer opens to approve the order (payer-action for vaulting flows)."""
    for rel in ("payer-action", "approve"):
        for link in order.get("links", []):
            if link.get("rel") == rel:
                return link.get("href")
    return None


async def create_topup_order(
    db: AsyncSession,
    paypal: PayPalClient,
    client_id: uuid.UUID,
    amount_micros: int,
    settings: Settings,
) -> Dict[str, Any]:
    """
    Records a top-up, then creates the PayPal order the buyer must approve.
    The row is committed before PayPal is called so a later capture or webhook can
    always find it. An order that is never approved is simply never credited.
    """
    require_sandbox(settings)
    validate_topup_amount(amount_micros, settings)

    topup_id = uuid.uuid4()
    await db.execute(
        text("INSERT INTO paypal_topups (topup_id, client_id, amount_micros) VALUES (:id, :client_id, :amount)"),
        {"id": topup_id, "client_id": client_id, "amount": amount_micros},
    )
    await db.commit()

    order = await paypal.request(
        "POST",
        "/v2/checkout/orders",
        json=build_topup_order(topup_id, amount_micros, settings),
        request_id=f"topup-order:{topup_id}",
    )
    await db.execute(
        text("UPDATE paypal_topups SET paypal_order_id = :order_id WHERE topup_id = :id"),
        {"order_id": order["id"], "id": topup_id},
    )
    await db.commit()

    return {
        "topup_id": topup_id,
        "paypal_order_id": order["id"],
        "approve_url": approval_url(order),
        "amount_micros": amount_micros,
        "status": "CREATED",
    }


def _paypal_issue(error: PayPalError) -> Optional[str]:
    details = error.body.get("details") or [{}]
    return details[0].get("issue")


def extract_completed_capture(order: Dict[str, Any], topup_id: uuid.UUID, amount_micros: int) -> Dict[str, Any]:
    """
    Returns the order's capture only if PayPal reports it COMPLETED in USD for exactly
    the recorded amount and tagged with this top-up. Anything else is refused.
    """
    units = order.get("purchase_units") or [{}]
    unit = units[0]
    captures = (unit.get("payments") or {}).get("captures") or []
    if not captures:
        raise TopUpError("PayPal returned no capture for this order.")
    capture = captures[0]

    if capture.get("status") != "COMPLETED":
        raise TopUpError(f"PayPal capture is {capture.get('status')}, not COMPLETED.")
    tag = capture.get("custom_id") or unit.get("custom_id") or unit.get("reference_id")
    if tag != str(topup_id):
        raise TopUpError("PayPal capture does not belong to this top-up.")
    amount = capture.get("amount") or {}
    if amount.get("currency_code") != "USD" or amount.get("value") != micros_to_usd_str(amount_micros):
        raise TopUpError("PayPal capture amount does not match the recorded top-up.")
    return capture


async def apply_verified_capture(db: AsyncSession, topup: Dict[str, Any], capture: Dict[str, Any]) -> None:
    """
    Marks a top-up CAPTURED and credits the client, from a capture already checked by
    extract_completed_capture. The credit is idempotent per top-up.
    """
    await LedgerService.credit_client_topup(db, topup["client_id"], topup["topup_id"], topup["amount_micros"])
    await db.execute(
        text("""
            UPDATE paypal_topups
            SET status = 'CAPTURED', paypal_capture_id = :capture_id, captured_at = NOW()
            WHERE topup_id = :id AND status <> 'CAPTURED'
        """),
        {"capture_id": capture["id"], "id": topup["topup_id"]},
    )


async def store_vault_from_order(db: AsyncSession, client_id: uuid.UUID, order: Dict[str, Any]) -> Optional[str]:
    """
    Saves the vault id PayPal returns once the buyer's account is stored (status VAULTED),
    so later top-ups can be charged without the buyer present. Returns the vault id.
    """
    paypal_source = (order.get("payment_source") or {}).get("paypal") or {}
    vault = (paypal_source.get("attributes") or {}).get("vault") or {}
    if vault.get("status") != "VAULTED" or not vault.get("id"):
        return None

    payer_id = paypal_source.get("account_id") or (order.get("payer") or {}).get("payer_id")
    await db.execute(
        text("""
            UPDATE clients
            SET paypal_vault_id = :vault_id,
                paypal_payer_id = COALESCE(:payer_id, paypal_payer_id)
            WHERE client_id = :client_id
        """),
        {"vault_id": vault["id"], "payer_id": payer_id, "client_id": client_id},
    )
    return vault["id"]


def topup_receipt(topup: Dict[str, Any], status: str) -> Dict[str, Any]:
    return {
        "topup_id": topup["topup_id"],
        "paypal_order_id": topup["paypal_order_id"],
        "amount_micros": topup["amount_micros"],
        "status": status,
    }


async def capture_topup(
    db: AsyncSession,
    paypal: PayPalClient,
    client_id: uuid.UUID,
    topup_id: uuid.UUID,
    settings: Settings,
) -> Dict[str, Any]:
    """
    Captures a buyer-approved top-up order. Safe to call repeatedly: the top-up row is
    locked for the whole call, the PayPal request id is fixed per top-up, and an already
    captured top-up returns its receipt without calling PayPal again.
    """
    require_sandbox(settings)
    row = (
        await db.execute(
            text("SELECT * FROM paypal_topups WHERE topup_id = :id FOR UPDATE"),
            {"id": topup_id},
        )
    ).mappings().first()
    if not row or row["client_id"] != client_id:
        raise TopUpError("Top-up not found.")
    topup = dict(row)
    if topup["status"] == "CAPTURED":
        await db.commit()
        return topup_receipt(topup, "CAPTURED")
    if topup["status"] == "FAILED" or not topup["paypal_order_id"]:
        raise TopUpError("This top-up can no longer be captured; start a new one.")

    order_path = f"/v2/checkout/orders/{topup['paypal_order_id']}"
    try:
        order = await paypal.request("POST", f"{order_path}/capture", json={}, request_id=f"topup-capture:{topup_id}")
    except PayPalError as error:
        issue = _paypal_issue(error)
        if issue == "ORDER_ALREADY_CAPTURED":
            order = await paypal.request("GET", order_path)
        elif issue in ("ORDER_NOT_APPROVED", "PAYER_ACTION_REQUIRED"):
            raise TopUpError("The buyer has not approved this top-up in PayPal yet.") from error
        elif issue == "INSTRUMENT_DECLINED":
            raise TopUpError("PayPal declined the payment method; the buyer can retry approval.") from error
        else:
            raise

    capture = extract_completed_capture(order, topup_id, topup["amount_micros"])
    await apply_verified_capture(db, topup, capture)
    await store_vault_from_order(db, client_id, order)
    await db.commit()
    return topup_receipt(topup, "CAPTURED")


async def charge_vaulted_topup(
    db: AsyncSession,
    paypal: PayPalClient,
    client_id: uuid.UUID,
    amount_micros: int,
    idempotency_key: uuid.UUID,
    settings: Settings,
) -> Dict[str, Any]:
    """
    Charges the client's vaulted PayPal account without the buyer present (for agents
    that top up their own balance). The caller's idempotency key becomes the topup_id,
    so a retried call returns the first result instead of charging twice.
    """
    require_sandbox(settings)
    validate_topup_amount(amount_micros, settings)

    vault_id = (
        await db.execute(
            text("SELECT paypal_vault_id FROM clients WHERE client_id = :id"),
            {"id": client_id},
        )
    ).scalar_one_or_none()
    if not vault_id:
        raise TopUpError("No saved PayPal account; complete one approved top-up first.")

    await db.execute(
        text("""
            INSERT INTO paypal_topups (topup_id, client_id, amount_micros, is_vaulted_charge)
            VALUES (:id, :client_id, :amount, TRUE)
            ON CONFLICT (topup_id) DO NOTHING
        """),
        {"id": idempotency_key, "client_id": client_id, "amount": amount_micros},
    )
    await db.commit()

    row = (
        await db.execute(
            text("SELECT * FROM paypal_topups WHERE topup_id = :id FOR UPDATE"),
            {"id": idempotency_key},
        )
    ).mappings().one()
    topup = dict(row)
    if topup["client_id"] != client_id or not topup["is_vaulted_charge"] or topup["amount_micros"] != amount_micros:
        raise TopUpError("This idempotency key was already used for a different top-up.")
    if topup["status"] != "CREATED":
        await db.commit()
        return topup_receipt(topup, topup["status"])

    payload = {
        "intent": "CAPTURE",
        "purchase_units": build_topup_order(idempotency_key, amount_micros, settings)["purchase_units"],
        "payment_source": {"paypal": {"vault_id": vault_id}},
    }
    order = await paypal.request("POST", "/v2/checkout/orders", json=payload, request_id=f"topup-order:{idempotency_key}")
    await db.execute(
        text("UPDATE paypal_topups SET paypal_order_id = :order_id WHERE topup_id = :id"),
        {"order_id": order["id"], "id": idempotency_key},
    )
    topup["paypal_order_id"] = order["id"]

    try:
        capture = extract_completed_capture(order, idempotency_key, amount_micros)
    except TopUpError:
        await db.execute(
            text("UPDATE paypal_topups SET status = 'FAILED' WHERE topup_id = :id"),
            {"id": idempotency_key},
        )
        await db.commit()
        raise

    await apply_verified_capture(db, topup, capture)
    await db.commit()
    return topup_receipt(topup, "CAPTURED")
