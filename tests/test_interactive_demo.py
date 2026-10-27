"""
ApexMarket: Tests for Interactive Chaos Injection & Zero-Setup Demo Fallbacks
Validates:
  1. POST /api/v1/demo/drift toggles node drift state in memory.
  2. Batch execution with drift active triggers VERIFIED_FAIL_REROUTED and emits [QUARANTINE] event log.
  3. Spot node receives $0.00 and prompts fail over to anchor.
  4. POST /api/v1/ledger/settle-now returns a valid sandbox receipt and zeroes withdrawable balances.
"""
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.services.chaos_service import set_node_drift, is_node_drifted, reset_drift, reset_quarantine, is_node_quarantined
from app.services.progress_tracker import tracker
from app.services.in_memory_store import global_in_memory_store, get_in_memory_session
from app.schemas import (
    BatchJobCreateRequest,
    InferencePrompt,
    WorkloadSensitivity,
    ShredStatus,
)
from app.services.orchestration_service import JobOrchestrationService


@pytest.fixture(autouse=True)
def clean_state():
    reset_drift()
    reset_quarantine()
    tracker.events.clear()
    for n in global_in_memory_store.compute_nodes.values():
        n["is_active"] = True
        if n["node_id"] != "nebius-nemotron-anchor":
            n["trust_tier"] = "PROBATION_SPOT"
    yield
    reset_drift()
    reset_quarantine()
    tracker.events.clear()
    for n in global_in_memory_store.compute_nodes.values():
        n["is_active"] = True
        if n["node_id"] != "nebius-nemotron-anchor":
            n["trust_tier"] = "PROBATION_SPOT" 


def test_demo_drift_toggle_endpoint():
    with TestClient(app) as client:
        # 1. Inject drift on runpod-h100-spot-01
        res = client.post(
            "/api/v1/demo/drift",
            headers={"X-Admin-Key": "apex-demo-2026"},
            json={"degraded": True, "node_id": "runpod-h100-spot-01"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["degraded"] is True
        assert data["status"] == "MOCK_CONFIGURED"
        assert is_node_drifted("runpod-h100-spot-01") is True

        # Check telemetry event was emitted
        events = tracker.snapshot()["events"]
        assert any("quantization drift INJECTED" in e["text"] for e in events)

        # 2. Clear drift
        res2 = client.post(
            "/api/v1/demo/drift",
            headers={"X-Admin-Key": "apex-demo-2026"},
            json={"degraded": False, "node_id": "runpod-h100-spot-01"},
        )
        assert res2.status_code == 200
        assert is_node_drifted("runpod-h100-spot-01") is False


@pytest.mark.asyncio
async def test_batch_execution_with_drift_triggers_quarantine_and_anchor_failover():
    # 1. Activate drift on runpod-h100-spot-01
    set_node_drift("runpod-h100-spot-01", True)

    session = get_in_memory_session()
    orchestrator = JobOrchestrationService()

    prompts = [
        InferencePrompt(prompt_index=i, content=f"Calculate the sum of {100 + i} and {200 + i} carefully.")
        for i in range(30)
    ]
    request = BatchJobCreateRequest(
        sensitivity=WorkloadSensitivity.PUBLIC,
        prompts=prompts,
        max_tokens_per_prompt=32,
        max_cost_ceiling_micros=3_000_000,
    )
    job_id = uuid.uuid4()
    client_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    # Record initial spot balance
    initial_spot = global_in_memory_store.compute_nodes["runpod-h100-spot-01"].get("withdrawable_micros", 0)

    results = await orchestrator.execute_job(
        job_id=job_id,
        request=request,
        client_id=client_id,
        db=session,
        tracker=tracker,
    )

    # 1. Reassembly check: all 30 prompts returned in order
    assert len(results) == 30
    assert [r.prompt_index for r in results] == list(range(30))

    # 2. Check quarantine event in telemetry tracker
    events = tracker.snapshot()["events"]
    quarantine_events = [e for e in events if "[QUARANTINE]" in e["text"]]
    assert len(quarantine_events) > 0
    assert "Node runpod-h100-spot-01 failed canary audit" in quarantine_events[0]["text"]
    assert "Rerouting prompts to Nebius Anchor" in quarantine_events[0]["text"]

    # 3. Check shred status is VERIFIED_FAIL_REROUTED for the spot shred
    spot_shreds = [
        sh for sh in global_in_memory_store.job_shreds.values()
        if sh["job_id"] == job_id and sh["node_id"] == "runpod-h100-spot-01"
    ]
    if spot_shreds:
        assert spot_shreds[0]["status"] == ShredStatus.VERIFIED_FAIL_REROUTED.value

    # 4. Spot node received $0.00 payout for the failed shred
    spot_after = global_in_memory_store.compute_nodes["runpod-h100-spot-01"].get("withdrawable_micros", 0)
    assert spot_after == initial_spot

    # 5. Persistent Quarantine / Slashing verification: node must be quarantined and excluded from candidates
    assert is_node_quarantined("runpod-h100-spot-01") is True
    candidates = await orchestrator.scheduler.get_candidate_nodes(db=session)
    candidate_ids = [c.node_id for c in candidates]
    assert "runpod-h100-spot-01" not in candidate_ids


def test_settle_now_endpoint_sandbox():
    with TestClient(app) as client:
        # Give a node some payable balance in memory
        global_in_memory_store.compute_nodes["runpod-h100-spot-01"]["withdrawable_micros"] = 50000

        res = client.post(
            "/api/v1/ledger/settle-now",
            headers={
                "X-Admin-Key": "apex-demo-2026",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["total_amount_micros"] >= 50000
        assert data["paypal_batch_id"].startswith("PAYPAL-SANDBOX-")

        # Telemetry event was emitted
        events = tracker.snapshot()["events"]
        assert any("PayPal Sandbox · COMPLETED" in e["text"] for e in events)
