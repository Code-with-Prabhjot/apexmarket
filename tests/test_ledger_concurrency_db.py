"""
ApexMarket Test Suite: Ledger Concurrency Tests (PostgreSQL)
Fires simultaneous escrow locks at one client from separate sessions and asserts the
SELECT ... FOR UPDATE row lock prevents overdrafts, hourly-limit bypasses, and
double locks. Skipped unless TEST_DATABASE_URL is set (see tests/conftest.py).
"""

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.ledger_service import LedgerService

pytestmark = pytest.mark.asyncio

CONCURRENT_REQUESTS = 10


async def try_lock_escrow(
    session_factory: async_sessionmaker[AsyncSession],
    client_id: uuid.UUID,
    amount_micros: int,
    job_id: uuid.UUID,
) -> bool:
    """Locks escrow and inserts the job in its own transaction, like one API request."""
    async with session_factory() as session:
        try:
            await LedgerService.lock_client_escrow(session, client_id, amount_micros, job_id)
            await session.execute(
                text("""
                    INSERT INTO batch_jobs (job_id, client_id, total_prompts, max_tokens_per_prompt, max_cost_ceiling_micros)
                    VALUES (:job_id, :client_id, 1, 1, :amount)
                    ON CONFLICT (job_id) DO NOTHING
                """),
                {"job_id": job_id, "client_id": client_id, "amount": amount_micros},
            )
            await session.commit()
            return True
        except ValueError:
            await session.rollback()
            return False


async def client_state(db: AsyncSession, client_id: uuid.UUID) -> tuple[int, int, int]:
    row = (
        await db.execute(
            text("""
                SELECT c.available_balance_micros, c.locked_escrow_micros,
                       (SELECT COUNT(*) FROM ledger_entries) AS entries
                FROM clients c WHERE c.client_id = :id
            """),
            {"id": client_id},
        )
    ).one()
    return row.available_balance_micros, row.locked_escrow_micros, row.entries


async def test_concurrent_locks_cannot_overdraw_balance(db, session_factory, make_client):
    client_id = await make_client(available_balance_micros=5_000_000, hourly_spend_limit_micros=100_000_000)

    results = await asyncio.gather(*(
        try_lock_escrow(session_factory, client_id, 1_000_000, uuid.uuid4())
        for _ in range(CONCURRENT_REQUESTS)
    ))

    assert results.count(True) == 5
    assert await client_state(db, client_id) == (0, 5_000_000, 5)


async def test_concurrent_locks_cannot_bypass_hourly_limit(db, session_factory, make_client):
    client_id = await make_client(available_balance_micros=10_000_000, hourly_spend_limit_micros=3_000_000)

    results = await asyncio.gather(*(
        try_lock_escrow(session_factory, client_id, 1_000_000, uuid.uuid4())
        for _ in range(CONCURRENT_REQUESTS)
    ))

    assert results.count(True) == 3
    assert await client_state(db, client_id) == (7_000_000, 3_000_000, 3)


async def test_concurrent_retries_for_one_job_lock_once(db, session_factory, make_client):
    client_id = await make_client(available_balance_micros=10_000_000)
    job_id = uuid.uuid4()

    results = await asyncio.gather(*(
        try_lock_escrow(session_factory, client_id, 2_000_000, job_id)
        for _ in range(CONCURRENT_REQUESTS)
    ))

    assert all(results)
    assert await client_state(db, client_id) == (8_000_000, 2_000_000, 1)
