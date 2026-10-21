"""
ApexMarket: End-to-End Batch Job Orchestration Pipeline
Coordinates:
  1. Sensitivity-gated prompt scheduling (Confidential anchor routing vs. greedy spot shredding).
  2. Asynchronous shred dispatching with per-node semaphore concurrency guards.
  3. 5-Tier shred verification (Byte-level token counting, deterministic canaries, output safety).
  4. Mid-shred failover to Nebius anchor with retry budget = 2 for failing shreds.
  5. Deterministic prompt output reassembly in original prompt_index order.
  6. Double-entry ledger settlement, escrow release, and node balance crediting.
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

from app.actors.executor_actor import ExecNode
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
        self._job_results: Dict[uuid.UUID, List[PromptResultItem]] = {}
        self._active_tasks: Dict[uuid.UUID, asyncio.Task] = {}
        self.default_http_client: Optional[httpx.AsyncClient] = None
        self.session_factory = None
        self.default_tracker: Optional[ProgressTracker] = None

    def get_job_results(self, job_id: uuid.UUID) -> Optional[List[PromptResultItem]]:
        return self._job_results.get(job_id)

    def set_job_results(self, job_id: uuid.UUID, results: List[PromptResultItem]) -> None:
        self._job_results[job_id] = results

    def register_task(self, job_id: uuid.UUID, task: asyncio.Task) -> None:
        self._active_tasks[job_id] = task

    async def wait_for_job(self, job_id: uuid.UUID, timeout_s: float = 30.0) -> Optional[List[PromptResultItem]]:
        task = self._active_tasks.get(job_id)
        if task:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout_s)
        return self.get_job_results(job_id)

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
        """Calls node completions API with streaming, TTFT measurement, and concurrency guards."""
        headers = {"Authorization": f"Bearer {node.api_key}"} if node.api_key else {}
        body = {
            "model": node.model_id,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": prompt}],
        }
        url = f"{node.endpoint_url.rstrip('/')}/chat/completions"
        parts: List[str] = []
        usage = None
        ttft = 0.0
        t0 = time.perf_counter()

        async with sem:
            tracker.inflight(node.node_id, +1)
            try:
                async with client.stream("POST", url, json=body, headers=headers, timeout=timeout_s) as r:
                    if r.status_code != 200:
                        raise RuntimeError(f"HTTP {r.status_code}")
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        for ch in chunk.get("choices", []):
                            piece = (ch.get("delta") or {}).get("content")
                            if piece:
                                if not parts:
                                    ttft = (time.perf_counter() - t0) * 1000.0
                                parts.append(piece)
                tracker.record(node.node_id, ttft, True)
            except Exception:
                tracker.record(node.node_id, None, False)
                raise
            finally:
                tracker.inflight(node.node_id, -1)

        text_out = "".join(parts)
        if not text_out:
            raise RuntimeError("empty response from node")

        in_tok = (usage or {}).get("prompt_tokens") or TokenizerBillingAuthority.count_tokens(prompt)
        out_tok = (usage or {}).get("completion_tokens") or TokenizerBillingAuthority.count_tokens(text_out)
        return text_out, in_tok, out_tok, ttft

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
          2. Resolve compute node topology & anchor node.
          3. Dispatch shreds asynchronously to candidate nodes.
          4. Audit each completed shred with 5-tier verification.
             On failure, fail over prompts to Nebius anchor with retry budget = 2.
          5. Reassemble prompt outputs in original prompt index order.
          6. Commit verified costs, release unspent escrow, credit nodes, and mark job COMPLETED.
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
            # 2. Query compute nodes and identify Nebius anchor
            candidates = await self.scheduler.get_candidate_nodes(db=db)
            if not candidates:
                raise RuntimeError("No active compute nodes found in the network.")

            anchor_cand = next(
                (
                    c for c in candidates
                    if c.trust_tier == NodeTrustTier.ANCHOR
                    or "anchor" in c.node_id.lower()
                    or "nebius" in c.provider_name.lower()
                ),
                candidates[0],
            )
            anchor_exec = ExecNode.from_candidate(anchor_cand)
            anchor_exec.is_anchor = True

            exec_nodes: Dict[str, ExecNode] = {c.node_id: ExecNode.from_candidate(c) for c in candidates}
            exec_nodes[anchor_exec.node_id] = anchor_exec

            sems = {nid: asyncio.Semaphore(max(1, node.max_concurrent)) for nid, node in exec_nodes.items()}

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

            # 3 & 4. Asynchronously execute and verify each shred
            async def process_single_shred(shred_row) -> Tuple[List[PromptResultItem], int]:
                shred_id = shred_row.shred_id
                target_node_id = shred_row.node_id
                prompt_indices = shred_row.prompt_indices
                assigned_node = exec_nodes.get(target_node_id, anchor_exec)
                node_cand = candidate_map.get(target_node_id, anchor_cand)

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
                    self._call_node(
                        client=client,
                        node=assigned_node,
                        prompt=p.content,
                        max_tokens=request.max_tokens_per_prompt,
                        sem=sems[assigned_node.node_id],
                        tracker=tr,
                    )
                    for p in shred_prompts
                ]
                canary_tasks = [
                    self._call_node(
                        client=client,
                        node=assigned_node,
                        prompt=c["prompt"],
                        max_tokens=64,
                        sem=sems[assigned_node.node_id],
                        tracker=tr,
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
                    is_probation = (node_cand.trust_tier == NodeTrustTier.PROBATION_SPOT)
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

                # FAIL CASE: Mark shred failed and fail over to Nebius anchor with retry budget = 2
                logger.warning(
                    f"Shred {shred_id} failed on node {assigned_node.node_id} (transport={transport_error}). "
                    f"Failing over {len(shred_prompts)} prompts to Nebius anchor."
                )

                pass_rate = attestation.canary_accuracy if attestation else 0.0
                att_sig = attestation.server_hmac_signature if attestation else None

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

                # Fail over unverified prompts to Nebius anchor (retry budget = 2)
                failover_items: List[PromptResultItem] = []
                anchor_failover_cost = 0

                for p in shred_prompts:
                    anchor_res = None
                    retries_left = 2
                    while retries_left >= 0:
                        try:
                            anchor_res = await self._call_node(
                                client=client,
                                node=anchor_exec,
                                prompt=p.content,
                                max_tokens=request.max_tokens_per_prompt,
                                sem=sems[anchor_exec.node_id],
                                tracker=tr,
                            )
                            tr.advance(str(job_id), failover=True)
                            break
                        except Exception as e:
                            retries_left -= 1
                            if retries_left < 0:
                                logger.error(f"Nebius anchor failover retry budget exhausted for prompt {p.prompt_index}: {e}")

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

            # Execute all shreds concurrently
            shred_tasks = [process_single_shred(row) for row in shred_rows]
            shred_outputs = await asyncio.gather(*shred_tasks)

            # 5. Reassemble prompt outputs in original prompt_index order
            all_prompt_results: List[PromptResultItem] = []
            total_settled_cost_micros = 0
            for items, cost in shred_outputs:
                all_prompt_results.extend(items)
                total_settled_cost_micros += cost

            reassembled = sorted(all_prompt_results, key=lambda item: item.prompt_index)
            self.set_job_results(job_id, reassembled)

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

            await db.execute(
                text("""
                    UPDATE batch_jobs
                    SET status = :status,
                        actual_settled_cost_micros = :cost,
                        platform_fee_micros = :fee,
                        total_makespan_ms = :makespan,
                        completed_at = :completed_at
                    WHERE job_id = :job_id
                """),
                {
                    "status": final_status.value,
                    "cost": total_settled_cost_micros,
                    "fee": settlement_report["platform_fee_micros"],
                    "makespan": makespan_ms,
                    "completed_at": datetime.now(timezone.utc),
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
                    text("UPDATE batch_jobs SET status = 'ABORTED_BUDGET', completed_at = :now WHERE job_id = :job_id"),
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
