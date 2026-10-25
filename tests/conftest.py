"""
ApexMarket Test Suite: Shared PostgreSQL Fixtures for Ledger Integration Tests
Tests that use these fixtures run against a real PostgreSQL database named by the
TEST_DATABASE_URL environment variable (postgresql+asyncpg://...). They are skipped
when it is not set. The database is wiped between tests, so never point it at real data.
"""

import os
import uuid
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
LEDGER_TABLES = (
    "paypal_topups, payout_items, payout_batches, ledger_entries, job_shreds, batch_jobs, compute_nodes, clients"
)

_schema_applied = False


async def _apply_schema_once() -> None:
    """Applies sql/schema.sql (idempotent) the first time a database test runs."""
    global _schema_applied
    if _schema_applied:
        return
    raw_dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(raw_dsn)
    try:
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        await conn.close()
    _schema_applied = True


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Yields a sessionmaker bound to a clean test database."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set; skipping PostgreSQL integration test.")

    await _apply_schema_once()
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {LEDGER_TABLES} CASCADE"))

    try:
        yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yields a single session on the clean test database."""
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def make_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[uuid.UUID]]:
    """Returns a helper that inserts a committed client and returns its client_id."""

    async def _make_client(
        available_balance_micros: int = 100_000_000,
        hourly_spend_limit_micros: int = 50_000_000,
    ) -> uuid.UUID:
        client_id = uuid.uuid4()
        async with session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO clients (
                        client_id, organization_name, api_key_hash,
                        available_balance_micros, hourly_spend_limit_micros
                    ) VALUES (
                        :client_id, 'Test Client', :key_hash, :available, :hourly_limit
                    )
                """),
                {
                    "client_id": client_id,
                    "key_hash": uuid.uuid4().hex,
                    "available": available_balance_micros,
                    "hourly_limit": hourly_spend_limit_micros,
                },
            )
            await session.commit()
        return client_id

    return _make_client


@pytest_asyncio.fixture
async def make_node(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[str]]:
    """Returns a helper that inserts a committed compute node and returns its node_id."""

    async def _make_node(trust_tier: str = "VERIFIED_PROVIDER") -> str:
        node_id = f"test-node-{uuid.uuid4().hex[:8]}"
        async with session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO compute_nodes (
                        node_id, provider_name, endpoint_url, model_id, trust_tier,
                        paypal_receiver_email, input_price_per_1m_micros, output_price_per_1m_micros
                    ) VALUES (
                        :node_id, 'Test Provider', 'https://example.invalid/v1', 'test-model',
                        CAST(:trust_tier AS node_trust_tier), 'node@example.invalid', 60000, 240000
                    )
                """),
                {"node_id": node_id, "trust_tier": trust_tier},
            )
            await session.commit()
        return node_id

    return _make_node
