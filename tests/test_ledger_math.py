"""
ApexMarket Test Suite: Sub-Cent Micro-Dollar Ledger Math & Conservation Tests
Asserts integer micro-dollar arithmetic, sub-cent truncation,
USD formatting, and mathematical balance conservation across debits and credits.
"""

from decimal import Decimal
import pytest

from app.services.ledger_service import (
    micros_to_usd_str,
    usd_to_micros,
    calculate_subcent_split,
    compute_net_savings_and_fee,
    MICROS_PER_DOLLAR,
    MICROS_PER_CENT,
)


def test_micros_to_usd_str_formatting():
    """Asserts exact 2-decimal string representation with strict downward rounding."""
    # Exact dollars
    assert micros_to_usd_str(1_000_000) == "1.00"
    assert micros_to_usd_str(10_000_000) == "10.00"
    assert micros_to_usd_str(0) == "0.00"

    # Exact cents
    assert micros_to_usd_str(1_230_000) == "1.23"
    assert micros_to_usd_str(490_000) == "0.49"

    # Sub-cent amounts: must truncate down, never round up!
    # $1.239999 should format to "1.23", NOT "1.24"
    assert micros_to_usd_str(1_239_999) == "1.23"
    assert micros_to_usd_str(9_999) == "0.00"
    assert micros_to_usd_str(10_001) == "0.01"

    # Negative value must raise ValueError
    with pytest.raises(ValueError):
        micros_to_usd_str(-1)


def test_usd_to_micros_conversion():
    """Asserts accurate micro-dollar integer conversion from various types."""
    assert usd_to_micros("1.00") == 1_000_000
    assert usd_to_micros("1.23") == 1_230_000
    assert usd_to_micros("0.05") == 50_000
    assert usd_to_micros(Decimal("20.50")) == 20_500_000
    assert usd_to_micros(10) == 10_000_000

    # Negative check
    with pytest.raises(ValueError):
        usd_to_micros("-5.00")


def test_subcent_split_downward_rounding_and_remainder():
    """
    Asserts sub-cent split:
    - payable_micros is a strict multiple of 10,000 (whole cents)
    - remainder_micros is strictly < 10,000
    - payable_micros + remainder_micros == original balance
    """
    test_cases = [
        0,
        1,
        9_999,
        10_000,
        10_001,
        1_234_567,
        10_000_000,
        50_999_999,
    ]

    for balance in test_cases:
        payable, remainder = calculate_subcent_split(balance)

        # Invariant 1: Conservation
        assert payable + remainder == balance

        # Invariant 2: Payable is a whole cent multiple
        assert payable % MICROS_PER_CENT == 0

        # Invariant 3: Remainder is strictly sub-cent
        assert 0 <= remainder < MICROS_PER_CENT


def test_balance_conservation_in_escrow_and_settlement():
    """
    Simulates a multi-node batch job lifecycle and asserts strict micro-dollar conservation:
    Total Reserved Escrow == Actual Settled Cost + Unused Escrow Refunded.
    """
    reserved_escrow = 5_000_000  # $5.00 authorized
    actual_settled = 3_420_150    # $3.420150 actual cost

    unused_refund = reserved_escrow - actual_settled
    assert unused_refund == 1_579_850

    # Conservation check
    assert actual_settled + unused_refund == reserved_escrow

    # Sub-cent payout check on node side
    payable, remainder = calculate_subcent_split(actual_settled)
    assert payable == 3_420_000  # $3.42 paid via PayPal
    assert remainder == 150       # $0.000150 stays in withdrawable balance
    assert payable + remainder == actual_settled


def test_platform_take_rate_savings_conservation():
    """
    Verifies platform 10% take-rate on verified savings:
    Baseline: $1.00 (1,000,000 micros)
    Actual Cost: $0.70 (700,000 micros)
    Gross Savings: $0.30 (300,000 micros)
    Platform Take-Rate (10%): $0.03 (30,000 micros)
    Net Client Savings: $0.27 (270,000 micros)
    """
    baseline_micros = 1_000_000
    actual_micros = 700_000

    gross_savings, platform_fee = compute_net_savings_and_fee(
        baseline_cost_micros=baseline_micros,
        actual_cost_micros=actual_micros,
        take_rate_bps=1000,  # 10%
    )

    assert gross_savings == 300_000
    assert platform_fee == 30_000
    net_client_savings = gross_savings - platform_fee
    assert net_client_savings == 270_000

    # Global conservation invariant:
    # Actual compute cost + Platform fee + Net client savings == Baseline Anchor cost
    assert actual_micros + platform_fee + net_client_savings == baseline_micros


def test_zero_savings_when_actual_exceeds_baseline():
    """Verifies that platform fee is 0 when actual cost >= baseline cost."""
    baseline = 500_000
    actual = 600_000  # Failover cost higher than baseline

    gross_savings, fee = compute_net_savings_and_fee(baseline, actual, take_rate_bps=1000)
    assert gross_savings == 0
    assert fee == 0
