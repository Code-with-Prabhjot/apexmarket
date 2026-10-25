"""
ApexMarket: End-to-End Batch Job Orchestration Pipeline
Coordinates:
  1. Sensitivity-gated prompt scheduling (Confidential anchor routing vs. greedy spot shredding).
  2. Asynchronous shred dispatching using the canonical ShredExecutor with per-node concurrency semaphores,
     dynamic timeouts, streaming TTFT measurement, and circuit breakers.
  3. 5-Tier shred verification (Byte-level token counting, deterministic canaries, output safety).
  4. Mid-shred failover to verified Nebius anchor with retry budget = 2 for failing shreds.
  5. Deterministic prompt output reassembly in original prompt_index order.
  6. Durable job results persistence in PostgreSQL (JSONB results_payload) and optional Redis cache.
  7. Double-entry ledger settlement, escrow release, and node balance crediting.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import math
import time
from typing import Dict, List, Optional, Tuple, Any
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.actors.executor_actor import ExecNode, ShredExecutor
from app.actors.scheduler_actor import CapacityAwareScheduler, NodeCandidate, ShredAssignment
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.schemas import (
    BatchJobCreateRequest,
    JobStatus,
    NodeTrustTier,
    PromptResultItem,
    ShredStatus,
    WorkloadSensitivity,
)
from app.services.ledger_service import LedgerService
from app.services.progress_tracker import ProgressTracker, tracker as default_tracker
from app.services.verification_service import (
    CanaryProbeEngine,
    TokenizerBillingAuthority,
    VerificationService,
)

logger = logging.getLogger("apexmarket.orchestration")
settings = get_settings()


class JobOrchestrationService:
    def __init__(self):
        self.scheduler = CapacityAwareScheduler()
        self._active_tasks: Dict[uuid.UUID, asyncio.Task] = {}
        self.default_http_client: Optional[httpx.AsyncClient] = None
        self.session_factory = None
        self.default_tracker: Optional[ProgressTracker] = None

    def get_job_results(self, job_id: uuid.UUID) -> Optional[List[PromptResultItem]]:
        """Deprecated in-memory lookup. Results are persisted durably in PostgreSQL."""
        return None

    def register_task(self, job_id: uuid.UUID, task: asyncio.Task) -> None:
        self._active_tasks[job_id] = task

    async def wait_for_job(self, job_id: uuid.UUID, timeout_s: float = 30.0) -> Optional[List[PromptResultItem]]:
        """Awaits completion of the active background job task and returns reassembled results."""
        task = self._active_tasks.get(job_id)
        if task:
            return await asyncio.wait_for(asyncio.shield(task), timeout=timeout_s)
        return None

    async def _call_node(
        self,
        client: httpx.AsyncClient,
        node: ExecNode,
        prompt: str,
        max_tokens: int,
        sem: asyncio.Semaphore,
        tracker: ProgressTracker,
        timeout_s: float = 30.0,
    ) -> Tuple[str, int, int, float]:
        """Canonical call delegation using ShredExecutor."""
        ex_nodes = [node] if node.is_anchor else [node, ExecNode("anchor_fallback", node.endpoint_url, node.model_id, is_anchor=True)]
        executor = ShredExecutor(ex_nodes, client=client, timeout_s=timeout_s, tracker=tracker)
        return await executor.call_node(node, prompt, max_tokens, timeout_s=timeout_s)

    async def create_job_task(
        self,
        job_id: uuid.UUID,
        request: BatchJobCreateRequest,
        client_id: uuid.UUID,
    ) -> asyncio.Task:
        """Launches the asynchronous execution loop as a background task."""
        task = asyncio.create_task(
            self.run_job_pipeline(
                job_id=job_id,
                request=request,
                client_id=client_id,
            )
        )
        self.register_task(job_id, task)
        return task

    async def run_job_pipeline(
        self,
        job_id: uuid.UUID,
        request: BatchJobCreateRequest,
        client_id: uuid.UUID,
    ) -> List[PromptResultItem]:
        """Wrapper to manage session lifecycle for background pipeline tasks."""
        factory = self.session_factory or AsyncSessionLocal
        async with factory() as session:
            try:
                return await self.execute_job(
                    job_id=job_id,
                    request=request,
                    client_id=client_id,
                    db=session,
                    http_client=self.default_http_client,
                    tracker=self.default_tracker,
                )
            except Exception as e:
                logger.exception(f"Fatal error in background pipeline execution for job {job_id}: {e}")
                raise

    async def execute_job(
        self,
        job_id: uuid.UUID,
        request: BatchJobCreateRequest,
        client_id: uuid.UUID,
        db: AsyncSession,
        http_client: Optional[httpx.AsyncClient] = None,
        tracker: Optional[ProgressTracker] = None,
    ) -> List[PromptResultItem]:
        """
        Executes the full end-to-end job orchestration pipeline:
          1. Mark job as RUNNING.
          2. Resolve compute node topology & strictly verify ANCHOR node.
          3. Dispatch shreds asynchronously using the canonical ShredExecutor.
          4. Audit each completed shred with 5-tier verification.
             On failure, fail over prompts to verified ANCHOR with retry budget = 2.
          5. Reassemble prompt outputs in original prompt index order.
          6. Persist results durably in PostgreSQL (batch_jobs.results_payload JSONB) & optional Redis cache.
          7. Commit verified costs, release unspent escrow, credit nodes, and mark job COMPLETED.
        """
        job_start_time = time.perf_counter()
        tr = tracker or self.default_tracker or default_tracker
        tr.start_job(str(job_id), len(request.prompts))

        # 1. Update job status to RUNNING (or insert if invoked directly)
        job_check = await db.execute(
            text("SELECT job_id FROM batch_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        )
        if not job_check.fetchone():
            now = datetime.now(timezone.utc)
            await db.execute(
                text("""
                    INSERT INTO batch_jobs (
                        job_id, client_id, sensitivity, status,
                        total_prompts, max_tokens_per_prompt, max_cost_ceiling_micros,
                        reserved_escrow_micros, baseline_anchor_cost_micros, created_at
                    ) VALUES (
                        :job_id, :client_id, :sensitivity, 'RUNNING',
                        :total_prompts, :max_tokens, :ceiling,
                        :escrow, :baseline, :created_at
                    )
                """),
                {
                    "job_id": job_id,
                    "client_id": client_id,
                    "sensitivity": request.sensitivity.value,
                    "total_prompts": len(request.prompts),
                    "max_tokens": request.max_tokens_per_prompt,
                    "ceiling": request.max_cost_ceiling_micros,
                    "escrow": request.max_cost_ceiling_micros,
                    "baseline": request.max_cost_ceiling_micros,
                    "created_at": now,
                },
            )
        else:
            await db.execute(
                text("UPDATE batch_jobs SET status = 'RUNNING' WHERE job_id = :job_id"),
                {"job_id": job_id},
            )
        await db.commit()

        owns_client = False
        client = http_client or self.default_http_client
        if client is None:
            client = httpx.AsyncClient()
            owns_client = True

        try:
            # 2. Query compute nodes and identify verified ANCHOR node via enum check
            candidates = await self.scheduler.get_candidate_nodes(db=db)
            if not candidates:
                raise RuntimeError("No active compute nodes found in the network.")

            anchor_cand = next(
                (c for c in candidates if c.trust_tier == NodeTrustTier.ANCHOR),
                None,
            )
            if not anchor_cand:
                raise RuntimeError("No verified ANCHOR node found in compute registry.")

            anchor_exec = ExecNode.from_candidate(anchor_cand)
            anchor_exec.is_anchor = True

            exec_nodes: Dict[str, ExecNode] = {c.node_id: ExecNode.from_candidate(c) for c in candidates}
            exec_nodes[anchor_exec.node_id] = anchor_exec

            # Canonical ShredExecutor encapsulates semaphores, streaming HTTP calls,
            # dynamic timeouts, TTFT measurement, and circuit breaker status updates
            executor = ShredExecutor(
                nodes=list(exec_nodes.values()),
                client=client,
                timeout_s=30.0,
                breaker_threshold=3,
                tracker=tr,
            )

            # Load shreds for this job from database
            shred_rows = (
                await db.execute(
                    text("""
                        SELECT shred_id, node_id, prompt_indices, shred_cost_micros
                        FROM job_shreds
                        WHERE job_id = :job_id
                    """),
                    {"job_id": job_id},
                )
            ).fetchall()

            if not shred_rows:
                # If shreds were not pre-persisted, schedule dynamically
                assignments = self.scheduler.schedule_batch(
                    job_id=job_id,
                    total_prompts=len(request.prompts),
                    sensitivity=request.sensitivity,
                    candidates=candidates,
                    makespan_sla_seconds=request.makespan_sla_seconds,
                )
                for a in assignments:
                    await db.execute(
                        text("""
                            INSERT INTO job_shreds (shred_id, job_id, node_id, status, prompt_indices, shred_cost_micros)
                            VALUES (:shred_id, :job_id, :node_id, 'PENDING', :indices, :cost)
                        """),
                        {
                            "shred_id": a.shred_id,
                            "job_id": job_id,
                            "node_id": a.node_id,
                            "indices": a.prompt_indices,
                            "cost": a.estimated_cost_micros,
                        },
                    )
                await db.commit()
                shred_rows = (
                    await db.execute(
                        text("""
                            SELECT shred_id, node_id, prompt_indices, shred_cost_micros
                            FROM job_shreds
                            WHERE job_id = :job_id
                        """),
                        {"job_id": job_id},
                    )
                ).fetchall()

            prompt_map = {p.prompt_index: p for p in request.prompts}
            candidate_map = {c.node_id: c for c in candidates}

            # Enforce that CONFIDENTIAL workloads route strictly to verified ANCHOR nodes
            if request.sensitivity == WorkloadSensitivity.CONFIDENTIAL:
                for row in shred_rows:
                    cand = candidate_map.get(row.node_id)
                    if not cand or cand.trust_tier != NodeTrustTier.ANCHOR:
                        raise RuntimeError(
                            f"Security violation: CONFIDENTIAL job shred {row.shred_id} "
                            f"assigned to non-ANCHOR node {row.node_id} (trust_tier={getattr(cand, 'trust_tier', None)})"
                        )

            # 3 & 4. Asynchronously execute and verify each shred using canonical executor.
            # Shreds run concurrently but share one AsyncSession, which does not allow
            # concurrent use, so every database step takes db_lock while HTTP calls stay parallel.
            db_lock = asyncio.Lock()

            async def process_single_shred(shred_row) -> Tuple[List[PromptResultItem], int]:
                shred_id = shred_row.shred_id
                target_node_id = shred_row.node_id
                prompt_indices = shred_row.prompt_indices
                assigned_node = exec_nodes.get(target_node_id, anchor_exec)
                node_cand = candidate_map.get(target_node_id, anchor_cand)

                async with db_lock:
                    await db.execute(
                        text("UPDATE job_shreds SET status = 'RUNNING' WHERE shred_id = :shred_id"),
                        {"shred_id": shred_id},
                    )
                    await db.commit()

                shred_prompts = [prompt_map[idx] for idx in prompt_indices]

                # Canaries are generated for spot nodes; anchor is ground truth
                canary_specs = []
                if not assigned_node.is_anchor:
                    canary_specs = CanaryProbeEngine.generate_canaries(shred_id, count=2)

                prompt_tasks = [
                    executor.call_node(
                        node=assigned_node,
                        prompt=p.content,
                        max_tokens=request.max_tokens_per_prompt,
                        timeout_s=30.0,
                    )
                    for p in shred_prompts
                ]
                canary_tasks = [
                    executor.call_node(
                        node=assigned_node,
                        prompt=c["prompt"],
                        max_tokens=64,
                        timeout_s=30.0,
                    )
                    for c in canary_specs
                ]

                all_raw = await asyncio.gather(*prompt_tasks, *canary_tasks, return_exceptions=True)
                prompt_raw = all_raw[: len(shred_prompts)]
                canary_raw = all_raw[len(shred_prompts) :]

                transport_error = any(isinstance(r, Exception) for r in all_raw)
                attestation = None
                canary_evals: List[Tuple[bool, str]] = []

                if not transport_error:
                    for spec, res in zip(canary_specs, canary_raw):
                        text_val, _, _, _ = res
                        is_valid = CanaryProbeEngine.verify_canary_output(text_val, spec["expected"])
                        canary_evals.append((is_valid, "ok" if is_valid else f"Expected {spec['expected']} got {text_val}"))

                    prompt_outputs = [r[0] for r in prompt_raw]
                    prompt_inputs = [p.content for p in shred_prompts]

                    attestation = VerificationService.audit_shred(
                        shred_id=shred_id,
                        node_id=assigned_node.node_id,
                        canary_results=canary_evals,
                        outputs=prompt_outputs,
                        input_prompts=prompt_inputs,
                    )

                shred_passed = (not transport_error) and attestation is not None and attestation.passed

                # PASS CASE: Spot or Anchor execution verified successfully
                if shred_passed:
                    total_in = sum(TokenizerBillingAuthority.count_tokens(p.content) for p in shred_prompts)
                    total_out = sum(TokenizerBillingAuthority.count_tokens(r[0]) for r in prompt_raw)
                    shred_cost = math.ceil(
                        total_in * assigned_node.input_price_per_1m_micros / 1e6
                        + total_out * assigned_node.output_price_per_1m_micros / 1e6
                    )

                    is_probation = (node_cand.trust_tier == NodeTrustTier.PROBATION_SPOT)
                    async with db_lock:
                        await db.execute(
                            text("""
                                UPDATE job_shreds
                                SET status = :status,
                                    measured_input_tokens = :in_tok,
                                    measured_output_tokens = :out_tok,
                                    shred_cost_micros = :cost,
                                    canary_pass_rate = :pass_rate,
                                    server_hmac_attestation = :att
                                WHERE shred_id = :shred_id
                            """),
                            {
                                "status": ShredStatus.VERIFIED_PASS.value,
                                "in_tok": total_in,
                                "out_tok": total_out,
                                "cost": shred_cost,
                                "pass_rate": attestation.canary_accuracy,
                                "att": attestation.server_hmac_signature,
                                "shred_id": shred_id,
                            },
                        )

                        # Credit verified node balance
                        await LedgerService.credit_node_verified_shred(
                            db=db,
                            client_id=client_id,
                            job_id=job_id,
                            shred_id=shred_id,
                            node_id=assigned_node.node_id,
                            shred_cost_micros=shred_cost,
                            is_probation=is_probation,
                        )
                        await db.commit()

                    items: List[PromptResultItem] = []
                    for p, res in zip(shred_prompts, prompt_raw):
                        text_val = res[0]
                        in_t = TokenizerBillingAuthority.count_tokens(p.content)
                        out_t = TokenizerBillingAuthority.count_tokens(text_val)
                        tr.advance(str(job_id))
                        items.append(
                            PromptResultItem(
                                prompt_index=p.prompt_index,
                                status="COMPLETED_SPOT",
                                executing_node_id=assigned_node.node_id,
                                output_text=text_val,
                                input_tokens=in_t,
                                output_tokens=out_t,
                            )
                        )
                    return items, shred_cost

                # FAIL CASE: Mark shred failed and fail over to verified anchor with retry budget = 2
                logger.warning(
                    f"Shred {shred_id} failed on node {assigned_node.node_id} (transport={transport_error}). "
                    f"Failing over {len(shred_prompts)} prompts to verified anchor node {anchor_exec.node_id}."
                )

                pass_rate = attestation.canary_accuracy if attestation else 0.0
                att_sig = attestation.server_hmac_signature if attestation else None

                async with db_lock:
                    await db.execute(
                        text("""
                            UPDATE job_shreds
                            SET status = :status,
                                canary_pass_rate = :pass_rate,
                                server_hmac_attestation = :att,
                                retry_count = retry_count + 1
                            WHERE shred_id = :shred_id
                        """),
                        {
                            "status": ShredStatus.VERIFIED_FAIL_REROUTED.value,
                            "pass_rate": pass_rate,
                            "att": att_sig,
                            "shred_id": shred_id,
                        },
                    )
                    await db.commit()

                # Fail over unverified prompts to verified anchor (retry budget = 2)
                failover_items: List[PromptResultItem] = []
                anchor_failover_cost = 0

                for p in shred_prompts:
                    anchor_res = None
                    retries_left = 2
                    while retries_left >= 0:
                        try:
                            anchor_res = await executor.call_node(
                                node=anchor_exec,
                                prompt=p.content,
                                max_tokens=request.max_tokens_per_prompt,
                                timeout_s=30.0,
                            )
                            tr.advance(str(job_id), failover=True)
                            break
                        except Exception as e:
                            retries_left -= 1
                            if retries_left < 0:
                                logger.error(f"Anchor failover retry budget exhausted for prompt {p.prompt_index}: {e}")

                    if anchor_res is not None:
                        text_val = anchor_res[0]
                        in_t = TokenizerBillingAuthority.count_tokens(p.content)
                        out_t = TokenizerBillingAuthority.count_tokens(text_val)
                        cost = math.ceil(
                            in_t * anchor_exec.input_price_per_1m_micros / 1e6
                            + out_t * anchor_exec.output_price_per_1m_micros / 1e6
                        )
                        anchor_failover_cost += cost
                        failover_items.append(
                            PromptResultItem(
                                prompt_index=p.prompt_index,
                                status="COMPLETED_ANCHOR_FAILOVER",
                                executing_node_id=anchor_exec.node_id,
                                output_text=text_val,
                                input_tokens=in_t,
                                output_tokens=out_t,
                            )
                        )
                    else:
                        failover_items.append(
                            PromptResultItem(
                                prompt_index=p.prompt_index,
                                status="FAILED",
                                executing_node_id=anchor_exec.node_id,
                                output_text="",
                                input_tokens=0,
                                output_tokens=0,
                            )
                        )

                # Credit anchor node for the failover prompts
                if anchor_failover_cost > 0:
                    async with db_lock:
                        await LedgerService.credit_node_verified_shred(
                            db=db,
                            client_id=client_id,
                            job_id=job_id,
                            shred_id=shred_id,
                            node_id=anchor_exec.node_id,
                            shred_cost_micros=anchor_failover_cost,
                            is_probation=False,
                        )
                        await db.commit()

                return failover_items, anchor_failover_cost

            # Execute all shreds concurrently. Wait for every shred before raising so the
            # abort cleanup below never runs while another shred is still using the session.
            shred_tasks = [process_single_shred(row) for row in shred_rows]
            shred_outputs = await asyncio.gather(*shred_tasks, return_exceptions=True)
            shred_errors = [o for o in shred_outputs if isinstance(o, BaseException)]
            if shred_errors:
                raise shred_errors[0]

            # 5. Reassemble prompt outputs in original prompt_index order
            all_prompt_results: List[PromptResultItem] = []
            total_settled_cost_micros = 0
            for items, cost in shred_outputs:
                all_prompt_results.extend(items)
                total_settled_cost_micros += cost

            reassembled = sorted(all_prompt_results, key=lambda item: item.prompt_index)
            results_payload = [item.model_dump() for item in reassembled]
            results_payload_json = json.dumps(results_payload)

            # Optional Redis cache for fast polling
            try:
                from app.database import get_redis_client
                redis = await get_redis_client()
                if redis:
                    await redis.set(f"job_results:{job_id}", results_payload_json, ex=3600)
            except Exception:
                pass

            # 6. Settle ledger & release unspent escrow
            job_row = (
                await db.execute(
                    text("SELECT reserved_escrow_micros, baseline_anchor_cost_micros FROM batch_jobs WHERE job_id = :job_id"),
                    {"job_id": job_id},
                )
            ).fetchone()

            reserved_micros = job_row.reserved_escrow_micros if job_row else request.max_cost_ceiling_micros
            baseline_micros = job_row.baseline_anchor_cost_micros if job_row else request.max_cost_ceiling_micros

            settlement_report = await LedgerService.release_unused_escrow_and_settle_job(
                db=db,
                client_id=client_id,
                job_id=job_id,
                total_reserved_micros=reserved_micros,
                actual_settled_micros=total_settled_cost_micros,
                baseline_cost_micros=baseline_micros,
            )

            makespan_ms = (time.perf_counter() - job_start_time) * 1000.0
            has_failed_prompts = any(p.status == "FAILED" for p in reassembled)
            final_status = JobStatus.PARTIAL_FAIL if has_failed_prompts else JobStatus.COMPLETED

            # Persist durable results payload in PostgreSQL batch_jobs
            await db.execute(
                text("""
                    UPDATE batch_jobs
                    SET status = :status,
                        actual_settled_cost_micros = :cost,
                        platform_fee_micros = :fee,
                        total_makespan_ms = :makespan,
                        completed_at = :completed_at,
                        results_payload = :results_payload
                    WHERE job_id = :job_id
                """),
                {
                    "status": final_status.value,
                    "cost": total_settled_cost_micros,
                    "fee": settlement_report["platform_fee_micros"],
                    "makespan": makespan_ms,
                    "completed_at": datetime.now(timezone.utc),
                    "results_payload": results_payload_json,
                    "job_id": job_id,
                },
            )
            await db.commit()
            return reassembled

        except Exception as e:
            logger.exception(f"Job {job_id} encountered fatal pipeline error: {e}")
            await db.rollback()
            try:
                job_row = (
                    await db.execute(
                        text("SELECT reserved_escrow_micros, baseline_anchor_cost_micros FROM batch_jobs WHERE job_id = :job_id"),
                        {"job_id": job_id},
                    )
                ).fetchone()
                if job_row:
                    await LedgerService.release_unused_escrow_and_settle_job(
                        db=db,
                        client_id=client_id,
                        job_id=job_id,
                        total_reserved_micros=job_row.reserved_escrow_micros,
                        actual_settled_micros=0,
                        baseline_cost_micros=job_row.baseline_anchor_cost_micros,
                    )
                await db.execute(
                    text("""
                        UPDATE batch_jobs
                        SET status = 'ABORTED_BUDGET',
                            completed_at = :now,
                            results_payload = '[]'
                        WHERE job_id = :job_id
                    """),
                    {"now": datetime.now(timezone.utc), "job_id": job_id},
                )
                await db.commit()
            except Exception as cleanup_err:
                logger.error(f"Failed to release escrow during abort cleanup: {cleanup_err}")
            raise
        finally:
            if owns_client:
                await client.aclose()


orchestration_service = JobOrchestrationService()
