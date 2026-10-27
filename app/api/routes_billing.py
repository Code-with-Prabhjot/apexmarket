"""
ApexMarket: Client Billing API Routes
Prepaid PayPal top-ups (approve-and-capture, and vaulted auto top-ups) and the
client balance view.
"""

import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_jobs import get_authenticated_client
from app.config import get_settings
from app.database import get_db
from app.schemas import ClientBalanceResponse, TopUpCreateRequest, TopUpResponse
from app.services.ledger_service import micros_to_usd_str
from app.services.paypal_client import PayPalClient, PayPalError
from app.services.topup_service import (
    TopUpError,
    TopUpNotFound,
    capture_topup,
    charge_vaulted_topup,
    create_topup_order,
)

router = APIRouter(prefix="/billing", tags=["Billing"])

UNCONFIRMED_DETAIL = "PayPal has not confirmed this request. Retry the same request; it will not be charged twice."

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


async def run_topup_action(db: AsyncSession, action) -> dict:
    """Runs a top-up service call with a persistent or mocked PayPal client and maps its errors to HTTP."""
    settings = get_settings()
    try:
        if httpx.AsyncClient is not _ORIGINAL_ASYNC_CLIENT:
            async with httpx.AsyncClient(timeout=20) as http:
                return await action(PayPalClient(settings, http), settings)
        else:
            return await action(PayPalClient(settings), settings)
    except TopUpNotFound as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except TopUpError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except ValueError as exc:  # e.g. PayPal Sandbox not configured
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except PayPalError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"PayPal rejected the request ({exc.name}, debug_id={exc.debug_id}).")
    except httpx.HTTPError:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNCONFIRMED_DETAIL)


@router.post("/topups", response_model=TopUpResponse, status_code=status.HTTP_201_CREATED, summary="Start a prepaid top-up")
async def start_topup(
    request: TopUpCreateRequest,
    client_id: uuid.UUID = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db),
):
    """Creates a PayPal order; send the buyer to approve_url, then call the capture endpoint."""
    return await run_topup_action(
        db, lambda paypal, settings: create_topup_order(db, paypal, client_id, request.amount_micros, settings)
    )


@router.post("/topups/{topup_id}/capture", response_model=TopUpResponse, summary="Capture an approved top-up")
async def capture_approved_topup(
    topup_id: uuid.UUID,
    client_id: uuid.UUID = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db),
):
    """Captures the buyer-approved order and credits the client balance once."""
    return await run_topup_action(
        db, lambda paypal, settings: capture_topup(db, paypal, client_id, topup_id, settings)
    )


@router.post("/topups/auto", response_model=TopUpResponse, summary="Top up from the saved PayPal account")
async def auto_topup(
    request: TopUpCreateRequest,
    idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    client_id: uuid.UUID = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db),
):
    """Charges the vaulted PayPal account. Retrying with the same Idempotency-Key never charges twice."""
    return await run_topup_action(
        db,
        lambda paypal, settings: charge_vaulted_topup(
            db, paypal, client_id, request.amount_micros, idempotency_key, settings
        ),
    )


@router.get("/balance", response_model=ClientBalanceResponse, summary="Get the client's balance")
async def get_balance(
    client_id: uuid.UUID = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            text("""
                SELECT client_id, organization_name, available_balance_micros,
                       locked_escrow_micros, hourly_spend_limit_micros
                FROM clients WHERE client_id = :id
            """),
            {"id": client_id},
        )
    ).one()
    return ClientBalanceResponse(
        client_id=row.client_id,
        organization_name=row.organization_name,
        available_balance_micros=row.available_balance_micros,
        locked_escrow_micros=row.locked_escrow_micros,
        hourly_spend_limit_micros=row.hourly_spend_limit_micros,
        available_balance_usd=micros_to_usd_str(row.available_balance_micros),
        locked_escrow_usd=micros_to_usd_str(row.locked_escrow_micros),
    )
