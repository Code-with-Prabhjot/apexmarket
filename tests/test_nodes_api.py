"""
ApexMarket: Tests for Node Registry Auto-Seeding and Telemetry Fallback
Verifies that GET /api/v1/nodes and GET /api/v1/telemetry return the 3 default
seeded nodes (Nebius Anchor and 2 Spot workers) immediately on startup without manual calls.
"""

import httpx
import pytest
from fastapi import FastAPI
from unittest.mock import patch

from app.api.routes_nodes import router as nodes_router, DEFAULT_SEEDED_NODES
from app.api.routes_telemetry import router as telemetry_router
from app.database import get_db, get_redis_client
from app.main import seed_default_nodes_if_empty
from app.schemas import NodeTrustTier
from tests.test_e2e_pipeline import InMemoryTestStore, MockAsyncSessionFactory


@pytest.mark.asyncio
async def test_nodes_auto_seeded_when_database_empty():
    """
    Asserts that when compute_nodes is empty, GET /api/v1/nodes returns
    the 3 default seeded nodes with correct pricing, tiers, and capacities.
    """
    store = InMemoryTestStore(seed_defaults=False)
    session_factory = MockAsyncSessionFactory(store)

    app = FastAPI()
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(telemetry_router, prefix="/api/v1")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_redis():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/v1/nodes returns the 3 default nodes
        resp = await client.get("/api/v1/nodes")
        assert resp.status_code == 200, resp.text
        nodes = resp.json()
        assert len(nodes) == 3

        # Node 1: Anchor
        anchor = next(n for n in nodes if n["node_id"] == "nebius-nemotron-anchor")
        assert anchor["provider_name"] == "Nebius Token Factory"
        assert anchor["trust_tier"] == NodeTrustTier.ANCHOR.value
        assert anchor["input_price_per_1m_micros"] == 60000
        assert anchor["output_price_per_1m_micros"] == 240000
        assert anchor["max_concurrent_requests"] == 20
        assert anchor["endpoint_url"] == "https://api.tokenfactory.nebius.com/v1"
        assert anchor["is_active"] is True

        # Node 2: Spot Worker 1
        spot1 = next(n for n in nodes if n["node_id"] == "runpod-h100-spot-01")
        assert spot1["provider_name"] == "RunPod PCIe H100"
        assert spot1["trust_tier"] == NodeTrustTier.PROBATION_SPOT.value
        assert spot1["input_price_per_1m_micros"] == 40000
        assert spot1["output_price_per_1m_micros"] == 180000
        assert spot1["max_concurrent_requests"] == 10
        assert spot1["endpoint_url"] == "http://localhost:8001/v1"

        # Node 3: Spot Worker 2
        spot2 = next(n for n in nodes if n["node_id"] == "community-spot-02")
        assert spot2["provider_name"] == "Community H100 Spot"
        assert spot2["trust_tier"] == NodeTrustTier.PROBATION_SPOT.value
        assert spot2["input_price_per_1m_micros"] == 35000
        assert spot2["output_price_per_1m_micros"] == 160000
        assert spot2["max_concurrent_requests"] == 8
        assert spot2["endpoint_url"] == "http://localhost:8002/v1"

        # 2. GET /api/v1/nodes/{node_id}
        resp_single = await client.get("/api/v1/nodes/nebius-nemotron-anchor")
        assert resp_single.status_code == 200
        assert resp_single.json()["node_id"] == "nebius-nemotron-anchor"

        # 3. GET /api/v1/telemetry returns telemetry snapshots for all 3 nodes
        resp_telemetry = await client.get("/api/v1/telemetry")
        assert resp_telemetry.status_code == 200
        telemetry = resp_telemetry.json()
        assert len(telemetry) == 3
        node_ids = {t["node_id"] for t in telemetry}
        assert node_ids == {"nebius-nemotron-anchor", "runpod-h100-spot-01", "community-spot-02"}


@pytest.mark.asyncio
async def test_startup_lifespan_auto_seed_inserts_to_database():
    """
    Verifies that seed_default_nodes_if_empty() inserts 3 default records
    into compute_nodes when count is 0.
    """
    store = InMemoryTestStore(seed_defaults=False)
    assert len(store.compute_nodes) == 0

    session_factory = MockAsyncSessionFactory(store)
    with patch("app.main.AsyncSessionLocal", session_factory):
        await seed_default_nodes_if_empty()

    assert len(store.compute_nodes) == 3
    assert "nebius-nemotron-anchor" in store.compute_nodes
    assert "runpod-h100-spot-01" in store.compute_nodes
    assert "community-spot-02" in store.compute_nodes
