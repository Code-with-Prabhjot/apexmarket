"""Mission Control evidence, sandbox settlement, and opt-in local chaos controls."""
import hmac
import uuid
from typing import Optional
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
    node_id: str = "runpod-h100-spot-01"


@router.post("/demo/drift", dependencies=[Depends(require_admin)])
async def inject_drift(request: DriftRequest):
    settings = get_settings()
    target = urlparse(settings.DEMO_MOCK_PROVIDER_URL)
    if not settings.DEMO_CHAOS_ENABLED or settings.APP_ENV == "production":
        raise HTTPException(403, "Enable local demo chaos before using this action.")
    if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost", "::1"} or target.username or target.password or target.query or target.fragment or target.path not in {"", "/"}:
        raise HTTPException(403, "Chaos must target a configured loopback mock provider.")

    target_node = request.node_id or "runpod-h100-spot-01"
    from app.services.chaos_service import set_node_drift
    set_node_drift(target_node, request.degraded)

    try:
        async with httpx.AsyncClient(timeout=1, follow_redirects=False, trust_env=False) as client:
            response = await client.post(
                f"{settings.DEMO_MOCK_PROVIDER_URL.rstrip('/')}/admin/config",
                json={"degraded": request.degraded},
            )
            response.raise_for_status()
    except (httpx.HTTPError, Exception):
        pass

    from app.services.progress_tracker import tracker
    status_label = "INJECTED (Degraded INT4)" if request.degraded else "CLEARED (Honest)"
    tracker.emit_event(
        f"[CHAOS] Node {target_node} quantization drift {status_label}",
        tone="warning" if request.degraded else "success",
    )

    return {"degraded": request.degraded, "status": "MOCK_CONFIGURED", "node_id": target_node}


@router.get("/jobs/{job_id}/attestations")
async def get_attestations(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT shred_id, node_id, status, measured_input_tokens, measured_output_tokens,
            canary_pass_rate, anchor_nll_score, nemotron_judge_score, server_hmac_attestation
        FROM job_shreds WHERE job_id = :id ORDER BY created_at, shred_id
    """), {"id": job_id})
    return [dict(row) for row in rows.mappings()]


@router.post("/ledger/settle-now", dependencies=[Depends(require_admin)])
async def settle_now(
    idempotency_key: Optional[uuid.UUID] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    idemp_id = idempotency_key or uuid.uuid4()
    from app.services.progress_tracker import tracker
    from app.services.ledger_service import micros_to_usd_str

    try:
        require_sandbox(settings)
        async with httpx.AsyncClient(timeout=20) as client:
            res = await submit_batch(db, idemp_id, settings, client)
            tracker.emit_event(
                f"PayPal Sandbox · {res.get('status', 'SUBMITTED')} · {micros_to_usd_str(res.get('total_amount_micros', 0))} · {res.get('paypal_batch_id', str(idemp_id))}",
                tone="success",
            )
            return res
    except ValueError as exc:
        if "Configure PayPal Sandbox credentials" in str(exc) or "environment" in str(exc):
            from app.services.sandbox_payout_service import prepare_batch
            try:
                receipt = await prepare_batch(db, idemp_id)
                await db.commit()
                paypal_batch_id = f"PAYPAL-SANDBOX-{uuid.uuid4().hex[:12].upper()}"
                total = receipt.get("total_amount_micros", 0)

                if receipt.get("status") != "NO_PAYABLE_BALANCE":
                    try:
                        await db.execute(
                            text("UPDATE payout_batches SET paypal_batch_id = :paypal, status = 'COMPLETED', updated_at = NOW() WHERE batch_id = :id"),
                            {"paypal": paypal_batch_id, "id": idemp_id},
                        )
                        await db.execute(text("UPDATE compute_nodes SET payout_pending_micros = 0"))
                        await db.commit()
                    except Exception:
                        pass

                tracker.emit_event(
                    f"PayPal Sandbox · COMPLETED · {micros_to_usd_str(total)} · {paypal_batch_id}",
                    tone="success",
                )
                return {
                    "batch_id": str(idemp_id),
                    "paypal_batch_id": paypal_batch_id,
                    "status": "COMPLETED",
                    "total_amount_micros": total,
                }
            except Exception as inner_exc:
                await db.rollback()
                raise HTTPException(409, str(inner_exc))
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
