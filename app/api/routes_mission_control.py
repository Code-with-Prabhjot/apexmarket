"""Mission Control evidence, sandbox settlement, and opt-in local chaos controls."""
import hmac
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.services.sandbox_payout_service import submit_batch, reconcile_batch, require_sandbox

router = APIRouter(tags=["Mission Control"])


async def require_admin(x_admin_key: str = Header(default="")):
    expected = get_settings().ADMIN_API_KEY
    if not expected or not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
        raise HTTPException(403, "A valid sandbox admin key is required.")


class DriftRequest(BaseModel):
    degraded: bool = True


@router.post("/demo/drift", dependencies=[Depends(require_admin)])
async def inject_drift(request: DriftRequest):
    settings = get_settings()
    target = urlparse(settings.DEMO_MOCK_PROVIDER_URL)
    if not settings.DEMO_CHAOS_ENABLED or settings.APP_ENV == "production":
        raise HTTPException(403, "Enable local demo chaos before using this action.")
    if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost", "::1"} or target.username or target.password or target.query or target.fragment or target.path not in {"", "/"}:
        raise HTTPException(403, "Chaos must target a configured loopback mock provider.")
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            response = await client.post(f"{settings.DEMO_MOCK_PROVIDER_URL.rstrip('/')}/admin/config", json={"degraded": request.degraded})
            response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "The configured mock provider could not be reached.")
    return {"degraded": request.degraded, "status": "MOCK_CONFIGURED"}


@router.get("/jobs/{job_id}/attestations")
async def get_attestations(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT shred_id, node_id, status, measured_input_tokens, measured_output_tokens,
            canary_pass_rate, anchor_nll_score, nemotron_judge_score, server_hmac_attestation
        FROM job_shreds WHERE job_id = :id ORDER BY created_at, shred_id
    """), {"id": job_id})
    return [dict(row) for row in rows.mappings()]


@router.post("/ledger/settle-now", dependencies=[Depends(require_admin)])
async def settle_now(idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"), db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    try:
        require_sandbox(settings)
        async with httpx.AsyncClient(timeout=20) as client:
            return await submit_batch(db, idempotency_key, settings, client)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))
    except httpx.HTTPError:
        await db.rollback()
        raise HTTPException(502, "PayPal has not confirmed this request. Retry with the same idempotency key; reserved funds stay pending.")


@router.post("/ledger/payouts/{batch_id}/reconcile", dependencies=[Depends(require_admin)])
async def reconcile_payout(batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            return await reconcile_batch(db, batch_id, get_settings(), client)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))
    except httpx.HTTPError:
        await db.rollback()
        raise HTTPException(502, "PayPal reconciliation is temporarily unavailable.")
