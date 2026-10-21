"""
ApexMarket: Sub-Cent Micro-Dollar Ledger & Double-Entry Accounting Service
Implements strict double-entry ledger math, balance conservation,
SELECT ... FOR UPDATE concurrency locking, and sub-cent remainder accounting.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, Tuple, List
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

settings = get_settings()

MICROS_PER_DOLLAR = 1_000_000
MICROS_PER_CENT = 10_000  # 1 cent = 10,000 micro-dollars


# -----------------------------------------------------------------------------
# PURE MATHEMATICAL FUNCTIONS (ZERO FLOATING POINT ROUNDING)
# -----------------------------------------------------------------------------

def micros_to_usd_str(micros: int) -> str:
    """
    Converts integer micro-dollars to an exact 2-decimal USD string representation,
    strictly rounding down to protect against over-disbursement.
    Example: 1,234,567 micros -> "$1.23"
    """
    if micros < 0:
        raise ValueError(f"micros cannot be negative: {micros}")
    dollars = (Decimal(micros) / Decimal(MICROS_PER_DOLLAR)).quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    )
    return f"{dollars:.2f}"


def usd_to_micros(usd_amount: str | float | Decimal | int) -> int:
    """
    Converts a USD amount (string, float, Decimal) to integer micro-dollars.
    Example: "1.23" -> 1,230,000 micros.
    """
    dec_val = Decimal(str(usd_amount))
    if dec_val < 0:
        raise ValueError(f"USD amount cannot be negative: {usd_amount}")
    return int((dec_val * Decimal(MICROS_PER_DOLLAR)).to_integral_value(rounding=ROUND_DOWN))


def calculate_subcent_split(balance_micros: int) -> Tuple[int, int]:
    """
    Splits an integer micro-dollar balance into:
      1. payable_micros: Whole-cent payable amount (multiples of 10,000 micros)
      2. remainder_micros: Sub-cent remainder to retain in withdrawable balance
    Example: 1,234,567 micros -> payable=1,230,000 ($1.23), remainder=4,567 ($0.004567)
    """
    if balance_micros < 0:
        raise ValueError(f"balance_micros cannot be negative: {balance_micros}")
    payable_micros = (balance_micros // MICROS_PER_CENT) * MICROS_PER_CENT
    remainder_micros = balance_micros % MICROS_PER_CENT
    # Invariant: payable_micros + remainder_micros == balance_micros
    assert payable_micros + remainder_micros == balance_micros
    return payable_micros, remainder_micros


def compute_net_savings_and_fee(
    baseline_cost_micros: int,
    actual_cost_micros: int,
    take_rate_bps: int = 1000,  # 10.00%
) -> Tuple[int, int]:
    """
    Computes gross savings and platform fee based on verified cost reduction.
    Returns: (gross_savings_micros, platform_fee_micros)
    """
    if baseline_cost_micros <= actual_cost_micros:
        return 0, 0
    gross_savings = baseline_cost_micros - actual_cost_micros
    platform_fee = (gross_savings * take_rate_bps) // 10_000
    return gross_savings, platform_fee


# -----------------------------------------------------------------------------
# DATABASE DOUBLE-ENTRY LEDGER SERVICE
# -----------------------------------------------------------------------------

class LedgerService:
    @staticmethod
    async def record_entry(
        db: AsyncSession,
        idempotency_key: str,
        debit_account: str,
        credit_account: str,
        amount_micros: int,
        description: str,
        job_id: Optional[uuid.UUID] = None,
        shred_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """
        Records a double-entry ledger transaction.
        Enforces idempotency: if the idempotency_key already exists, returns existing entry_id.
        The insert uses ON CONFLICT so concurrent writers with the same key cannot both insert.
        """
        if amount_micros <= 0:
            raise ValueError(f"amount_micros must be positive: {amount_micros}")
        if debit_account == credit_account:
            raise ValueError(f"Debit and credit accounts must be distinct: {debit_account}")

        inserted = await db.execute(
            text("""
                INSERT INTO ledger_entries (
                    entry_id, idempotency_key, job_id, shred_id,
                    debit_account, credit_account, amount_micros, description
                ) VALUES (
                    :entry_id, :key, :job_id, :shred_id,
                    :debit_account, :credit_account, :amount_micros, :description
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING entry_id
            """),
            {
                "entry_id": uuid.uuid4(),
                "key": idempotency_key,
                "job_id": job_id,
                "shred_id": shred_id,
                "debit_account": debit_account,
                "credit_account": credit_account,
                "amount_micros": amount_micros,
                "description": description,
            },
        )
        inserted_row = inserted.fetchone()
        if inserted_row:
            return inserted_row[0]

        existing = await db.execute(
            text("SELECT entry_id FROM ledger_entries WHERE idempotency_key = :key"),
            {"key": idempotency_key},
        )
        return existing.scalar_one()

    @staticmethod
    async def lock_client_escrow(
        db: AsyncSession,
        client_id: uuid.UUID,
        required_escrow_micros: int,
        job_id: uuid.UUID,
    ) -> bool:
        """
        Acquires row-level lock on client record with SELECT ... FOR UPDATE.
        Verifies balance and hourly circuit breaker, transfers micro-dollars
        from available_balance_micros to locked_escrow_micros, and writes ledger entry.
        """
        result = await db.execute(
            text("""
                SELECT available_balance_micros, hourly_spend_limit_micros
                FROM clients
                WHERE client_id = :client_id
                FOR UPDATE
            """),
            {"client_id": client_id},
        )
        client = result.fetchone()
        if not client:
            raise ValueError(f"Client {client_id} not found.")

        available, hourly_limit = client.available_balance_micros, client.hourly_spend_limit_micros

        if available < required_escrow_micros:
            raise ValueError(
                f"Insufficient funds: available {available} micros < required {required_escrow_micros} micros."
            )

        if required_escrow_micros > hourly_limit:
            raise ValueError(
                f"Hourly spend limit exceeded: required {required_escrow_micros} micros > limit {hourly_limit} micros."
            )

        # Move available -> locked
        await db.execute(
            text("""
                UPDATE clients
                SET available_balance_micros = available_balance_micros - :amount,
                    locked_escrow_micros = locked_escrow_micros + :amount
                WHERE client_id = :client_id
            """),
            {"amount": required_escrow_micros, "client_id": client_id},
        )

        # Record double-entry transaction
        idempotency_key = f"escrow_lock:{job_id}"
        await LedgerService.record_entry(
            db=db,
            idempotency_key=idempotency_key,
            debit_account=f"client_available:{client_id}",
            credit_account=f"client_escrow:{client_id}",
            amount_micros=required_escrow_micros,
            description=f"Escrow lock for batch job {job_id}",
            job_id=job_id,
        )
        return True

    @staticmethod
    async def credit_node_verified_shred(
        db: AsyncSession,
        client_id: uuid.UUID,
        job_id: uuid.UUID,
        shred_id: uuid.UUID,
        node_id: str,
        shred_cost_micros: int,
        is_probation: bool,
    ) -> None:
        """
        Credits node earnings after successful 5-tier shred verification.
        Debits client_escrow, credits node_probation or node_withdrawable.
        """
        if shred_cost_micros <= 0:
            return

        # Deduct from client's locked escrow
        await db.execute(
            text("""
                UPDATE clients
                SET locked_escrow_micros = locked_escrow_micros - :amount
                WHERE client_id = :client_id
            """),
            {"amount": shred_cost_micros, "client_id": client_id},
        )

        # Credit compute node
        target_column = "pending_probation_micros" if is_probation else "withdrawable_micros"
        target_account = f"node_probation:{node_id}" if is_probation else f"node_withdrawable:{node_id}"

        await db.execute(
            text(f"""
                UPDATE compute_nodes
                SET {target_column} = {target_column} + :amount
                WHERE node_id = :node_id
            """),
            {"amount": shred_cost_micros, "node_id": node_id},
        )

        # Record ledger entry
        idempotency_key = f"shred_credit:{shred_id}:{node_id}"
        await LedgerService.record_entry(
            db=db,
            idempotency_key=idempotency_key,
            debit_account=f"client_escrow:{client_id}",
            credit_account=target_account,
            amount_micros=shred_cost_micros,
            description=f"Verified shred payout for {shred_id} on node {node_id}",
            job_id=job_id,
            shred_id=shred_id,
        )

    @staticmethod
    async def release_unused_escrow_and_settle_job(
        db: AsyncSession,
        client_id: uuid.UUID,
        job_id: uuid.UUID,
        total_reserved_micros: int,
        actual_settled_micros: int,
        baseline_cost_micros: int,
    ) -> Dict[str, int]:
        """
        Finalizes batch job accounting:
          1. Retains platform take-rate fee on net verified savings.
          2. Refunds remaining unspent escrow back to client's available balance.
        """
        unused_micros = total_reserved_micros - actual_settled_micros
        gross_savings, platform_fee = compute_net_savings_and_fee(
            baseline_cost_micros=baseline_cost_micros,
            actual_cost_micros=actual_settled_micros,
            take_rate_bps=settings.PLATFORM_TAKE_RATE_BPS,
        )

        # Adjust client escrow and available balances
        if unused_micros > 0:
            await db.execute(
                text("""
                    UPDATE clients
                    SET locked_escrow_micros = locked_escrow_micros - :unused,
                        available_balance_micros = available_balance_micros + :unused
                    WHERE client_id = :client_id
                """),
                {"unused": unused_micros, "client_id": client_id},
            )

            await LedgerService.record_entry(
                db=db,
                idempotency_key=f"escrow_refund:{job_id}",
                debit_account=f"client_escrow:{client_id}",
                credit_account=f"client_available:{client_id}",
                amount_micros=unused_micros,
                description=f"Unused escrow release for job {job_id}",
                job_id=job_id,
            )

        if platform_fee > 0:
            await LedgerService.record_entry(
                db=db,
                idempotency_key=f"platform_fee:{job_id}",
                debit_account=f"client_available:{client_id}",
                credit_account="platform_revenue",
                amount_micros=platform_fee,
                description=f"Platform 10% take-rate on savings for job {job_id}",
                job_id=job_id,
            )

        return {
            "reserved_micros": total_reserved_micros,
            "actual_cost_micros": actual_settled_micros,
            "unused_refunded_micros": unused_micros,
            "gross_savings_micros": gross_savings,
            "platform_fee_micros": platform_fee,
        }
