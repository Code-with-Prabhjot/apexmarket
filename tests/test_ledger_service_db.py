"""
ApexMarket Test Suite: Ledger Service Integration Tests (PostgreSQL)
Asserts escrow locking, the rolling hourly circuit breaker, verified shred credits,
job settlement, retry idempotency, and that balances always agree with the
double-entry ledger. Skipped unless TEST_DATABASE_URL is set (see tests/conftest.py).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_service import LedgerService

pytestmark = pytest.mark.asyncio


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

async def insert_job(db: AsyncSession, client_id: uuid.UUID, job_id: uuid.UUID, reserved_micros: int) -> None:
    await db.execute(
        text("""
            INSERT INTO batch_jobs (
                job_id, client_id, total_prompts, max_tokens_per_prompt,
                max_cost_ceiling_micros, reserved_escrow_micros
            ) VALUES (:job_id, :client_id, 10, 512, :reserved, :reserved)
        """),
        {"job_id": job_id, "client_id": client_id, "reserved": reserved_micros},
    )


async def insert_shred(db: AsyncSession, job_id: uuid.UUID, node_id: str) -> uuid.UUID:
    shred_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO job_shreds (shred_id, job_id, node_id, prompt_indices)
            VALUES (:shred_id, :job_id, :node_id, ARRAY[0, 1])
        """),
        {"shred_id": shred_id, "job_id": job_id, "node_id": node_id},
    )
    return shred_id


async def client_balances(db: AsyncSession, client_id: uuid.UUID) -> tuple[int, int]:
    row = (
        await db.execute(
            text("SELECT available_balance_micros, locked_escrow_micros FROM clients WHERE client_id = :id"),
            {"id": client_id},
        )
    ).one()
    return row.available_balance_micros, row.locked_escrow_micros


async def node_balances(db: AsyncSession, node_id: str) -> tuple[int, int]:
    row = (
        await db.execute(
            text("SELECT withdrawable_micros, pending_probation_micros FROM compute_nodes WHERE node_id = :id"),
            {"id": node_id},
        )
    ).one()
    return row.withdrawable_micros, row.pending_probation_micros


async def ledger_net(db: AsyncSession, account: str) -> int:
    """Net amount credited to an account minus amount debited from it."""
    result = await db.execute(
        text("""
            SELECT COALESCE(SUM(CASE WHEN credit_account = :account THEN amount_micros ELSE 0 END), 0)
                 - COALESCE(SUM(CASE WHEN debit_account = :account THEN amount_micros ELSE 0 END), 0)
            FROM ledger_entries
            WHERE credit_account = :account OR debit_account = :account
        """),
        {"account": account},
    )
    return int(result.scalar_one())


async def entry_count(db: AsyncSession) -> int:
    return (await db.execute(text("SELECT COUNT(*) FROM ledger_entries"))).scalar_one()


async def lock_escrow_for_new_job(db: AsyncSession, client_id: uuid.UUID, amount_micros: int) -> uuid.UUID:
    job_id = uuid.uuid4()
    await LedgerService.lock_client_escrow(db, client_id, amount_micros, job_id)
    await insert_job(db, client_id, job_id, amount_micros)
    await db.commit()
    return job_id


# -----------------------------------------------------------------------------
# ESCROW LOCK & HOURLY CIRCUIT BREAKER
# -----------------------------------------------------------------------------

async def test_lock_escrow_moves_funds_and_records_entry(db, make_client):
    client_id = await make_client(available_balance_micros=10_000_000)

    await lock_escrow_for_new_job(db, client_id, 4_000_000)

    assert await client_balances(db, client_id) == (6_000_000, 4_000_000)
    assert await ledger_net(db, f"client_escrow:{client_id}") == 4_000_000
    assert await ledger_net(db, f"client_available:{client_id}") == -4_000_000


async def test_lock_escrow_retry_for_same_job_moves_funds_once(db, make_client):
    client_id = await make_client(available_balance_micros=10_000_000)
    job_id = await lock_escrow_for_new_job(db, client_id, 4_000_000)

    assert await LedgerService.lock_client_escrow(db, client_id, 4_000_000, job_id) is True
    await db.commit()

    assert await client_balances(db, client_id) == (6_000_000, 4_000_000)
    assert await entry_count(db) == 1


async def test_lock_escrow_rejects_insufficient_funds(db, make_client):
    client_id = await make_client(available_balance_micros=1_000_000)

    with pytest.raises(ValueError, match="Insufficient funds"):
        await LedgerService.lock_client_escrow(db, client_id, 2_000_000, uuid.uuid4())
    await db.rollback()

    assert await client_balances(db, client_id) == (1_000_000, 0)
    assert await entry_count(db) == 0


async def test_hourly_limit_counts_all_escrow_locked_in_the_last_hour(db, make_client):
    client_id = await make_client(available_balance_micros=10_000_000, hourly_spend_limit_micros=3_000_000)
    await lock_escrow_for_new_job(db, client_id, 2_000_000)

    with pytest.raises(ValueError, match="Hourly spend limit exceeded"):
        await LedgerService.lock_client_escrow(db, client_id, 1_500_000, uuid.uuid4())
    await db.rollback()

    # Exactly reaching the limit is allowed.
    await lock_escrow_for_new_job(db, client_id, 1_000_000)
    assert await client_balances(db, client_id) == (7_000_000, 3_000_000)


async def test_hourly_limit_ignores_escrow_locked_over_an_hour_ago(db, make_client):
    client_id = await make_client(available_balance_micros=10_000_000, hourly_spend_limit_micros=3_000_000)
    await lock_escrow_for_new_job(db, client_id, 3_000_000)
    await db.execute(text("UPDATE ledger_entries SET created_at = NOW() - INTERVAL '2 hours'"))
    await db.commit()

    await lock_escrow_for_new_job(db, client_id, 3_000_000)
    assert await client_balances(db, client_id) == (4_000_000, 6_000_000)


# -----------------------------------------------------------------------------
# VERIFIED SHRED CREDITS
# -----------------------------------------------------------------------------

async def test_shred_credit_moves_escrow_to_node_once(db, make_client, make_node):
    client_id = await make_client(available_balance_micros=10_000_000)
    node_id = await make_node()
    job_id = await lock_escrow_for_new_job(db, client_id, 5_000_000)
    shred_id = await insert_shred(db, job_id, node_id)

    for _ in range(2):  # second call simulates a retry
        await LedgerService.credit_node_verified_shred(
            db, client_id, job_id, shred_id, node_id, shred_cost_micros=1_250_000, is_probation=False
        )
        await db.commit()

    assert await client_balances(db, client_id) == (5_000_000, 3_750_000)
    assert await node_balances(db, node_id) == (1_250_000, 0)
    assert await ledger_net(db, f"node_withdrawable:{node_id}") == 1_250_000


async def test_probation_shred_credit_goes_to_pending_probation(db, make_client, make_node):
    client_id = await make_client(available_balance_micros=10_000_000)
    node_id = await make_node(trust_tier="PROBATION_SPOT")
    job_id = await lock_escrow_for_new_job(db, client_id, 5_000_000)
    shred_id = await insert_shred(db, job_id, node_id)

    await LedgerService.credit_node_verified_shred(
        db, client_id, job_id, shred_id, node_id, shred_cost_micros=800_000, is_probation=True
    )
    await db.commit()

    assert await node_balances(db, node_id) == (0, 800_000)
    assert await ledger_net(db, f"node_probation:{node_id}") == 800_000


# -----------------------------------------------------------------------------
# JOB SETTLEMENT & CONSERVATION
# -----------------------------------------------------------------------------

async def test_job_settlement_conserves_every_micro_dollar(db, make_client, make_node):
    initial_micros = 10_000_000
    client_id = await make_client(available_balance_micros=initial_micros)
    verified_node = await make_node()
    probation_node = await make_node(trust_tier="PROBATION_SPOT")
    job_id = await lock_escrow_for_new_job(db, client_id, 5_000_000)

    for node_id, cost, is_probation in ((verified_node, 1_500_000, False), (probation_node, 1_000_000, True)):
        shred_id = await insert_shred(db, job_id, node_id)
        await LedgerService.credit_node_verified_shred(
            db, client_id, job_id, shred_id, node_id, shred_cost_micros=cost, is_probation=is_probation
        )

    # Baseline $4.00, actual $2.50 -> savings $1.50 -> 10% fee $0.15 -> refund $2.35.
    summary = await LedgerService.release_unused_escrow_and_settle_job(
        db, client_id, job_id,
        total_reserved_micros=5_000_000, actual_settled_micros=2_500_000, baseline_cost_micros=4_000_000,
    )
    await db.commit()

    assert summary["platform_fee_micros"] == 150_000
    assert summary["unused_refunded_micros"] == 2_350_000
    assert await client_balances(db, client_id) == (7_350_000, 0)
    assert await node_balances(db, verified_node) == (1_500_000, 0)
    assert await node_balances(db, probation_node) == (0, 1_000_000)
    assert await ledger_net(db, "platform_revenue") == 150_000

    # Conservation: the client's starting money is fully accounted for.
    available, locked = await client_balances(db, client_id)
    assert available + locked + 1_500_000 + 1_000_000 + 150_000 == initial_micros

    # Balances agree with the ledger.
    assert initial_micros + await ledger_net(db, f"client_available:{client_id}") == available
    assert await ledger_net(db, f"client_escrow:{client_id}") == locked


async def test_job_settlement_retry_does_not_refund_or_charge_twice(db, make_client):
    client_id = await make_client(available_balance_micros=10_000_000)
    job_id = await lock_escrow_for_new_job(db, client_id, 5_000_000)

    # Nothing executed: actual $0 against a $1.00 baseline -> $0.10 fee, $4.90 refund.
    for _ in range(2):
        await LedgerService.release_unused_escrow_and_settle_job(
            db, client_id, job_id,
            total_reserved_micros=5_000_000, actual_settled_micros=0, baseline_cost_micros=1_000_000,
        )
        await db.commit()

    assert await client_balances(db, client_id) == (9_900_000, 0)
    assert await ledger_net(db, "platform_revenue") == 100_000


async def test_platform_fee_is_capped_at_unspent_escrow(db, make_client):
    client_id = await make_client(available_balance_micros=10_000_000)
    job_id = await lock_escrow_for_new_job(db, client_id, 1_000_000)

    # Savings vs baseline would imply a $0.205 fee, but only $0.05 of escrow is unspent.
    summary = await LedgerService.release_unused_escrow_and_settle_job(
        db, client_id, job_id,
        total_reserved_micros=1_000_000, actual_settled_micros=950_000, baseline_cost_micros=3_000_000,
    )
    await db.commit()

    assert summary["platform_fee_micros"] == 50_000
    assert summary["unused_refunded_micros"] == 0
    assert await ledger_net(db, "platform_revenue") == 50_000
