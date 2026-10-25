"""
ApexMarket Test Suite: Node Registration Trust Tiers (PostgreSQL)
Asserts anyone can register a PROBATION_SPOT node, but ANCHOR and VERIFIED_PROVIDER
nodes require the admin key. Skipped unless TEST_DATABASE_URL is set.
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text

from app.api import routes_nodes
from app.config import Settings
from app.database import get_db

pytestmark = pytest.mark.asyncio

ADMIN = {"X-Admin-Key": "admin-secret"}


def node_payload(node_id: str, trust_tier: str | None = None) -> dict:
    payload = {
        "node_id": node_id,
        "provider_name": "Operator",
        "endpoint_url": "https://node.example.invalid/v1",
        "model_id": "nvidia/nemotron-3-nano-30b-a3b",
        "paypal_receiver_email": "operator@example.invalid",
        "input_price_per_1m_micros": 40000,
        "output_price_per_1m_micros": 160000,
    }
    if trust_tier:
        payload["trust_tier"] = trust_tier
    return payload


@pytest_asyncio.fixture
async def api(session_factory, monkeypatch):
    monkeypatch.setattr(routes_nodes, "get_settings", lambda: Settings(ADMIN_API_KEY="admin-secret"))
    app = FastAPI()
    app.include_router(routes_nodes.router, prefix="/api/v1")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def node_count(db) -> int:
    return (await db.execute(text("SELECT COUNT(*) FROM compute_nodes"))).scalar_one()


async def test_anyone_can_register_a_probation_node(api, db):
    response = await api.post("/api/v1/nodes", json=node_payload("open-node"))
    assert response.status_code == 201, response.text
    assert response.json()["trust_tier"] == "PROBATION_SPOT"


@pytest.mark.parametrize("trust_tier", ["ANCHOR", "VERIFIED_PROVIDER"])
@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong-key"}])
async def test_trusted_tiers_are_refused_without_the_admin_key(api, db, trust_tier, headers):
    response = await api.post("/api/v1/nodes", json=node_payload("fake-anchor", trust_tier), headers=headers)
    assert response.status_code == 403
    assert await node_count(db) == 0


@pytest.mark.parametrize("trust_tier", ["ANCHOR", "VERIFIED_PROVIDER"])
async def test_admin_can_register_trusted_tiers(api, db, trust_tier):
    response = await api.post("/api/v1/nodes", json=node_payload("trusted-node", trust_tier), headers=ADMIN)
    assert response.status_code == 201, response.text
    assert response.json()["trust_tier"] == trust_tier


async def test_trusted_tiers_are_refused_when_no_admin_key_is_configured(api, db, monkeypatch):
    monkeypatch.setattr(routes_nodes, "get_settings", lambda: Settings(ADMIN_API_KEY=""))
    response = await api.post("/api/v1/nodes", json=node_payload("fake-anchor", "ANCHOR"), headers={"X-Admin-Key": ""})
    assert response.status_code == 403
    assert await node_count(db) == 0
