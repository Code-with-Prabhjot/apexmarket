"""
ApexMarket: Production Pydantic v2 Schemas
Defines strictly validated data models for batch jobs, prompts, telemetry,
attestation, nodes, ledger accounting, and settlement.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Set
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator


# -----------------------------------------------------------------------------
# ENUM DEFINITIONS
# -----------------------------------------------------------------------------

class WorkloadSensitivity(str, Enum):
    """
    Workload sensitivity level.
    CONFIDENTIAL is the fail-closed default: forces 100% execution through trusted anchor.
    """
    CONFIDENTIAL = "CONFIDENTIAL"
    SYNTHETIC = "SYNTHETIC"
    PUBLIC = "PUBLIC"


class NodeTrustTier(str, Enum):
    """Trust hierarchy for compute providers."""
    ANCHOR = "ANCHOR"
    VERIFIED_PROVIDER = "VERIFIED_PROVIDER"
    PROBATION_SPOT = "PROBATION_SPOT"
    SLASHED = "SLASHED"


class JobStatus(str, Enum):
    """Batch job state machine lifecycle."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL_FAIL = "PARTIAL_FAIL"
    ABORTED_BUDGET = "ABORTED_BUDGET"


class ShredStatus(str, Enum):
    """Execution and verification status for individual prompt shreds."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFIED_PASS = "VERIFIED_PASS"
    VERIFIED_FAIL_REROUTED = "VERIFIED_FAIL_REROUTED"


class PayoutBatchStatus(str, Enum):
    """PayPal batch payout settlement status."""
    CREATED = "CREATED"
    SUBMITTED_PENDING = "SUBMITTED_PENDING"
    COMPLETED = "COMPLETED"
    FAILED_REVERSED = "FAILED_REVERSED"


# -----------------------------------------------------------------------------
# PROMPT & BATCH JOB MODELS
# -----------------------------------------------------------------------------

class InferencePrompt(BaseModel):
    """Individual prompt item inside a batch submission."""
    prompt_index: int = Field(
        ...,
        ge=0,
        description="Zero-indexed position of the prompt within the batch",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=32000,
        description="Prompt text payload, strictly bounded between 1 and 32,000 characters",
    )

    @field_validator("content")
    @classmethod
    def validate_content_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt content cannot consist solely of whitespace.")
        return v


# Backward-compatible alias matching blueprint v3.0 section 3.2
PromptItem = InferencePrompt


class BatchJobCreateRequest(BaseModel):
    """
    Client submission request for an inference batch job.
    Enforces fail-closed CONFIDENTIAL default and hard bounds on prompts and tokens.
    """
    sensitivity: WorkloadSensitivity = Field(
        default=WorkloadSensitivity.CONFIDENTIAL,
        description="Workload privacy classification. Fail-closed default: CONFIDENTIAL.",
    )
    prompts: List[InferencePrompt] = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="List of batch prompts, bounded strictly between 1 and 5,000 items",
    )
    max_tokens_per_prompt: int = Field(
        default=512,
        ge=1,
        le=4096,
        description="Max generation token budget per prompt",
    )
    max_cost_ceiling_micros: int = Field(
        ...,
        gt=0,
        le=100_000_000,
        description="Client-authorized maximum cost ceiling in micro-dollars (up to $100.00)",
    )
    makespan_sla_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=3600.0,
        description="Maximum makespan deadline in seconds for the entire batch",
    )
    target_model: Optional[str] = Field(
        default="meta-llama/Llama-3.1-8B-Instruct",
        description="Target model identifier for inference execution",
    )

    @field_validator("prompts")
    @classmethod
    def validate_unique_prompt_indices(cls, prompts: List[InferencePrompt]) -> List[InferencePrompt]:
        indices: Set[int] = set()
        for p in prompts:
            if p.prompt_index >= 5000:
                raise ValueError(f"prompt_index must be strictly less than 5000, got {p.prompt_index}")
            if p.prompt_index in indices:
                raise ValueError(f"Duplicate prompt_index detected: {p.prompt_index}. All indices must be unique.")
            indices.add(p.prompt_index)
        return prompts


class PromptResultItem(BaseModel):
    """Result of an individual processed prompt after verification and failover handling."""
    prompt_index: int = Field(..., ge=0, le=4999)
    status: str = Field(
        ...,
        description="'COMPLETED_SPOT', 'COMPLETED_ANCHOR_FAILOVER', or 'FAILED'",
    )
    executing_node_id: str = Field(..., min_length=1)
    output_text: str
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    is_simulated: bool = Field(default=False, description="True if generated via fallback mock simulation")
    execution_mode: str = Field(default="LIVE", description="Execution mode tag: LIVE or SIMULATED_MOCK")


class ShredAttestation(BaseModel):
    """
    Cryptographic and empirical attestation record for an executed shred.
    Covers the 5-tier verification pipeline results.
    """
    shred_id: uuid.UUID
    node_id: str = Field(..., min_length=1)
    passed: bool
    measured_input_tokens: int = Field(..., ge=0)
    measured_output_tokens: int = Field(..., ge=0)
    canary_accuracy: float = Field(..., ge=0.0, le=1.0)
    anchor_nll_score: Optional[float] = Field(default=None, ge=0.0)
    nemotron_judge_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    server_hmac_signature: str = Field(..., min_length=1)
    failure_reason: Optional[str] = None


class BatchJobResponse(BaseModel):
    """Full lifecycle status and settlement accounting for a batch job."""
    job_id: uuid.UUID
    client_id: uuid.UUID
    sensitivity: WorkloadSensitivity
    status: JobStatus
    total_prompts: int
    max_tokens_per_prompt: int
    max_cost_ceiling_micros: int
    reserved_escrow_micros: int
    actual_settled_cost_micros: int
    platform_fee_micros: int
    baseline_anchor_cost_micros: int
    baseline_batch_api_cost_micros: int
    total_makespan_ms: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# -----------------------------------------------------------------------------
# TELEMETRY & NODE REGISTRY MODELS
# -----------------------------------------------------------------------------

class NodeTelemetrySnapshot(BaseModel):
    """Point-in-time performance and pricing snapshot for an inference node."""
    node_id: str = Field(..., min_length=1)
    provider_name: str = Field(..., min_length=1)
    endpoint_url: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    trust_tier: NodeTrustTier
    input_price_per_1m_micros: int = Field(..., ge=0)
    output_price_per_1m_micros: int = Field(..., ge=0)
    p95_ttft_ms: float = Field(..., ge=0.0)
    tokens_per_sec: float = Field(..., ge=0.0)
    error_rate_50req: float = Field(..., ge=0.0, le=1.0)
    is_active: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NodeRegistrationRequest(BaseModel):
    """Registration payload for a new or updated compute node."""
    node_id: str = Field(..., min_length=1, max_length=64)
    provider_name: str = Field(..., min_length=1, max_length=128)
    endpoint_url: str = Field(..., min_length=1, max_length=512)
    model_id: str = Field(..., min_length=1, max_length=128)
    trust_tier: NodeTrustTier = Field(default=NodeTrustTier.PROBATION_SPOT)
    paypal_receiver_email: str = Field(..., min_length=5, max_length=255)
    input_price_per_1m_micros: int = Field(..., ge=0)
    output_price_per_1m_micros: int = Field(..., ge=0)
    max_concurrent_requests: int = Field(default=10, ge=1, le=500)


class NodeResponse(BaseModel):
    """Public compute node status and balance representation."""
    node_id: str
    provider_name: str
    endpoint_url: str
    model_id: str
    trust_tier: NodeTrustTier
    paypal_receiver_email: str
    input_price_per_1m_micros: int
    output_price_per_1m_micros: int
    max_concurrent_requests: int
    pending_probation_micros: int
    withdrawable_micros: int
    payout_pending_micros: int
    is_active: bool
    created_at: datetime


# -----------------------------------------------------------------------------
# CLIENT & LEDGER ACCOUNTING MODELS
# -----------------------------------------------------------------------------

class ClientCreateRequest(BaseModel):
    """Payload to register a new API client."""
    organization_name: str = Field(..., min_length=1, max_length=255)
    api_key_hash: str = Field(..., min_length=32, max_length=128)
    paypal_payer_id: Optional[str] = None
    paypal_vault_id: Optional[str] = None
    hourly_spend_limit_micros: int = Field(default=50_000_000, ge=1_000_000)


class ClientBalanceResponse(BaseModel):
    """Current financial ledger state for an enterprise client."""
    client_id: uuid.UUID
    organization_name: str
    available_balance_micros: int = Field(..., ge=0)
    locked_escrow_micros: int = Field(..., ge=0)
    hourly_spend_limit_micros: int = Field(..., ge=0)
    available_balance_usd: str
    locked_escrow_usd: str


class TopUpCreateRequest(BaseModel):
    """Prepaid balance top-up amount; limits are enforced from settings by the service."""
    amount_micros: int = Field(..., gt=0)


class TopUpResponse(BaseModel):
    """State of a prepaid PayPal top-up."""
    topup_id: uuid.UUID
    paypal_order_id: Optional[str] = None
    approve_url: Optional[str] = None
    amount_micros: int
    status: str


class LedgerEntryCreate(BaseModel):
    """Double-entry transaction input model."""
    idempotency_key: str = Field(..., min_length=1)
    job_id: Optional[uuid.UUID] = None
    shred_id: Optional[uuid.UUID] = None
    debit_account: str = Field(..., min_length=1)
    credit_account: str = Field(..., min_length=1)
    amount_micros: int = Field(..., gt=0)
    description: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_distinct_accounts(self) -> "LedgerEntryCreate":
        if self.debit_account == self.credit_account:
            raise ValueError("Debit and credit accounts must be distinct in double-entry bookkeeping.")
        return self


class LedgerEntryResponse(BaseModel):
    """Double-entry transaction receipt model."""
    entry_id: uuid.UUID
    idempotency_key: str
    job_id: Optional[uuid.UUID] = None
    shred_id: Optional[uuid.UUID] = None
    debit_account: str
    credit_account: str
    amount_micros: int
    amount_usd: str
    description: str
    created_at: datetime


# -----------------------------------------------------------------------------
# SETTLEMENT & PAYOUT MODELS
# -----------------------------------------------------------------------------

class PayoutBatchResponse(BaseModel):
    """Summary of a PayPal mass payout batch."""
    batch_id: uuid.UUID
    paypal_batch_id: Optional[str] = None
    status: PayoutBatchStatus
    total_amount_micros: int
    total_amount_usd: str
    total_fee_micros: int
    created_at: datetime
    updated_at: datetime


class PayoutItemResponse(BaseModel):
    """Individual node payout item inside a batch."""
    item_id: uuid.UUID
    batch_id: uuid.UUID
    node_id: str
    amount_paid_micros: int
    amount_paid_usd: str
    remainder_carried_micros: int
    paypal_item_id: Optional[str] = None
    item_status: str
