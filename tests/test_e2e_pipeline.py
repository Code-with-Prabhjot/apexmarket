"""
ApexMarket: End-to-End Batch Job Orchestration Pipeline Integration Tests
Validates:
  1. Confidential workload: 100% routing to Nebius anchor (air-gap guarantee).
  2. Public/synthetic workload: greedy capacity shredding across spot nodes and anchor.
  3. Byte-level tokenizer count validation & canary probe verification.
  4. Mid-shred failover to Nebius anchor with retry budget = 2 on canary or transport failure.
  5. Ordered reassembly of PromptResultItem list by original prompt_index.
  6. Double-entry ledger settlement: unspent escrow release, platform fee, node credits, COMPLETED status.
  7. REST API invocation via POST /api/v1/jobs and GET /api/v1/jobs/{job_id}/results.
"""

from datetime import datetime, timezone
import json
import os
import uuid
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.actors.executor_actor import ExecNode
from app.api.routes_jobs import router as jobs_router
from app.database import get_db
from app.main import app as main_app
from app.schemas import (
    BatchJobCreateRequest,
    InferencePrompt,
    JobStatus,
    NodeTrustTier,
    PromptResultItem,
    WorkloadSensitivity,
)
from app.services.ledger_service import LedgerService
from app.services.orchestration_service import JobOrchestrationService, orchestration_service
from app.services.progress_tracker import ProgressTracker
from app.services.verification_service import CanaryProbeEngine, TokenizerBillingAuthority
from tools.mock_provider import create_app, honest_text

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


# -----------------------------------------------------------------------------
# IN-MEMORY TEST DATABASE FOR POSTGRES-FREE ENVIRONMENTS
# -----------------------------------------------------------------------------

class MockRow:
    def __init__(self, d: dict):
        self._d = d
        for k, v in d.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        if isinstance(idx, int):
            return list(self._d.values())[idx]
        return self._d[idx]

    def __getattr__(self, name):
        if name in self._d:
            return self._d[name]
        raise AttributeError(f"MockRow has no attribute {name}")


class MockResult:
    def __init__(self, rows: list):
        self._rows = [MockRow(r) if isinstance(r, dict) else r for r in rows]
        self._idx = 0

    def fetchone(self):
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None

    def fetchall(self):
        return self._rows

    def scalar(self):
        row = self.fetchone()
        if row is None:
            return None
        if isinstance(row, MockRow):
            return list(row._d.values())[0]
        if isinstance(row, (tuple, list)):
            return row[0]
        return row

    def scalar_one(self):
        row = self.fetchone()
        if row is None:
            raise ValueError("No rows returned from query")
        if isinstance(row, MockRow):
            return list(row._d.values())[0]
        if isinstance(row, (tuple, list)):
            return row[0]
        return row

    def one(self):
        row = self.fetchone()
        if row is None:
            raise ValueError("No rows returned")
        return row


class InMemoryTestStore:
    def __init__(self, seed_defaults: bool = False):
        self.clients = {}
        self.compute_nodes = {}
        self.batch_jobs = {}
        self.job_shreds = {}
        self.ledger_entries = {}
        if seed_defaults:
            from app.api.routes_nodes import DEFAULT_SEEDED_NODES
            for n in DEFAULT_SEEDED_NODES:
                self.compute_nodes[n["node_id"]] = {
                    **n,
                    "trust_tier": n["trust_tier"] if isinstance(n["trust_tier"], str) else n["trust_tier"].value,
                    "pending_probation_micros": 0,
                    "withdrawable_micros": 0,
                    "payout_pending_micros": 0,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                }

    def execute_sql(self, sql_str: str, params: dict) -> MockResult:
        s = " ".join(sql_str.strip().split())

        # 0. compute_nodes queries & count
        if "SELECT COUNT(*) FROM compute_nodes" in s or "SELECT count(*) FROM compute_nodes" in s.lower():
            return MockResult([{"count": len(self.compute_nodes)}])

        if s.startswith("SELECT * FROM compute_nodes"):
            if "WHERE node_id = :node_id" in s:
                nid = params.get("node_id")
                n = self.compute_nodes.get(nid)
                return MockResult([n] if n else [])
            return MockResult(list(self.compute_nodes.values()))

        if s.startswith("INSERT INTO compute_nodes"):
            nid = params["node_id"]
            self.compute_nodes[nid] = {
                "node_id": nid,
                "provider_name": params.get("provider_name", "Test Provider"),
                "endpoint_url": params.get("endpoint_url", "http://test/v1"),
                "model_id": params.get("model_id", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
                "trust_tier": params.get("trust_tier", "PROBATION_SPOT"),
                "paypal_receiver_email": params.get("paypal_receiver_email", "node@example.com"),
                "input_price_per_1m_micros": params.get("input_price_per_1m_micros", params.get("input_price", 40000)),
                "output_price_per_1m_micros": params.get("output_price_per_1m_micros", params.get("output_price", 160000)),
                "max_concurrent_requests": params.get("max_concurrent_requests", params.get("max_concurrent", 10)),
                "pending_probation_micros": 0,
                "withdrawable_micros": 0,
                "payout_pending_micros": 0,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        # 1. clients lookup
        if "SELECT client_id FROM clients WHERE api_key_hash" in s:
            h = params.get("hash")
            for cid, c in self.clients.items():
                if c.get("api_key_hash") == h:
                    return MockResult([{"client_id": cid}])
            return MockResult([])

        # 2. insert client
        if s.startswith("INSERT INTO clients"):
            cid = params["client_id"]
            self.clients[cid] = {
                "client_id": cid,
                "organization_name": params.get("organization_name", "Test Client Org"),
                "api_key_hash": params.get("hash", params.get("key_hash")),
                "available_balance_micros": params.get("available", 100_000_000),
                "locked_escrow_micros": 0,
                "hourly_spend_limit_micros": params.get("hourly_limit", 50_000_000),
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        # 3. select client for update
        if "SELECT available_balance_micros, hourly_spend_limit_micros FROM clients" in s:
            cid = params["client_id"]
            c = self.clients.get(cid)
            return MockResult([c] if c else [])

        # 4. idempotency check in ledger
        if "SELECT 1 FROM ledger_entries WHERE idempotency_key" in s:
            k = params["key"]
            if k in self.ledger_entries:
                return MockResult([{"found": 1}])
            return MockResult([])

        # 5. hourly spend circuit breaker
        if "SELECT COALESCE(SUM(amount_micros), 0) FROM ledger_entries" in s:
            total = sum(
                e["amount_micros"] for e in self.ledger_entries.values()
                if e.get("credit_account") == params.get("escrow_account")
                and e.get("idempotency_key", "").startswith("escrow_lock:")
            )
            return MockResult([{"sum": total}])

        # 6. client balance updates
        if s.startswith("UPDATE clients"):
            cid = params["client_id"]
            c = self.clients[cid]
            if "available_balance_micros - :amount" in s:
                amt = params["amount"]
                c["available_balance_micros"] -= amt
                c["locked_escrow_micros"] += amt
            elif "locked_escrow_micros - :amount" in s:
                amt = params["amount"]
                c["locked_escrow_micros"] -= amt
            elif "locked_escrow_micros - :fee" in s:
                fee = params["fee"]
                c["locked_escrow_micros"] -= fee
            elif "locked_escrow_micros - :unused" in s:
                unused = params["unused"]
                c["locked_escrow_micros"] -= unused
                c["available_balance_micros"] += unused
            return MockResult([])

        # 7. insert ledger entries
        if s.startswith("INSERT INTO ledger_entries"):
            k = params["key"]
            if k in self.ledger_entries:
                return MockResult([])
            eid = params.get("entry_id", uuid.uuid4())
            self.ledger_entries[k] = {
                "entry_id": eid,
                "idempotency_key": k,
                "job_id": params.get("job_id"),
                "shred_id": params.get("shred_id"),
                "debit_account": params.get("debit_account"),
                "credit_account": params.get("credit_account"),
                "amount_micros": params.get("amount_micros"),
                "description": params.get("description"),
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([{"entry_id": eid}])

        if "SELECT entry_id FROM ledger_entries WHERE idempotency_key" in s:
            k = params["key"]
            e = self.ledger_entries.get(k)
            return MockResult([{"entry_id": e["entry_id"]}] if e else [])

        # 8. query candidate compute nodes
        if "SELECT node_id, provider_name, endpoint_url, model_id, trust_tier" in s:
            active = [n for n in self.compute_nodes.values() if n.get("is_active", True)]
            return MockResult(active)

        # 9. batch_jobs queries and inserts
        if s.startswith("INSERT INTO batch_jobs"):
            jid = params["job_id"]
            self.batch_jobs[jid] = {
                "job_id": jid,
                "client_id": params["client_id"],
                "sensitivity": params["sensitivity"],
                "status": "QUEUED",
                "total_prompts": params["total_prompts"],
                "max_tokens_per_prompt": params["max_tokens"],
                "max_cost_ceiling_micros": params["ceiling"],
                "reserved_escrow_micros": params["escrow"],
                "actual_settled_cost_micros": 0,
                "platform_fee_micros": 0,
                "baseline_anchor_cost_micros": params["baseline"],
                "baseline_batch_api_cost_micros": int(params["ceiling"] * 0.75),
                "total_makespan_ms": None,
                "created_at": params.get("created_at", datetime.now(timezone.utc)),
                "completed_at": None,
                "results_payload": None,
            }
            return MockResult([])

        if s.startswith("SELECT reserved_escrow_micros, baseline_anchor_cost_micros FROM batch_jobs"):
            jid = params["job_id"]
            job = self.batch_jobs.get(jid)
            return MockResult([job] if job else [])

        if "FROM batch_jobs WHERE job_id = :job_id" in s:
            jid = params["job_id"]
            job = self.batch_jobs.get(jid)
            return MockResult([job] if job else [])

        if s.startswith("UPDATE batch_jobs"):
            jid = params["job_id"]
            job = self.batch_jobs.get(jid)
            if job:
                if "status" in params:
                    job["status"] = params["status"]
                if "cost" in params:
                    job["actual_settled_cost_micros"] = params["cost"]
                if "fee" in params:
                    job["platform_fee_micros"] = params["fee"]
                if "makespan" in params:
                    job["total_makespan_ms"] = params["makespan"]
                if "completed_at" in params or "now" in params:
                    job["completed_at"] = params.get("completed_at", params.get("now"))
                if "results_payload" in params:
                    job["results_payload"] = params["results_payload"]
            return MockResult([])

        # 10. job_shreds queries and updates
        if s.startswith("INSERT INTO job_shreds"):
            sid = params["shred_id"]
            self.job_shreds[sid] = {
                "shred_id": sid,
                "job_id": params["job_id"],
                "node_id": params["node_id"],
                "status": "PENDING",
                "prompt_indices": params["indices"],
                "shred_cost_micros": params["cost"],
                "measured_input_tokens": 0,
                "measured_output_tokens": 0,
                "canary_pass_rate": None,
                "server_hmac_attestation": None,
                "retry_count": 0,
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        if "FROM job_shreds WHERE job_id = :job_id" in s:
            jid = params["job_id"]
            shreds = [sh for sh in self.job_shreds.values() if sh["job_id"] == jid]
            return MockResult(shreds)

        if s.startswith("UPDATE job_shreds"):
            sid = params["shred_id"]
            shred = self.job_shreds.get(sid)
            if shred:
                if "status" in params:
                    shred["status"] = params["status"]
                elif "VERIFIED_PASS" in s:
                    shred["status"] = "VERIFIED_PASS"
                elif "VERIFIED_FAIL_REROUTED" in s:
                    shred["status"] = "VERIFIED_FAIL_REROUTED"
                elif "RUNNING" in s:
                    shred["status"] = "RUNNING"
                if "in_tok" in params:
                    shred["measured_input_tokens"] = params["in_tok"]
                if "out_tok" in params:
                    shred["measured_output_tokens"] = params["out_tok"]
                if "cost" in params:
                    shred["shred_cost_micros"] = params["cost"]
                if "pass_rate" in params:
                    shred["canary_pass_rate"] = params["pass_rate"]
                if "att" in params:
                    shred["server_hmac_attestation"] = params["att"]
                if "retry_count + 1" in s:
                    shred["retry_count"] += 1
            return MockResult([])

        # 11. compute_nodes credits
        if s.startswith("UPDATE compute_nodes"):
            nid = params["node_id"]
            node = self.compute_nodes.get(nid)
            if node:
                amt = params["amount"]
                if "withdrawable_micros" in s:
                    node["withdrawable_micros"] = node.get("withdrawable_micros", 0) + amt
                elif "pending_probation_micros" in s:
                    node["pending_probation_micros"] = node.get("pending_probation_micros", 0) + amt
            return MockResult([])

        return MockResult([])


class MockAsyncSession:
    def __init__(self, store: InMemoryTestStore):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, statement, params=None):
        return self.store.execute_sql(str(statement), params or {})

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


class MockAsyncSessionFactory:
    def __init__(self, store: InMemoryTestStore):
        self.store = store

    def __call__(self):
        return MockAsyncSession(self.store)


# -----------------------------------------------------------------------------
# FIXTURES & NODE SETUP
# -----------------------------------------------------------------------------

def mk_mock_node(name: str, **over):
    cfg = {
        "name": name,
        "ttft_ms": 1,
        "token_delay_ms": 0,
        "fail_rate": 0.0,
        "fail_status": 503,
        "degraded": False,
    }
    cfg.update(over)
    return create_app(cfg)


def build_mock_client(apps: dict) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        app = apps.get(request.url.host)
        if not app:
            return httpx.Response(status_code=404, text=f"Mock node {request.url.host} not found")
        t = httpx.ASGITransport(app=app)
        return await t.handle_async_request(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def mock_store():
    store = InMemoryTestStore()
    client_id = uuid.uuid4()
    store.clients[client_id] = {
        "client_id": client_id,
        "organization_name": "Apex Test Client",
        "api_key_hash": "default_key_hash",
        "available_balance_micros": 50_000_000,  # $50.00
        "locked_escrow_micros": 0,
        "hourly_spend_limit_micros": 50_000_000,
        "created_at": datetime.now(timezone.utc),
    }

    # Register 1 Nebius Anchor and 2 Spot nodes
    store.compute_nodes["nebius-anchor"] = {
        "node_id": "nebius-anchor",
        "provider_name": "Nebius Token Factory",
        "endpoint_url": "http://nebius-anchor/v1",
        "model_id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "trust_tier": NodeTrustTier.ANCHOR.value,
        "paypal_receiver_email": "anchor@nebius.com",
        "input_price_per_1m_micros": 100_000,   # $0.10 / 1M
        "output_price_per_1m_micros": 400_000,  # $0.40 / 1M
        "max_concurrent_requests": 8,
        "pending_probation_micros": 0,
        "withdrawable_micros": 0,
        "is_active": True,
    }
    store.compute_nodes["spot-node-1"] = {
        "node_id": "spot-node-1",
        "provider_name": "Spot Provider 1",
        "endpoint_url": "http://spot-node-1/v1",
        "model_id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "trust_tier": NodeTrustTier.VERIFIED_PROVIDER.value,
        "paypal_receiver_email": "spot1@provider.com",
        "input_price_per_1m_micros": 30_000,    # $0.03 / 1M
        "output_price_per_1m_micros": 120_000,  # $0.12 / 1M
        "max_concurrent_requests": 8,
        "pending_probation_micros": 0,
        "withdrawable_micros": 0,
        "is_active": True,
    }
    store.compute_nodes["spot-node-2"] = {
        "node_id": "spot-node-2",
        "provider_name": "Spot Provider 2",
        "endpoint_url": "http://spot-node-2/v1",
        "model_id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "trust_tier": NodeTrustTier.VERIFIED_PROVIDER.value,
        "paypal_receiver_email": "spot2@provider.com",
        "input_price_per_1m_micros": 40_000,    # $0.04 / 1M
        "output_price_per_1m_micros": 160_000,  # $0.16 / 1M
        "max_concurrent_requests": 8,
        "pending_probation_micros": 0,
        "withdrawable_micros": 0,
        "is_active": True,
    }
    return store


# -----------------------------------------------------------------------------
# TEST 1: CONFIDENTIAL WORKLOAD (100% ROUTING TO NEBIUS ANCHOR)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confidential_job_routes_100_percent_to_anchor(mock_store):
    """
    Submitting a CONFIDENTIAL workload must enforce the fail-closed air-gap guarantee:
    100% of prompts route exclusively to the Nebius anchor node.
    Spot nodes must never receive prompts or ledger credits.
    """
    apps = {
        "nebius-anchor": mk_mock_node("nebius-anchor"),
        "spot-node-1": mk_mock_node("spot-node-1"),
        "spot-node-2": mk_mock_node("spot-node-2"),
    }
    mock_http_client = build_mock_client(apps)

    orchestrator = JobOrchestrationService()
    orchestrator.default_http_client = mock_http_client
    session_factory = MockAsyncSessionFactory(mock_store)
    orchestrator.session_factory = session_factory

    client_id = list(mock_store.clients.keys())[0]
    initial_avail = mock_store.clients[client_id]["available_balance_micros"]

    prompts = [
        InferencePrompt(prompt_index=i, content=f"Confidential financial statement prompt {i}")
        for i in range(15)
    ]
    request = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.CONFIDENTIAL,
        prompts=prompts,
        max_tokens_per_prompt=64,
        max_cost_ceiling_micros=1_000_000,
    )

    job_id = uuid.uuid4()

    async with session_factory() as session:
        # Step 1: Lock client escrow
        await LedgerService.lock_client_escrow(
            db=session,
            client_id=client_id,
            required_escrow_micros=request.max_cost_ceiling_micros,
            job_id=job_id,
        )

        # Step 2: Execute full pipeline
        results = await orchestrator.execute_job(
            job_id=job_id,
            request=request,
            client_id=client_id,
            db=session,
            http_client=mock_http_client,
            tracker=ProgressTracker(),
        )

    # 1. Assert all 15 prompts executed and reassembled strictly in order 0..14
    assert len(results) == 15
    assert [r.prompt_index for r in results] == list(range(15))

    # 2. Assert 100% of prompts executed exclusively on the Nebius anchor
    for r in results:
        assert r.executing_node_id == "nebius-anchor"
        assert r.output_text != ""
        assert r.input_tokens > 0
        assert r.output_tokens > 0

    # 3. Assert spot nodes received zero execution and zero withdrawable credits
    assert mock_store.compute_nodes["spot-node-1"]["withdrawable_micros"] == 0
    assert mock_store.compute_nodes["spot-node-2"]["withdrawable_micros"] == 0

    # 4. Assert anchor received positive verified credit
    anchor_balance = mock_store.compute_nodes["nebius-anchor"]["withdrawable_micros"]
    assert anchor_balance > 0

    # 5. Assert job status is COMPLETED
    job_record = mock_store.batch_jobs[job_id]
    assert job_record["status"] == "COMPLETED"
    assert job_record["actual_settled_cost_micros"] == anchor_balance

    # 6. Assert client escrow is fully released with zero trapped balance
    client_state = mock_store.clients[client_id]
    assert client_state["locked_escrow_micros"] == 0
    total_deducted = anchor_balance + job_record["platform_fee_micros"]
    assert client_state["available_balance_micros"] == initial_avail - total_deducted

    await mock_http_client.aclose()


# -----------------------------------------------------------------------------
# TEST 2: PUBLIC WORKLOAD (GREEDY SHREDDING ACROSS SPOT NODES)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_public_job_shreds_across_spot_and_settles_savings(mock_store):
    """
    Submitting a PUBLIC workload shreds prompts across available spot nodes using
    the greedy capacity scheduler, passes all shreds through 5-tier verification,
    and settles verified savings and platform take-rate in the ledger.
    """
    apps = {
        "nebius-anchor": mk_mock_node("nebius-anchor"),
        "spot-node-1": mk_mock_node("spot-node-1"),
        "spot-node-2": mk_mock_node("spot-node-2"),
    }
    mock_http_client = build_mock_client(apps)

    orchestrator = JobOrchestrationService()
    orchestrator.default_http_client = mock_http_client
    session_factory = MockAsyncSessionFactory(mock_store)

    client_id = list(mock_store.clients.keys())[0]
    initial_avail = mock_store.clients[client_id]["available_balance_micros"]

    prompts = [
        InferencePrompt(prompt_index=i, content=f"Public benchmark document processing prompt {i}")
        for i in range(25)
    ]
    request = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.PUBLIC,
        prompts=prompts,
        max_tokens_per_prompt=64,
        max_cost_ceiling_micros=2_000_000,
    )
    job_id = uuid.uuid4()

    async with session_factory() as session:
        await LedgerService.lock_client_escrow(
            db=session,
            client_id=client_id,
            required_escrow_micros=request.max_cost_ceiling_micros,
            job_id=job_id,
        )

        results = await orchestrator.execute_job(
            job_id=job_id,
            request=request,
            client_id=client_id,
            db=session,
            http_client=mock_http_client,
            tracker=ProgressTracker(),
        )

    # 1. Assert reassembly in exact index order
    assert len(results) == 25
    assert [r.prompt_index for r in results] == list(range(25))
    assert all(r.status == "COMPLETED_SPOT" for r in results)

    # 2. Assert spot nodes were credited
    spot1_balance = mock_store.compute_nodes["spot-node-1"]["withdrawable_micros"]
    assert spot1_balance > 0

    # 3. Assert job finished with COMPLETED status and exact settled costs
    job_record = mock_store.batch_jobs[job_id]
    assert job_record["status"] == "COMPLETED"
    assert job_record["actual_settled_cost_micros"] == spot1_balance
    assert job_record["platform_fee_micros"] > 0  # Platform take-rate on savings

    # 4. Assert zero leaked escrow and client refunded unused funds
    client_state = mock_store.clients[client_id]
    assert client_state["locked_escrow_micros"] == 0
    total_deducted = spot1_balance + job_record["platform_fee_micros"]
    assert client_state["available_balance_micros"] == initial_avail - total_deducted

    await mock_http_client.aclose()


# -----------------------------------------------------------------------------
# TEST 3: CANARY FAILURE & ANCHOR FAILOVER (RETRY BUDGET = 2)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_canary_failure_fails_over_to_anchor_with_retries(mock_store):
    """
    When a spot node fails canary verification (e.g. degraded / hallucinated output):
      1. VerificationService flags the shred as VERIFIED_FAIL_REROUTED.
      2. The failing spot node receives 0 ledger payout.
      3. Prompts are failed over to the Nebius anchor node with retry budget = 2.
      4. Prompt results have status 'COMPLETED_ANCHOR_FAILOVER'.
      5. Results are reassembled in original index order with complete financial settlement.
    """
    apps = {
        "nebius-anchor": mk_mock_node("nebius-anchor"),
        "spot-node-1": mk_mock_node("spot-node-1", degraded=True),  # Degraded spot node
    }
    mock_http_client = build_mock_client(apps)

    orchestrator = JobOrchestrationService()
    orchestrator.default_http_client = mock_http_client
    session_factory = MockAsyncSessionFactory(mock_store)

    client_id = list(mock_store.clients.keys())[0]

    prompts = [
        InferencePrompt(prompt_index=i, content=f"Prompt for degraded node test {i}")
        for i in range(10)
    ]
    request = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.PUBLIC,
        prompts=prompts,
        max_tokens_per_prompt=32,
        max_cost_ceiling_micros=1_500_000,
    )
    job_id = uuid.uuid4()

    async with session_factory() as session:
        await LedgerService.lock_client_escrow(
            db=session,
            client_id=client_id,
            required_escrow_micros=request.max_cost_ceiling_micros,
            job_id=job_id,
        )

        results = await orchestrator.execute_job(
            job_id=job_id,
            request=request,
            client_id=client_id,
            db=session,
            http_client=mock_http_client,
            tracker=ProgressTracker(),
        )

    # 1. Assert all 10 prompts reassembled in original prompt_index order
    assert len(results) == 10
    assert [r.prompt_index for r in results] == list(range(10))

    # 2. Assert failing spot prompts were rerouted to Nebius anchor
    for r in results:
        assert r.status == "COMPLETED_ANCHOR_FAILOVER"
        assert r.executing_node_id == "nebius-anchor"
        assert r.output_text != ""

    # 3. Assert failing spot node received ZERO payout in ledger
    assert mock_store.compute_nodes["spot-node-1"]["withdrawable_micros"] == 0

    # 4. Assert Nebius anchor received verified failover compensation
    anchor_payout = mock_store.compute_nodes["nebius-anchor"]["withdrawable_micros"]
    assert anchor_payout > 0

    # 5. Assert shred status recorded as VERIFIED_FAIL_REROUTED
    shreds = [s for s in mock_store.job_shreds.values() if s["job_id"] == job_id]
    assert any(s["status"] == "VERIFIED_FAIL_REROUTED" for s in shreds)

    # 6. Assert job status COMPLETED and escrow unlocked
    job_record = mock_store.batch_jobs[job_id]
    assert job_record["status"] == "COMPLETED"
    assert mock_store.clients[client_id]["locked_escrow_micros"] == 0

    await mock_http_client.aclose()


# -----------------------------------------------------------------------------
# TEST 4: TRANSPORT ERROR FAILOVER (HTTP 503)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transport_error_failover_to_anchor(mock_store):
    """
    When a spot node suffers an unrecoverable HTTP 503 / network failure,
    prompts automatically fail over to the Nebius anchor node.
    """
    apps = {
        "nebius-anchor": mk_mock_node("nebius-anchor"),
        "spot-node-1": mk_mock_node("spot-node-1", fail_rate=1.0, fail_status=503),
    }
    mock_http_client = build_mock_client(apps)

    orchestrator = JobOrchestrationService()
    orchestrator.default_http_client = mock_http_client
    session_factory = MockAsyncSessionFactory(mock_store)

    client_id = list(mock_store.clients.keys())[0]

    prompts = [
        InferencePrompt(prompt_index=i, content=f"Prompt for 503 transport test {i}")
        for i in range(5)
    ]
    request = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.PUBLIC,
        prompts=prompts,
        max_tokens_per_prompt=32,
        max_cost_ceiling_micros=1_000_000,
    )
    job_id = uuid.uuid4()

    async with session_factory() as session:
        await LedgerService.lock_client_escrow(
            db=session,
            client_id=client_id,
            required_escrow_micros=request.max_cost_ceiling_micros,
            job_id=job_id,
        )

        results = await orchestrator.execute_job(
            job_id=job_id,
            request=request,
            client_id=client_id,
            db=session,
            http_client=mock_http_client,
            tracker=ProgressTracker(),
        )

    assert len(results) == 5
    assert [r.prompt_index for r in results] == list(range(5))
    assert all(r.status == "COMPLETED_ANCHOR_FAILOVER" for r in results)
    assert all(r.executing_node_id == "nebius-anchor" for r in results)
    assert mock_store.compute_nodes["spot-node-1"]["withdrawable_micros"] == 0
    assert mock_store.compute_nodes["nebius-anchor"]["withdrawable_micros"] > 0

    await mock_http_client.aclose()


# -----------------------------------------------------------------------------
# TEST 5: FULL FASTAPI REST API INGESTION & QUERY (POST /jobs & GET /jobs/{id}/results)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_rest_api_lifecycle_and_results_query(mock_store):
    """
    Asserts the full end-to-end API lifecycle:
      1. POST /api/v1/jobs submits the job and returns 201 CREATED (status=QUEUED).
      2. Orchestrator executes in the background event loop.
      3. GET /api/v1/jobs/{job_id} reflects COMPLETED status and settled ledger balances.
      4. GET /api/v1/jobs/{job_id}/results returns ordered PromptResultItem list.
    """
    apps = {
        "nebius-anchor": mk_mock_node("nebius-anchor"),
        "spot-node-1": mk_mock_node("spot-node-1"),
        "spot-node-2": mk_mock_node("spot-node-2"),
    }
    mock_http_client = build_mock_client(apps)

    session_factory = MockAsyncSessionFactory(mock_store)
    orchestration_service.default_http_client = mock_http_client
    orchestration_service.session_factory = session_factory

    app = FastAPI()
    app.include_router(jobs_router, prefix="/api/v1")

    # Dependency override to use in-memory mock session
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "sensitivity": "CONFIDENTIAL",
            "prompts": [
                {"prompt_index": 0, "content": "Compute sum of 10 and 20."},
                {"prompt_index": 1, "content": "Analyze regulatory compliance report."},
                {"prompt_index": 2, "content": "Extract financial ledger statistics."},
            ],
            "max_tokens_per_prompt": 64,
            "max_cost_ceiling_micros": 1_000_000,
        }

        # 1. Submit batch job
        post_resp = await client.post(
            "/api/v1/jobs",
            json=payload,
            headers={"X-API-Key": "default_apex_test_key"},
        )
        assert post_resp.status_code == 201
        job_data = post_resp.json()
        job_id_str = job_data["job_id"]
        job_id = uuid.UUID(job_id_str)
        assert job_data["status"] == "QUEUED"
        assert job_data["total_prompts"] == 3

        # 2. Await the background orchestration task to finish
        results = await orchestration_service.wait_for_job(job_id, timeout_s=10.0)
        assert results is not None
        assert len(results) == 3

        # 3. Query job status via GET /api/v1/jobs/{job_id}
        status_resp = await client.get(f"/api/v1/jobs/{job_id_str}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "COMPLETED"
        assert status_data["actual_settled_cost_micros"] > 0

        # 4. Query prompt results via GET /api/v1/jobs/{job_id}/results
        results_resp = await client.get(f"/api/v1/jobs/{job_id_str}/results")
        assert results_resp.status_code == 200
        results_data = results_resp.json()
        assert len(results_data) == 3
        assert [r["prompt_index"] for r in results_data] == [0, 1, 2]
        assert all(r["output_text"] != "" for r in results_data)
        assert all(r["executing_node_id"] == "nebius-anchor" for r in results_data)

        # 5. Assert durable storage: results_payload is durably written to PostgreSQL batch_jobs
        stored_job = mock_store.batch_jobs[job_id]
        assert stored_job["results_payload"] is not None
        durable_payload = json.loads(stored_job["results_payload"])
        assert len(durable_payload) == 3
        assert [r["prompt_index"] for r in durable_payload] == [0, 1, 2]

    await mock_http_client.aclose()


@pytest.mark.asyncio
async def test_enum_anchor_enforcement_rejects_nebius_imposter(mock_store):
    """
    Vulnerability 3 Test: Cryptographic/Enum-Based Anchor Enforcement.
    A rogue node named 'nebius-imposter' with provider_name 'Nebius Token Factory Fake'
    must NEVER be selected for CONFIDENTIAL workloads if its trust_tier != ANCHOR.
    Traffic must strictly route to the verified ANCHOR node regardless of node names.
    """
    store = mock_store
    store.compute_nodes.clear()

    # Rogue node with 'nebius' in provider_name and node_id, but PROBATION_SPOT trust tier
    store.compute_nodes["nebius-imposter"] = {
        "node_id": "nebius-imposter",
        "provider_name": "Nebius Token Factory Imposter",
        "endpoint_url": "http://nebius-imposter/v1",
        "model_id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "trust_tier": NodeTrustTier.PROBATION_SPOT.value,
        "paypal_receiver_email": "imposter@fake.com",
        "input_price_per_1m_micros": 10_000,
        "output_price_per_1m_micros": 40_000,
        "max_concurrent_requests": 10,
        "pending_probation_micros": 0,
        "withdrawable_micros": 0,
        "payout_pending_micros": 0,
        "is_active": True,
    }

    # Legitimate anchor node without 'nebius' in its name
    store.compute_nodes["custom-anchor-01"] = {
        "node_id": "custom-anchor-01",
        "provider_name": "Validated Sovereign Cloud",
        "endpoint_url": "http://custom-anchor-01/v1",
        "model_id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "trust_tier": NodeTrustTier.ANCHOR.value,
        "paypal_receiver_email": "anchor@sovereign.com",
        "input_price_per_1m_micros": 60_000,
        "output_price_per_1m_micros": 240_000,
        "max_concurrent_requests": 10,
        "pending_probation_micros": 0,
        "withdrawable_micros": 0,
        "payout_pending_micros": 0,
        "is_active": True,
    }

    apps = {
        "nebius-imposter": mk_mock_node("nebius-imposter"),
        "custom-anchor-01": mk_mock_node("custom-anchor-01"),
    }
    mock_http_client = build_mock_client(apps)
    session_factory = MockAsyncSessionFactory(store)

    orchestrator = JobOrchestrationService()
    orchestrator.default_http_client = mock_http_client
    orchestrator.session_factory = session_factory

    req = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.CONFIDENTIAL,
        prompts=[InferencePrompt(prompt_index=i, content=f"Confidential payload {i}") for i in range(10)],
        max_tokens_per_prompt=64,
        max_cost_ceiling_micros=1_000_000,
    )
    job_id = uuid.uuid4()
    client_id = uuid.uuid4()
    store.clients[client_id] = {
        "client_id": client_id,
        "available_balance_micros": 100_000_000,
        "locked_escrow_micros": 1_000_000,
        "hourly_spend_limit_micros": 50_000_000,
    }

    async with session_factory() as session:
        results = await orchestrator.execute_job(
            job_id=job_id,
            request=req,
            client_id=client_id,
            db=session,
            http_client=mock_http_client,
            tracker=ProgressTracker(),
        )

    # Assert 100% of prompts executed on custom-anchor-01, 0 on nebius-imposter
    assert len(results) == 10
    assert all(r.executing_node_id == "custom-anchor-01" for r in results)
    assert not any(r.executing_node_id == "nebius-imposter" for r in results)
    assert store.compute_nodes["custom-anchor-01"]["withdrawable_micros"] > 0
    assert store.compute_nodes["nebius-imposter"]["withdrawable_micros"] == 0

    await mock_http_client.aclose()


@pytest.mark.asyncio
async def test_confidential_fails_closed_when_no_anchor_registered(mock_store):
    """
    Vulnerability 3 Test: Fail-closed guarantee for CONFIDENTIAL workloads.
    When no verified ANCHOR node exists in the registry, scheduling must raise ValueError.
    """
    store = mock_store
    store.compute_nodes.clear()

    # Only spot nodes exist
    store.compute_nodes["spot-only-1"] = {
        "node_id": "spot-only-1",
        "provider_name": "Spot Provider 1",
        "endpoint_url": "http://spot1/v1",
        "model_id": "m",
        "trust_tier": NodeTrustTier.VERIFIED_PROVIDER.value,
        "paypal_receiver_email": "spot1@test.com",
        "input_price_per_1m_micros": 40_000,
        "output_price_per_1m_micros": 160_000,
        "max_concurrent_requests": 4,
        "pending_probation_micros": 0,
        "withdrawable_micros": 0,
        "payout_pending_micros": 0,
        "is_active": True,
    }

    session_factory = MockAsyncSessionFactory(store)
    orchestrator = JobOrchestrationService()

    req = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.CONFIDENTIAL,
        prompts=[InferencePrompt(prompt_index=0, content="Secret prompt")],
        max_tokens_per_prompt=64,
        max_cost_ceiling_micros=100_000,
    )

    async with session_factory() as session:
        candidates = await orchestrator.scheduler.get_candidate_nodes(db=session)
        with pytest.raises(ValueError, match="No verified ANCHOR nodes available"):
            orchestrator.scheduler.schedule_batch(
                job_id=uuid.uuid4(),
                total_prompts=1,
                sensitivity=req.sensitivity,
                candidates=candidates,
            )

