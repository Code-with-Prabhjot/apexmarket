"""
ApexMarket Test Suite: Pydantic v2 Schema Validation Tests
Asserts input validation constraints, fail-closed defaults, and security boundaries.
"""

import uuid
import pytest
from pydantic import ValidationError

from app.schemas import (
    BatchJobCreateRequest,
    InferencePrompt,
    PromptItem,
    ShredAttestation,
    WorkloadSensitivity,
    NodeTrustTier,
    NodeRegistrationRequest,
    LedgerEntryCreate,
)


def test_workload_sensitivity_fail_closed_default():
    """Confirms that BatchJobCreateRequest defaults to CONFIDENTIAL for privacy safety."""
    req = BatchJobCreateRequest(
        prompts=[InferencePrompt(prompt_index=0, content="Analyze revenue metrics.")],
        max_cost_ceiling_micros=1_000_000,
    )
    assert req.sensitivity == WorkloadSensitivity.CONFIDENTIAL
    assert req.sensitivity.value == "CONFIDENTIAL"


def test_reject_more_than_5000_prompts():
    """Asserts that batches with > 5000 prompts are strictly rejected."""
    prompts = [
        InferencePrompt(prompt_index=i, content=f"Prompt #{i}")
        for i in range(5001)
    ]
    with pytest.raises(ValidationError) as exc_info:
        BatchJobCreateRequest(
            prompts=prompts,
            max_cost_ceiling_micros=10_000_000,
        )
    errors = str(exc_info.value)
    assert "List should have at most 5000 items" in errors or "5000" in errors


def test_reject_zero_prompts():
    """Asserts that batches with 0 prompts are strictly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        BatchJobCreateRequest(
            prompts=[],
            max_cost_ceiling_micros=10_000_000,
        )
    assert "at least 1 item" in str(exc_info.value) or "min_length" in str(exc_info.value)


def test_prompt_content_length_boundaries():
    """Asserts bounds on individual prompt string length (1 to 32,000 characters)."""
    # Valid: 1 char
    p_min = InferencePrompt(prompt_index=0, content="A")
    assert p_min.content == "A"

    # Valid: 32,000 chars
    p_max = InferencePrompt(prompt_index=1, content="x" * 32000)
    assert len(p_max.content) == 32000

    # Invalid: 32,001 chars
    with pytest.raises(ValidationError):
        InferencePrompt(prompt_index=2, content="x" * 32001)

    # Invalid: empty string
    with pytest.raises(ValidationError):
        InferencePrompt(prompt_index=3, content="")

    # Invalid: whitespace only
    with pytest.raises(ValidationError):
        InferencePrompt(prompt_index=4, content="   \n\t  ")

    # Invalid: Unicode control characters
    with pytest.raises(ValidationError):
        InferencePrompt(prompt_index=5, content="Prompt with null\x00byte")

    with pytest.raises(ValidationError):
        InferencePrompt(prompt_index=6, content="Prompt with bell\x07char")

    with pytest.raises(ValidationError):
        InferencePrompt(prompt_index=7, content="Prompt with backspace\x08char")


def test_reject_duplicate_prompt_indices():
    """Asserts that duplicate prompt_index values are rejected to prevent state corruption."""
    prompts = [
        InferencePrompt(prompt_index=0, content="Prompt zero"),
        InferencePrompt(prompt_index=0, content="Another prompt with index zero"),
    ]
    with pytest.raises(ValidationError) as exc_info:
        BatchJobCreateRequest(
            prompts=prompts,
            max_cost_ceiling_micros=1_000_000,
        )
    assert "Duplicate prompt_index detected" in str(exc_info.value)


def test_max_tokens_per_prompt_constraints():
    """Asserts max_tokens_per_prompt is bounded between 1 and 4096."""
    # Valid default
    req = BatchJobCreateRequest(
        prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
        max_cost_ceiling_micros=1_000_000,
    )
    assert req.max_tokens_per_prompt == 512

    # Valid boundaries
    req_1 = BatchJobCreateRequest(
        prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
        max_cost_ceiling_micros=1_000_000,
        max_tokens_per_prompt=1,
    )
    assert req_1.max_tokens_per_prompt == 1

    req_4096 = BatchJobCreateRequest(
        prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
        max_cost_ceiling_micros=1_000_000,
        max_tokens_per_prompt=4096,
    )
    assert req_4096.max_tokens_per_prompt == 4096

    # Invalid: 0
    with pytest.raises(ValidationError):
        BatchJobCreateRequest(
            prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
            max_cost_ceiling_micros=1_000_000,
            max_tokens_per_prompt=0,
        )

    # Invalid: 4097
    with pytest.raises(ValidationError):
        BatchJobCreateRequest(
            prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
            max_cost_ceiling_micros=1_000_000,
            max_tokens_per_prompt=4097,
        )


def test_cost_ceiling_bounds():
    """Asserts micro-dollar cost ceiling must be positive and <= $100.00 (100,000,000 micros)."""
    # Invalid: 0
    with pytest.raises(ValidationError):
        BatchJobCreateRequest(
            prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
            max_cost_ceiling_micros=0,
        )

    # Invalid: negative
    with pytest.raises(ValidationError):
        BatchJobCreateRequest(
            prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
            max_cost_ceiling_micros=-500,
        )

    # Invalid: exceeds $100
    with pytest.raises(ValidationError):
        BatchJobCreateRequest(
            prompts=[InferencePrompt(prompt_index=0, content="Test prompt")],
            max_cost_ceiling_micros=100_000_001,
        )


def test_shred_attestation_validation():
    """Validates canary accuracy and HMAC signature constraints on ShredAttestation."""
    shred_id = uuid.uuid4()

    # Valid attestation
    att = ShredAttestation(
        shred_id=shred_id,
        node_id="nebius-anchor-01",
        passed=True,
        measured_input_tokens=150,
        measured_output_tokens=256,
        canary_accuracy=1.0,
        anchor_nll_score=1.42,
        nemotron_judge_score=9.5,
        server_hmac_signature="abcdef0123456789abcdef0123456789",
    )
    assert att.passed is True
    assert att.canary_accuracy == 1.0

    # Invalid canary accuracy > 1.0
    with pytest.raises(ValidationError):
        ShredAttestation(
            shred_id=shred_id,
            node_id="nebius-anchor-01",
            passed=True,
            measured_input_tokens=150,
            measured_output_tokens=256,
            canary_accuracy=1.05,
            server_hmac_signature="sig",
        )


def test_ledger_entry_distinct_accounts():
    """Asserts that debit and credit accounts must be distinct in double-entry bookkeeping."""
    # Valid
    entry = LedgerEntryCreate(
        idempotency_key="tx-123",
        debit_account="client_available:client_1",
        credit_account="client_escrow:client_1",
        amount_micros=500_000,
        description="Escrow lock",
    )
    assert entry.amount_micros == 500_000

    # Invalid: same account for debit and credit
    with pytest.raises(ValidationError) as exc_info:
        LedgerEntryCreate(
            idempotency_key="tx-124",
            debit_account="client_available:client_1",
            credit_account="client_available:client_1",
            amount_micros=500_000,
            description="Invalid self-transfer",
        )
    assert "Debit and credit accounts must be distinct" in str(exc_info.value)
