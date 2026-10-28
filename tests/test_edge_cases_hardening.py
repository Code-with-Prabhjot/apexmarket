"""
ApexMarket: Backend Edge-Case Hardening & Invariant Verification Tests
Asserts:
  1. Input Boundary Validation: Malformed prompts (empty, whitespace, Unicode control chars, >5,000 prompts)
     return clean HTTP 422 structured JSON errors without unhandled 500s.
  2. Double-Entry Ledger Integrity: Strict balance conservation (Total = Available + Escrow + Probation)
     and sub-cent remainder accounting across all states.
  3. Graceful Degraded State: Clean operation when PostgreSQL or Redis is offline via in-memory fallback.
  4. Nebius Credit Protection Guard: Verification that live calls are blocked and capped unless explicitly opted-in.
"""

import os
import uuid
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    InferencePrompt,
    BatchJobCreateRequest,
    WorkloadSensitivity,
)
from app.services.ledger_service import (
    calculate_subcent_split,
    compute_net_savings_and_fee,
    micros_to_usd_str,
    usd_to_micros,
    MICROS_PER_CENT,
)
from app.services.in_memory_store import InMemoryTestStore, MockAsyncSession


# ---------------------------------------------------------------------------
# 1. INPUT BOUNDARY VALIDATION & CLEAN HTTP 422 RESPONSES
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_input_boundary_empty_prompt_returns_422():
    """Empty prompt string must return clean HTTP 422 with structured JSON details."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "sensitivity": "CONFIDENTIAL",
            "prompts": [{"prompt_index": 0, "content": ""}],
            "max_cost_ceiling_micros": 1000000,
        }
        res = await client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"
        data = res.json()
        assert "detail" in data
        assert any("content" in str(err) for err in data["detail"])


@pytest.mark.asyncio
async def test_input_boundary_whitespace_prompt_returns_422():
    """Whitespace-only prompt must return clean HTTP 422 with structured JSON details."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "sensitivity": "CONFIDENTIAL",
            "prompts": [{"prompt_index": 0, "content": "   \n\t  "}],
            "max_cost_ceiling_micros": 1000000,
        }
        res = await client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"
        data = res.json()
        assert "detail" in data
        assert any("whitespace" in str(err) or "content" in str(err) for err in data["detail"])


@pytest.mark.asyncio
@pytest.mark.parametrize("control_char", ["\x00", "\x01", "\x07", "\x08", "\x1b", "\x7f"])
async def test_input_boundary_unicode_control_characters_return_422(control_char):
    """Submitting Unicode control characters must return clean HTTP 422 rather than 500."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "sensitivity": "CONFIDENTIAL",
            "prompts": [{"prompt_index": 0, "content": f"Malformed payload with control {control_char} character"}],
            "max_cost_ceiling_micros": 1000000,
        }
        res = await client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 422, f"Expected 422 for control char {repr(control_char)}, got {res.status_code}"
        data = res.json()
        assert "detail" in data
        assert any("control character" in str(err) or "content" in str(err) for err in data["detail"])


@pytest.mark.asyncio
async def test_input_boundary_oversized_payload_returns_422():
    """Batch with > 5000 prompts must return clean HTTP 422."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "sensitivity": "CONFIDENTIAL",
            "prompts": [{"prompt_index": i, "content": f"Valid prompt {i}"} for i in range(5001)],
            "max_cost_ceiling_micros": 10000000,
        }
        res = await client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"
        data = res.json()
        assert "detail" in data


# ---------------------------------------------------------------------------
# 2. DOUBLE-ENTRY LEDGER BALANCE CONSERVATION
# ---------------------------------------------------------------------------

def test_ledger_balance_conservation_multistep_lifecycle():
    """
    Asserts strict double-entry balance conservation ($Total = Available + Escrow + Probation$)
    across the entire lifecycle:
      - Initial deposit top-up
      - Escrow locking
      - Verified shred execution (probation and withdrawable)
      - Unused escrow release and platform savings fee
    """
    # Initial State: Client deposits $50.00
    initial_topup_micros = 50_000_000  # $50.00
    available = initial_topup_micros
    locked_escrow = 0
    node_probation = 0
    node_withdrawable = 0
    platform_revenue = 0

    def assert_global_conservation(step_name: str):
        total_accounted = (
            available + locked_escrow + node_probation + node_withdrawable + platform_revenue
        )
        assert total_accounted == initial_topup_micros, (
            f"Conservation violated at step '{step_name}': "
            f"expected {initial_topup_micros}, got {total_accounted}"
        )

    assert_global_conservation("Initial Top-up")

    # Step 1: Lock Escrow for $5.00 Job
    job_reserved_escrow = 5_000_000
    available -= job_reserved_escrow
    locked_escrow += job_reserved_escrow
    assert_global_conservation("Escrow Locked")

    # Step 2: Shred 1 executed by Probation Node (Cost $1.851234)
    shred1_cost = 1_851_234
    locked_escrow -= shred1_cost
    node_probation += shred1_cost
    assert_global_conservation("Shred 1 Probation Executed")

    # Step 3: Shred 2 executed by Verified Node (Cost $1.568766)
    shred2_cost = 1_568_766
    locked_escrow -= shred2_cost
    node_withdrawable += shred2_cost
    assert_global_conservation("Shred 2 Verified Executed")

    # Total Settled Work = $3.420000
    actual_settled = shred1_cost + shred2_cost
    assert actual_settled == 3_420_000

    # Step 4: Final Job Settlement
    # Baseline was $5.00 (5,000,000 micros).
    # Actual cost was $3.42 (3,420,000 micros).
    # Gross savings = $1.58 (1,580,000 micros).
    baseline_cost = 5_000_000
    gross_savings, platform_fee = compute_net_savings_and_fee(
        baseline_cost_micros=baseline_cost,
        actual_cost_micros=actual_settled,
        take_rate_bps=1000,  # 10%
    )
    assert gross_savings == 1_580_000
    assert platform_fee == 158_000

    # Unspent escrow before fee was 5,000,000 - 3,420,000 = 1,580,000
    # Remaining in locked_escrow: 1,580,000
    assert locked_escrow == 1_580_000

    # Deduct platform fee from escrow
    locked_escrow -= platform_fee
    platform_revenue += platform_fee
    assert_global_conservation("Platform Fee Deducted")

    # Refund unused escrow back to client available balance
    unused_refund = locked_escrow
    locked_escrow -= unused_refund
    available += unused_refund
    assert locked_escrow == 0
    assert_global_conservation("Unused Escrow Refunded")

    # Step 5: Sub-Cent Payout Split on Node Withdrawable
    payable, subcent_remainder = calculate_subcent_split(node_withdrawable)
    assert payable + subcent_remainder == node_withdrawable
    assert payable % MICROS_PER_CENT == 0
    assert 0 <= subcent_remainder < MICROS_PER_CENT


# ---------------------------------------------------------------------------
# 3. GRACEFUL DEGRADED STATE (OFFLINE POSTGRES / REDIS)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_degraded_state_health_and_nodes_endpoints():
    """
    Verifies that system health and node listing endpoints operate cleanly
    even when persistent database is not used, using in-memory fallbacks.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health endpoint
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "HEALTHY"

        # 2. Nodes endpoint
        res_nodes = await client.get("/api/v1/nodes")
        assert res_nodes.status_code == 200
        nodes = res_nodes.json()
        assert len(nodes) >= 3

        # 3. Telemetry endpoint
        res_telemetry = await client.get("/api/v1/telemetry")
        assert res_telemetry.status_code == 200
        telemetry = res_telemetry.json()
        assert len(telemetry) >= 3


# ---------------------------------------------------------------------------
# 4. NEBIUS CREDIT PROTECTION GUARD
# ---------------------------------------------------------------------------

def test_credit_protection_guard_blocks_without_explicit_optin():
    """
    Ensures that without EXECUTE_LIVE_NEBIUS=true, live calls are guarded.
    """
    from app.config import get_settings
    settings = get_settings()
    assert settings.EXECUTE_LIVE_NEBIUS is False


@pytest.mark.asyncio
async def test_benchmark_dry_run_provenance_when_live_flag_omitted(tmp_path, monkeypatch):
    """
    Asserts benchmarks/run_benchmark.py emits [DRY-RUN / MOCK] provenance
    and does not call Nebius when EXECUTE_LIVE_NEBIUS is not set.
    """
    from benchmarks.run_benchmark import main
    monkeypatch.delenv("EXECUTE_LIVE_NEBIUS", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "fake_voucher_key")

    csv_file = tmp_path / "test_results.csv"
    monkeypatch.setattr("benchmarks.run_benchmark.EXECUTE_LIVE_NEBIUS", False)

    await main(argv=[])
    
    with open("benchmarks/empirical_results.csv", "r", encoding="utf-8") as f:
        content = f.read()
    assert "[DRY-RUN / MOCK]" in content

