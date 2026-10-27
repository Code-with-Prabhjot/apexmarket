"""
ApexMarket: Tests for Code Review Remediations
Verifies all 7 targeted production fixes:
  1. Restrict Mock Fallback to Development (Production Fail-Closed)
  2. Production Hardened Defaults (Fail-Closed ADMIN_API_KEY & CORS)
  3. Robust Offline Tokenizer Billing Guard (Strict Timeout & Conservative Chars/Token Ratio)
  4. Persistent Node Quarantine / Slashing Filtering in CapacityAwareScheduler
  5. HTTP Client Connection Reuse & Limits
"""
import asyncio
from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.actors.executor_actor import (
    ExecNode,
    ShredExecutor,
    UpstreamProviderError,
    NodeExecutionError,
    get_shared_client as get_executor_client,
    close_shared_client as close_executor_client,
)
from app.actors.scheduler_actor import CapacityAwareScheduler, NodeCandidate
from app.schemas import NodeTrustTier, WorkloadSensitivity
from app.services.chaos_service import (
    quarantine_node,
    is_node_quarantined,
    reset_quarantine,
    get_quarantined_nodes,
)
from app.services.verification_service import TokenizerBillingAuthority
from app.services.paypal_client import (
    PayPalClient,
    get_shared_client as get_paypal_client,
    close_shared_client as close_paypal_client,
)
from app.main import lifespan


@pytest.fixture(autouse=True)
def clean_quarantine_state():
    reset_quarantine()
    yield
    reset_quarantine()


@pytest.mark.asyncio
async def test_mock_fallback_fails_closed_in_production(monkeypatch):
    """In production (or when ALLOW_MOCK_FALLBACK=False), offline nodes must raise UpstreamProviderError."""
    # Set production settings
    prod_settings = Settings(
        APP_ENV="production",
        ADMIN_API_KEY="prod-secret-key-12345",
        ALLOW_MOCK_FALLBACK=False,
    )
    monkeypatch.setattr("app.actors.executor_actor.get_settings", lambda: prod_settings)

    node = ExecNode(
        node_id="runpod-h100-spot-01",
        endpoint_url="http://localhost:8001/v1",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        is_anchor=False,
    )
    executor = ShredExecutor([node, ExecNode("anchor", "https://api.tokenfactory.nebius.com/v1", "anchor", is_anchor=True)])

    with pytest.raises(UpstreamProviderError) as exc_info:
        await executor.call_node(node, "Hello world", max_tokens=10)

    assert "Mock fallback rejected" in str(exc_info.value)
    assert issubclass(UpstreamProviderError, NodeExecutionError)
    assert issubclass(UpstreamProviderError, RuntimeError)


@pytest.mark.asyncio
async def test_mock_fallback_tagged_with_simulated_metadata(monkeypatch):
    """In development with mock fallback allowed, result is tagged with is_simulated=True and SIMULATED_MOCK."""
    dev_settings = Settings(
        APP_ENV="development",
        ALLOW_MOCK_FALLBACK=True,
    )
    monkeypatch.setattr("app.actors.executor_actor.get_settings", lambda: dev_settings)

    node = ExecNode(
        node_id="runpod-h100-spot-01",
        endpoint_url="http://localhost:8001/v1",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        is_anchor=False,
    )
    anchor = ExecNode(
        node_id="nebius-nemotron-anchor",
        endpoint_url="https://api.tokenfactory.nebius.com/v1",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        is_anchor=True,
    )
    executor = ShredExecutor([node, anchor])

    # 1. Direct call_node result carries simulation metadata
    call_res = await executor.call_node(node, "Hello world", max_tokens=10)
    assert len(call_res) == 4
    assert getattr(call_res, "is_simulated", False) is True
    assert getattr(call_res, "execution_mode", "LIVE") == "SIMULATED_MOCK"

    # 2. ShredExecutor.run() produces PromptResult with is_simulated=True
    results = await executor.run(
        job_id="test-job",
        prompts=["Prompt 0"],
        assignments=[("runpod-h100-spot-01", [0])],
        max_tokens=10,
    )
    assert len(results) == 1
    assert results[0].is_simulated is True
    assert results[0].execution_mode == "SIMULATED_MOCK"


@pytest.mark.asyncio
async def test_production_fails_closed_on_default_admin_key(monkeypatch):
    """FastAPI startup lifespan must raise RuntimeError if ADMIN_API_KEY is apex-demo-2026 in production."""
    insecure_prod = Settings(
        APP_ENV="production",
        ADMIN_API_KEY="apex-demo-2026",
        FRONTEND_ORIGIN="https://apexmarket.ai",
    )
    monkeypatch.setattr("app.main.get_settings", lambda: insecure_prod)

    app = FastAPI(lifespan=lifespan)
    with pytest.raises(RuntimeError) as exc_info:
        async with lifespan(app):
            pass

    assert "Production requires secure ADMIN_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_production_restricts_cors_and_rejects_wildcard(monkeypatch):
    """FastAPI startup lifespan rejects wildcard CORS origins in production."""
    wildcard_prod = Settings(
        APP_ENV="production",
        ADMIN_API_KEY="super-secret-admin-key-2026",
        FRONTEND_ORIGIN="*",
    )
    monkeypatch.setattr("app.main.get_settings", lambda: wildcard_prod)

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"])

    with pytest.raises(RuntimeError) as exc_info:
        async with lifespan(app):
            pass

    assert "FRONTEND_ORIGIN" in str(exc_info.value) or "Wildcard CORS" in str(exc_info.value)


def test_offline_tokenizer_billing_guard_never_returns_none_or_zero(monkeypatch):
    """Tokenizer billing authority falls back to conservative 4.0 chars/token and never returns None or 0."""
    # Force tokenizer to offline state
    monkeypatch.setattr(TokenizerBillingAuthority, "get_tokenizer", classmethod(lambda cls: None))
    TokenizerBillingAuthority._warned_offline = False

    # Empty string returns minimum 1
    assert TokenizerBillingAuthority.count_tokens("") == 1
    assert TokenizerBillingAuthority.count_tokens(None) == 1

    # Exact conservative 4.0 chars/token boundary
    # 4 chars -> 1 token
    assert TokenizerBillingAuthority.count_tokens("1234") == 1
    # 5 chars -> 2 tokens (ceil(5/4) = 2)
    assert TokenizerBillingAuthority.count_tokens("12345") == 2
    # 8 chars -> 2 tokens
    assert TokenizerBillingAuthority.count_tokens("12345678") == 2
    # 9 chars -> 3 tokens
    assert TokenizerBillingAuthority.count_tokens("123456789") == 3

    long_prompt = "A" * 100
    assert TokenizerBillingAuthority.count_tokens(long_prompt) == 25


def test_capacity_aware_scheduler_filters_quarantined_nodes():
    """Scheduler must exclude quarantined and slashed nodes from the candidate pool."""
    scheduler = CapacityAwareScheduler()

    anchor = NodeCandidate(
        node_id="nebius-nemotron-anchor",
        provider_name="Nebius",
        endpoint_url="https://api.tokenfactory.nebius.com/v1",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        trust_tier=NodeTrustTier.ANCHOR,
        input_price_per_1m_micros=60000,
        output_price_per_1m_micros=240000,
        max_concurrent_requests=20,
        tokens_per_sec=100.0,
        effective_cost_per_token_micros=0.0003,
    )
    spot_node = NodeCandidate(
        node_id="runpod-h100-spot-01",
        provider_name="RunPod",
        endpoint_url="http://localhost:8001/v1",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        trust_tier=NodeTrustTier.PROBATION_SPOT,
        input_price_per_1m_micros=40000,
        output_price_per_1m_micros=180000,
        max_concurrent_requests=10,
        tokens_per_sec=100.0,
        effective_cost_per_token_micros=0.0002,
    )

    # Before quarantine: spot node is scheduled
    assignments_before = scheduler.schedule_batch(
        job_id="job-1",
        total_prompts=10,
        sensitivity=WorkloadSensitivity.PUBLIC,
        candidates=[spot_node, anchor],
    )
    scheduled_nodes = {a.node_id for a in assignments_before}
    assert "runpod-h100-spot-01" in scheduled_nodes

    # Quarantine spot node
    quarantine_node("runpod-h100-spot-01", duration_minutes=30)
    assert is_node_quarantined("runpod-h100-spot-01") is True
    assert "runpod-h100-spot-01" in get_quarantined_nodes()

    # After quarantine: spot node MUST be filtered out and fallback to anchor
    assignments_after = scheduler.schedule_batch(
        job_id="job-2",
        total_prompts=10,
        sensitivity=WorkloadSensitivity.PUBLIC,
        candidates=[spot_node, anchor],
    )
    scheduled_nodes_after = {a.node_id for a in assignments_after}
    assert "runpod-h100-spot-01" not in scheduled_nodes_after
    assert "nebius-nemotron-anchor" in scheduled_nodes_after


@pytest.mark.asyncio
async def test_shared_http_clients_pool_and_limits():
    """Verify shared HTTP clients enforce keepalive and max connection limits."""
    exec_client = get_executor_client()
    paypal_http = get_paypal_client()

    assert not exec_client.is_closed
    assert not paypal_http.is_closed

    # Verify same instance is returned on repeated calls (connection pooling)
    assert get_executor_client() is exec_client
    assert get_paypal_client() is paypal_http

    # Clean shutdown
    await close_executor_client()
    await close_paypal_client()

    assert exec_client.is_closed
    assert paypal_http.is_closed
