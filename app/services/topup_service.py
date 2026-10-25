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
from app.services.ledger_service import MICROS_PER_CENT, micros_to_usd_str
from app.services.paypal_client import PayPalClient
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
