"""
ApexMarket Test Suite: Job Pipeline Against Real PostgreSQL
Runs JobOrchestrationService.execute_job end to end with a mocked OpenAI-compatible
provider and asserts multi-shred jobs complete, results come back in prompt order,
escrow is fully released, and every micro-dollar is accounted for.
Skipped unless TEST_DATABASE_URL is set (see tests/conftest.py).
"""

import json
import re
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.schemas import BatchJobCreateRequest, PromptItem, WorkloadSensitivity
from app.services.ledger_service import LedgerService
from app.services.orchestration_service import JobOrchestrationService

pytestmark = pytest.mark.asyncio

INITIAL_BALANCE = 10_000_000
CEILING = 1_000_000


class FakeProvider:
    """Streams chat completions; answers canary probes correctly so honest nodes pass."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    @staticmethod
    def answer(prompt: str) -> str:
        if m := re.search(r"sum of (\d+) and (\d+)", prompt):
            return str(int(m[1]) + int(m[2]))
        if m := re.search(r"product of (\d+) and (\d+)", prompt):
            return str(int(m[1]) * int(m[2]))
        if m := re.search(r'": (\d+)\}', prompt):
            return m[1]
        return f"answer to: {prompt}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        prompt = json.loads(request.content)["messages"][0]["content"]
        chunks = [{"choices": [{"delta": {"content": self.answer(prompt)}}]}]
        body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


async def submit_job(db, client_id, sensitivity: WorkloadSensitivity, prompt_count: int) -> tuple[uuid.UUID, BatchJobCreateRequest]:
    """Locks escrow and records the job the way POST /api/v1/jobs does."""
    request = BatchJobCreateRequest(
        sensitivity=sensitivity,
        prompts=[PromptItem(prompt_index=i, content=f"Summarise record {i}.") for i in range(prompt_count)],
        max_tokens_per_prompt=64,
        max_cost_ceiling_micros=CEILING,
    )
    job_id = uuid.uuid4()
    await LedgerService.lock_client_escrow(db, client_id, CEILING, job_id)
    await db.execute(
        text("""
            INSERT INTO batch_jobs (job_id, client_id, sensitivity, total_prompts, max_tokens_per_prompt,
                                    max_cost_ceiling_micros, reserved_escrow_micros)
            VALUES (:job_id, :client_id, :sensitivity, :count, 64, :ceiling, :ceiling)
        """),
        {"job_id": job_id, "client_id": client_id, "sensitivity": sensitivity.value, "count": prompt_count, "ceiling": CEILING},
    )
    await db.commit()
    return job_id, request


async def run_job(db, client_id, job_id, request, provider: FakeProvider):
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as http:
        return await JobOrchestrationService().execute_job(job_id, request, client_id, db, http_client=http)


async def money_snapshot(db, client_id) -> dict:
    client = (await db.execute(
        text("SELECT available_balance_micros, locked_escrow_micros FROM clients WHERE client_id = :id"), {"id": client_id}
    )).one()
    nodes = (await db.execute(
        text("SELECT COALESCE(SUM(withdrawable_micros + pending_probation_micros), 0) FROM compute_nodes")
    )).scalar_one()
    revenue = (await db.execute(
        text("SELECT COALESCE(SUM(amount_micros), 0) FROM ledger_entries WHERE credit_account = 'platform_revenue'")
    )).scalar_one()
    return {"available": client[0], "locked": client[1], "nodes": int(nodes), "platform_revenue": int(revenue)}


async def test_multi_shred_confidential_job_completes_and_conserves_money(db, make_client, make_node):
    client_id = await make_client(available_balance_micros=INITIAL_BALANCE)
    await make_node(trust_tier="ANCHOR")
    job_id, request = await submit_job(db, client_id, WorkloadSensitivity.CONFIDENTIAL, prompt_count=120)

    results = await run_job(db, client_id, job_id, request, FakeProvider())

    assert [r.prompt_index for r in results] == list(range(120))
    assert all(r.status == "COMPLETED_SPOT" for r in results)
    job = (await db.execute(text("SELECT status, results_payload FROM batch_jobs WHERE job_id = :id"), {"id": job_id})).one()
    assert job.status == "COMPLETED" and len(job.results_payload) == 120
    assert (await db.execute(
        text("SELECT COUNT(*) FROM job_shreds WHERE job_id = :id AND status = 'VERIFIED_PASS'"), {"id": job_id}
    )).scalar_one() == 3

    money = await money_snapshot(db, client_id)
    assert money["locked"] == 0
    assert money["available"] + money["nodes"] + money["platform_revenue"] == INITIAL_BALANCE


async def test_multi_shred_public_job_across_spot_and_anchor_completes(db, make_client, make_node):
    client_id = await make_client(available_balance_micros=INITIAL_BALANCE)
    await make_node(trust_tier="ANCHOR")
    await make_node(trust_tier="VERIFIED_PROVIDER")
    job_id, request = await submit_job(db, client_id, WorkloadSensitivity.PUBLIC, prompt_count=150)

    results = await run_job(db, client_id, job_id, request, FakeProvider())

    assert [r.prompt_index for r in results] == list(range(150))
    assert len({r.executing_node_id for r in results}) == 2
    money = await money_snapshot(db, client_id)
    assert money["locked"] == 0
    assert money["available"] + money["nodes"] + money["platform_revenue"] == INITIAL_BALANCE
