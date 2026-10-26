"""
ApexMarket: Settlement API Routes
Releases matured probation earnings so new nodes become payable after their hold, and
receives PayPal webhooks for top-up captures and node payouts.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_mission_control import require_admin
from app.config import get_settings
from app.database import get_db
from app.services.ledger_service import LedgerService
from app.services.paypal_client import PayPalClient, PayPalError
from app.services.paypal_webhook_service import handle_webhook_event, verify_webhook_signature

router = APIRouter(tags=["Settlement"])


@router.post(
    "/ledger/probation/release",
    dependencies=[Depends(require_admin)],
    summary="Release matured probation earnings",
)
async def release_probation(db: AsyncSession = Depends(get_db)):
    """Moves probation credits older than PROBATION_ESCROW_DAYS to node withdrawable balances."""
    result = await LedgerService.release_matured_probation(db, hold_days=get_settings().PROBATION_ESCROW_DAYS)
    await db.commit()
    return result


@router.post("/webhooks/paypal", summary="Receive PayPal webhook events")
async def paypal_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Verifies the event with PayPal, then applies it. Non-2xx responses make PayPal retry,
    which is safe because every handler is idempotent.
    """
    settings = get_settings()
    try:
        event = await request.json()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook body must be JSON.")
    if not isinstance(event, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook body must be a JSON object.")

    try:
        async with httpx.AsyncClient(timeout=20) as http:
            paypal = PayPalClient(settings, http)
            if not await verify_webhook_signature(paypal, settings, request.headers, event):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook signature could not be verified.")
            return await handle_webhook_event(db, paypal, http, settings, event)
    except ValueError as exc:  # webhook or sandbox not configured
        await db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except (PayPalError, httpx.HTTPError):
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal could not be reached; the event will be retried.")
