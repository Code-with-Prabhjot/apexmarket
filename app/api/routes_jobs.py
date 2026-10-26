"""
ApexMarket: Batch Job Submission & Lifecycle API Routes
Handles batch ingestion, escrow locking, sensitivity gating, and job result querying.
"""

from datetime import datetime, timezone
import json
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.actors.scheduler_actor import CapacityAwareScheduler
from app.database import get_db
from app.schemas import (
    BatchJobCreateRequest,
    BatchJobResponse,
    JobStatus,
    PromptResultItem,
    WorkloadSensitivity,
)
from app.services.ledger_service import LedgerService
from app.services.orchestration_service import orchestration_service

router = APIRouter(prefix="/jobs", tags=["Batch Jobs"])
scheduler = CapacityAwareScheduler()


async def get_authenticated_client(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Authenticates the client by X-API-Key.
    For local development/testing, provisions a fallback test client if none exists.
    """
    import hashlib

    key_hash = hashlib.sha256((x_api_key or "default_apex_test_key").encode("utf-8")).hexdigest()
    result = await db.execute(
        text("SELECT client_id FROM clients WHERE api_key_hash = :hash"),
        {"hash": key_hash},
    )
    row = result.fetchone()
    if row:
        return row[0]

    # Create default development client with initial balance ($100.00 = 100,000,000 micros)
    client_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO clients (
                client_id, organization_name, api_key_hash,
                available_balance_micros, hourly_spend_limit_micros
            ) VALUES (
                :client_id, 'Default Enterprise Client', :hash,
                100000000, 50000000
            )
        """),
        {"client_id": client_id, "hash": key_hash},
    )
    await db.commit()
    return client_id


@router.post(
    "",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a batch inference job",
)
async def create_batch_job(
    request: BatchJobCreateRequest,
    client_id: uuid.UUID = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingests a batch inference job:
      1. Validates inputs & enforces fail-closed CONFIDENTIAL default.
      2. Locks client escrow via PostgreSQL double-entry ledger.
      3. Partitions prompts into deterministic shreds.
      4. Persists batch_jobs and job_shreds records.
    """
    job_id = uuid.uuid4()
    total_prompts = len(request.prompts)
    escrow_locked = False

    try:
        # 1. Acquire client escrow lock
        try:
            await LedgerService.lock_client_escrow(
                db=db,
                client_id=client_id,
                required_escrow_micros=request.max_cost_ceiling_micros,
                job_id=job_id,
            )
            escrow_locked = True
        except ValueError as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=str(e),
            )

        # 2. Query candidates and partition into shreds
        candidates = await scheduler.get_candidate_nodes(db=db)
        if not candidates:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No compute nodes currently registered in the network.",
            )

        shred_assignments = scheduler.schedule_batch(
            job_id=job_id,
            total_prompts=total_prompts,
            sensitivity=request.sensitivity,
            candidates=candidates,
            makespan_sla_seconds=request.makespan_sla_seconds,
        )

        # 3. Insert batch job record
        now = datetime.now(timezone.utc)
        await db.execute(
            text("""
                INSERT INTO batch_jobs (
                    job_id, client_id, sensitivity, status,
                    total_prompts, max_tokens_per_prompt, max_cost_ceiling_micros,
                    reserved_escrow_micros, baseline_anchor_cost_micros, created_at
                ) VALUES (
                    :job_id, :client_id, :sensitivity, 'QUEUED',
                    :total_prompts, :max_tokens, :ceiling,
                    :escrow, :baseline, :created_at
                )
            """),
            {
                "job_id": job_id,
                "client_id": client_id,
                "sensitivity": request.sensitivity.value,
                "total_prompts": total_prompts,
                "max_tokens": request.max_tokens_per_prompt,
                "ceiling": request.max_cost_ceiling_micros,
                "escrow": request.max_cost_ceiling_micros,
                "baseline": request.max_cost_ceiling_micros,
                "created_at": now,
            },
        )

        # 4. Insert job shreds
        for shred in shred_assignments:
            await db.execute(
                text("""
                    INSERT INTO job_shreds (
                        shred_id, job_id, node_id, status, prompt_indices, shred_cost_micros
                    ) VALUES (
                        :shred_id, :job_id, :node_id, 'PENDING', :indices, :cost
                    )
                """),
                {
                    "shred_id": shred.shred_id,
                    "job_id": job_id,
                    "node_id": shred.node_id,
                    "indices": shred.prompt_indices,
                    "cost": shred.estimated_cost_micros,
                },
            )

        await db.commit()

        # 5. Launch asynchronous end-to-end orchestration pipeline
        await orchestration_service.create_job_task(
            job_id=job_id,
            request=request,
            client_id=client_id,
        )

        return BatchJobResponse(
            job_id=job_id,
            client_id=client_id,
            sensitivity=request.sensitivity,
            status=JobStatus.QUEUED,
            total_prompts=total_prompts,
            max_tokens_per_prompt=request.max_tokens_per_prompt,
            max_cost_ceiling_micros=request.max_cost_ceiling_micros,
            reserved_escrow_micros=request.max_cost_ceiling_micros,
            actual_settled_cost_micros=0,
            platform_fee_micros=0,
            baseline_anchor_cost_micros=request.max_cost_ceiling_micros,
            baseline_batch_api_cost_micros=int(request.max_cost_ceiling_micros * 0.75),
            created_at=now,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit batch job: {str(e)}",
        )


@router.get(
    "/{job_id}",
    response_model=BatchJobResponse,
    summary="Get batch job status",
)
async def get_batch_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieves current job status, execution progress, and financial accounting."""
    result = await db.execute(
        text("""
            SELECT job_id, client_id, sensitivity, status, total_prompts,
                   max_tokens_per_prompt, max_cost_ceiling_micros,
                   reserved_escrow_micros, actual_settled_cost_micros,
                   platform_fee_micros, baseline_anchor_cost_micros,
                   baseline_batch_api_cost_micros, total_makespan_ms,
                   created_at, completed_at
            FROM batch_jobs
            WHERE job_id = :job_id
        """),
        {"job_id": job_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )

    job_id_val = getattr(row, "job_id", None) or (row[0] if len(row) > 0 else job_id)
    client_id_val = getattr(row, "client_id", None) or (row[1] if len(row) > 1 else uuid.uuid4())

    raw_sens = getattr(row, "sensitivity", None) or (row[2] if len(row) > 2 else "CONFIDENTIAL")
    try:
        sensitivity_val = WorkloadSensitivity(raw_sens)
    except ValueError:
        sensitivity_val = WorkloadSensitivity.CONFIDENTIAL

    raw_status = getattr(row, "status", None) or (row[3] if len(row) > 3 else "QUEUED")
    try:
        status_val = JobStatus(raw_status)
    except ValueError:
        status_val = JobStatus.QUEUED

    total_prompts_val = getattr(row, "total_prompts", None) or (row[4] if len(row) > 4 else 0)
    max_tokens_val = getattr(row, "max_tokens_per_prompt", None) or (row[5] if len(row) > 5 else 512)
    ceiling_val = getattr(row, "max_cost_ceiling_micros", None) or (row[6] if len(row) > 6 else 0)
    escrow_val = getattr(row, "reserved_escrow_micros", None) or (row[7] if len(row) > 7 else ceiling_val)
    cost_val = getattr(row, "actual_settled_cost_micros", None) or (row[8] if len(row) > 8 else 0)
    fee_val = getattr(row, "platform_fee_micros", None) or (row[9] if len(row) > 9 else 0)
    baseline_val = getattr(row, "baseline_anchor_cost_micros", None) or (row[10] if len(row) > 10 else ceiling_val)
    batch_api_val = getattr(row, "baseline_batch_api_cost_micros", None) or (row[11] if len(row) > 11 else int(ceiling_val * 0.75))
    makespan_val = getattr(row, "total_makespan_ms", None) or (row[12] if len(row) > 12 else None)
    created_val = getattr(row, "created_at", None) or (row[13] if len(row) > 13 else datetime.now(timezone.utc))
    completed_val = getattr(row, "completed_at", None) or (row[14] if len(row) > 14 else None)

    return BatchJobResponse(
        job_id=job_id_val,
        client_id=client_id_val,
        sensitivity=sensitivity_val,
        status=status_val,
        total_prompts=total_prompts_val,
        max_tokens_per_prompt=max_tokens_val,
        max_cost_ceiling_micros=ceiling_val,
        reserved_escrow_micros=escrow_val,
        actual_settled_cost_micros=cost_val,
        platform_fee_micros=fee_val,
        baseline_anchor_cost_micros=baseline_val,
        baseline_batch_api_cost_micros=batch_api_val,
        total_makespan_ms=makespan_val,
        created_at=created_val,
        completed_at=completed_val,
    )


@router.get(
    "/{job_id}/results",
    response_model=List[PromptResultItem],
    summary="Get batch job prompt results",
)
async def get_batch_job_results(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieves reassembled prompt outputs in original index order from durable storage."""
    # 1. Check optional Redis cache for fast polling
    try:
        from app.database import get_redis_client
        redis = await get_redis_client()
        if redis:
            cached_json = await redis.get(f"job_results:{job_id}")
            if cached_json:
                data = json.loads(cached_json if isinstance(cached_json, str) else cached_json.decode("utf-8"))
                return [PromptResultItem(**item) for item in data]
    except Exception:
        pass

    # 2. Query durable PostgreSQL database
    result = await db.execute(
        text("SELECT status, results_payload FROM batch_jobs WHERE job_id = :job_id"),
        {"job_id": job_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )

    job_status = getattr(row, "status", None) or row[0]
    if job_status in ("QUEUED", "RUNNING"):
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"Job {job_id} is currently {job_status}. Results not yet finalized.",
        )

    raw_payload = getattr(row, "results_payload", None)
    if raw_payload is None and len(row) > 1:
        raw_payload = row[1]

    if raw_payload is not None:
        try:
            data = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
            items = [PromptResultItem(**item) for item in data]
            try:
                from app.database import get_redis_client
                redis = await get_redis_client()
                if redis:
                    await redis.set(f"job_results:{job_id}", json.dumps(data), ex=3600)
            except Exception:
                pass
            return items
        except Exception as e:
            logger.warning(f"Error deserializing results_payload for job {job_id}: {e}")
            return []

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Results for job {job_id} could not be retrieved.",
    )
