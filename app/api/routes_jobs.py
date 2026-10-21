"""
ApexMarket: Batch Job Submission & Lifecycle API Routes
Handles batch ingestion, escrow locking, sensitivity gating, and job result querying.
"""

from datetime import datetime, timezone
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

    # 1. Acquire client escrow lock
    try:
        await LedgerService.lock_client_escrow(
            db=db,
            client_id=client_id,
            required_escrow_micros=request.max_cost_ceiling_micros,
            job_id=job_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e),
        )

    # 2. Query candidates and partition into shreds
    candidates = await scheduler.get_candidate_nodes(db=db)
    if not candidates:
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

    return BatchJobResponse(
        job_id=row.job_id,
        client_id=row.client_id,
        sensitivity=WorkloadSensitivity(row.sensitivity),
        status=JobStatus(row.status),
        total_prompts=row.total_prompts,
        max_tokens_per_prompt=row.max_tokens_per_prompt,
        max_cost_ceiling_micros=row.max_cost_ceiling_micros,
        reserved_escrow_micros=row.reserved_escrow_micros,
        actual_settled_cost_micros=row.actual_settled_cost_micros,
        platform_fee_micros=row.platform_fee_micros,
        baseline_anchor_cost_micros=row.baseline_anchor_cost_micros,
        baseline_batch_api_cost_micros=row.baseline_batch_api_cost_micros,
        total_makespan_ms=row.total_makespan_ms,
        created_at=row.created_at,
        completed_at=row.completed_at,
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
    """Retrieves reassembled prompt outputs in original index order."""
    results = orchestration_service.get_job_results(job_id)
    if results is not None:
        return results

    # Verify if job exists in database
    result = await db.execute(
        text("SELECT status FROM batch_jobs WHERE job_id = :job_id"),
        {"job_id": job_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )
    if row[0] in ("QUEUED", "RUNNING"):
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"Job {job_id} is currently {row[0]}. Results not yet finalized.",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Results for job {job_id} could not be retrieved.",
    )
