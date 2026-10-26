"""
ApexMarket: PayPal Webhook Verification & Event Handling
Every event is first verified with PayPal's verify-webhook-signature API. A verified event
is only used to find which top-up or payout batch changed; the current state is then
fetched from PayPal and applied through the same idempotent paths as the API calls, so a
replayed or out-of-order event cannot credit or reverse anything twice.
"""

from typing import Any, Dict, Mapping, Optional
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.paypal_client import PayPalClient
from app.services.sandbox_payout_service import reconcile_batch
from app.services.topup_service import (
    TopUpError,
    apply_verified_capture,
    extract_completed_capture,
    store_vault_from_order,
)

SIGNATURE_HEADERS = {
    "auth_algo": "paypal-auth-algo",
    "cert_url": "paypal-cert-url",
    "transmission_id": "paypal-transmission-id",
    "transmission_sig": "paypal-transmission-sig",
    "transmission_time": "paypal-transmission-time",
}


async def verify_webhook_signature(
    paypal: PayPalClient, settings: Settings, headers: Mapping[str, str], event: Dict[str, Any]
) -> bool:
    """Asks PayPal whether this event really came from PayPal for our webhook."""
    if not settings.PAYPAL_WEBHOOK_ID:
        raise ValueError("Configure PAYPAL_WEBHOOK_ID before accepting PayPal webhooks.")
    fields = {name: headers.get(header) for name, header in SIGNATURE_HEADERS.items()}
    if not all(fields.values()):
        return False

    result = await paypal.request(
        "POST",
        "/v1/notifications/verify-webhook-signature",
        json={**fields, "webhook_id": settings.PAYPAL_WEBHOOK_ID, "webhook_event": event},
    )
    return result.get("verification_status") == "SUCCESS"


async def _handle_capture_completed(db: AsyncSession, paypal: PayPalClient, resource: Dict[str, Any]) -> str:
    order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
    if not order_id:
        return "IGNORED_NO_ORDER"
    row = (
        await db.execute(
            text("SELECT * FROM paypal_topups WHERE paypal_order_id = :order_id FOR UPDATE"),
            {"order_id": order_id},
        )
    ).mappings().first()
    if not row:
        return "IGNORED_UNKNOWN_ORDER"
    topup = dict(row)
    if topup["status"] == "CAPTURED":
        await db.commit()
        return "ALREADY_CREDITED"

    order = await paypal.request("GET", f"/v2/checkout/orders/{order_id}")
    try:
        capture = extract_completed_capture(order, topup["topup_id"], topup["amount_micros"])
    except TopUpError:
        await db.commit()
        return "NOT_COMPLETED"
    await apply_verified_capture(db, topup, capture)
    await store_vault_from_order(db, topup["client_id"], order)
    await db.commit()
    return "CREDITED"


async def _handle_capture_denied(db: AsyncSession, resource: Dict[str, Any]) -> str:
    order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
    result = await db.execute(
        text("UPDATE paypal_topups SET status = 'FAILED' WHERE paypal_order_id = :order_id AND status = 'CREATED'"),
        {"order_id": order_id},
    )
    await db.commit()
    return "MARKED_FAILED" if result.rowcount else "IGNORED"


def _payout_batch_reference(event_type: str, resource: Dict[str, Any]) -> Optional[str]:
    if event_type.startswith("PAYMENT.PAYOUTSBATCH."):
        return (resource.get("batch_header") or {}).get("payout_batch_id")
    return resource.get("payout_batch_id")


async def handle_webhook_event(
    db: AsyncSession,
    paypal: PayPalClient,
    http: httpx.AsyncClient,
    settings: Settings,
    event: Dict[str, Any],
) -> Dict[str, str]:
    """Applies a verified PayPal event. Unknown event types are acknowledged and ignored."""
    event_type = event.get("event_type", "")
    resource = event.get("resource") or {}

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        action = await _handle_capture_completed(db, paypal, resource)
    elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
        action = await _handle_capture_denied(db, resource)
    elif event_type.startswith(("PAYMENT.PAYOUTSBATCH.", "PAYMENT.PAYOUTS-ITEM.")):
        paypal_batch_id = _payout_batch_reference(event_type, resource)
        batch_id: Optional[uuid.UUID] = (
            await db.execute(
                text("SELECT batch_id FROM payout_batches WHERE paypal_batch_id = :id"),
                {"id": paypal_batch_id},
            )
        ).scalar_one_or_none()
        if batch_id is None:
            action = "IGNORED_UNKNOWN_BATCH"
        else:
            await reconcile_batch(db, batch_id, settings, http)
            action = "RECONCILED"
    else:
        action = "IGNORED"

    return {"event_type": event_type, "action": action}
