"""
ApexMarket Test Suite: Probation Earnings Release (PostgreSQL)
Asserts probation credits move to withdrawable only after the hold period, exactly once,
with balances matching the ledger, and that the release endpoint requires the admin key.
Skipped unless TEST_DATABASE_URL is set.
"""

import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text

from app.api import routes_mission_control
from app.api.routes_settlement import router as settlement_router
from app.config import Settings
from app.database import get_db
from app.services.ledger_service import LedgerService
from tests.test_ledger_service_db import insert_shred, ledger_net, lock_escrow_for_new_job, node_balances

pytestmark = pytest.mark.asyncio

HOLD_DAYS = 7


async def credit_probation(db, client_id, node_id, amount_micros: int, days_ago: int) -> None:
    job_id = await lock_escrow_for_new_job(db, client_id, amount_micros)
    shred_id = await insert_shred(db, job_id, node_id)
    await LedgerService.credit_node_verified_shred(
        db, client_id, job_id, shred_id, node_id, shred_cost_micros=amount_micros, is_probation=True
    )
    await db.execute(
        text("UPDATE ledger_entries SET created_at = NOW() - make_interval(days => :days) WHERE shred_id = :shred"),
        {"days": days_ago, "shred": shred_id},
    )
    await db.commit()


async def test_only_credits_past_the_hold_are_released_once(db, make_client, make_node):
    client_id = await make_client(available_balance_micros=10_000_000)
    node_id = await make_node(trust_tier="PROBATION_SPOT")
    await credit_probation(db, client_id, node_id, 1_250_000, days_ago=HOLD_DAYS + 1)
    await credit_probation(db, client_id, node_id, 400_000, days_ago=2)

    first = await LedgerService.release_matured_probation(db, hold_days=HOLD_DAYS)
    await db.commit()
    second = await LedgerService.release_matured_probation(db, hold_days=HOLD_DAYS)
    await db.commit()

    assert first == {"released_entries": 1, "released_micros": 1_250_000}
    assert second == {"released_entries": 0, "released_micros": 0}
    assert await node_balances(db, node_id) == (1_250_000, 400_000)
    assert await ledger_net(db, f"node_withdrawable:{node_id}") == 1_250_000
    assert await ledger_net(db, f"node_probation:{node_id}") == 400_000


async def test_concurrent_releases_do_not_double_release(session_factory, db, make_client, make_node):
    client_id = await make_client(available_balance_micros=10_000_000)
    node_id = await make_node(trust_tier="PROBATION_SPOT")
    await credit_probation(db, client_id, node_id, 900_000, days_ago=HOLD_DAYS + 3)

    async def release_in_own_session() -> dict:
        async with session_factory() as session:
            result = await LedgerService.release_matured_probation(session, hold_days=HOLD_DAYS)
            await session.commit()
            return result

    results = await asyncio.gather(*(release_in_own_session() for _ in range(5)))

    assert sum(r["released_micros"] for r in results) == 900_000
    assert await node_balances(db, node_id) == (900_000, 0)


@pytest_asyncio.fixture
async def admin_api(session_factory, monkeypatch):
    monkeypatch.setattr(routes_mission_control, "get_settings", lambda: Settings(ADMIN_API_KEY="admin-secret"))
    app = FastAPI()
    app.include_router(settlement_router, prefix="/api/v1")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_release_endpoint_requires_admin_key(admin_api, db, make_client, make_node):
    client_id = await make_client(available_balance_micros=10_000_000)
    node_id = await make_node(trust_tier="PROBATION_SPOT")
    await credit_probation(db, client_id, node_id, 600_000, days_ago=HOLD_DAYS + 1)

    denied = await admin_api.post("/api/v1/ledger/probation/release")
    assert denied.status_code == 403
    assert await node_balances(db, node_id) == (0, 600_000)

    allowed = await admin_api.post("/api/v1/ledger/probation/release", headers={"X-Admin-Key": "admin-secret"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"released_entries": 1, "released_micros": 600_000}
    assert await node_balances(db, node_id) == (600_000, 0)
