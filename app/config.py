"""
ApexMarket: Configuration and Environment Settings
Implements typed, production-grade settings via Pydantic Settings v2.
"""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Runtime
    APP_ENV: str = Field(default="development", description="Runtime environment: development, test, production")
    LOG_LEVEL: str = Field(default="INFO", description="Logging verbosity level")
    HOST: str = Field(default="127.0.0.1", description="FastAPI host binding")
    PORT: int = Field(default=8000, description="FastAPI port binding")
    ADMIN_API_KEY: str = Field(default="apex-demo-2026", description="Required for Mission Control sandbox admin actions")
    DEMO_CHAOS_ENABLED: bool = Field(default=True, description="Explicit opt-in to mutate the local mock provider")
    DEMO_MOCK_PROVIDER_URL: str = Field(default="http://127.0.0.1:9002", description="Local mock provider chaos target")

    # Nebius Token Factory (Reference Anchor & Verification Judge)
    NEBIUS_API_KEY: str = Field(default="", description="Nebius Token Factory API key")
    NEBIUS_BASE_URL: str = Field(
        default="https://api.tokenfactory.nebius.com/v1",
        description="Nebius Token Factory OpenAI-compatible base URL",
    )
    NEBIUS_ANCHOR_MODEL_ID: str = Field(
        default="nvidia/nemotron-3-nano-30b-a3b",
        description="Reference anchor model ID on Nebius",
    )
    NEBIUS_JUDGE_MODEL_ID: str = Field(
        default="nvidia/nemotron-4-340b-instruct",
        description="Tier-5 semantic arbiter judge model ID on Nebius",
    )

    # Secondary / Arbitrage Providers
    SECONDARY_API_KEY: str = Field(default="", description="Secondary API key for benchmark comparison")
    SECONDARY_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Secondary OpenAI-compatible base URL",
    )
    BENCHMARK_MODEL_ID: str = Field(
        default="nvidia/nemotron-3-nano-30b-a3b",
        description="Default model ID for empirical benchmarks",
    )

    # PayPal Agentic Commerce Integration
    PAYPAL_MODE: str = Field(default="sandbox", description="PayPal environment mode: sandbox or live")
    PAYPAL_CLIENT_ID: str = Field(default="", description="PayPal REST API Client ID")
    PAYPAL_CLIENT_SECRET: str = Field(default="", description="PayPal REST API Secret")
    PAYPAL_BASE_URL: str = Field(
        default="https://api-m.sandbox.paypal.com",
        description="PayPal REST API Base URL",
    )
    PAYPAL_WEBHOOK_ID: str = Field(default="", description="PayPal Webhook ID for signature verification")

    # Database & Redis Infrastructure
    POSTGRES_USER: str = Field(default="postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: str = Field(default="postgres_secure_password", description="PostgreSQL password")
    POSTGRES_DB: str = Field(default="apexmarket", description="PostgreSQL database name")
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres_secure_password@127.0.0.1:5432/apexmarket",
        description="Async SQLAlchemy database connection string",
    )
    REDIS_PASSWORD: str = Field(default="redis_secure_password", description="Redis authentication password")
    REDIS_URL: str = Field(
        default="redis://:redis_secure_password@127.0.0.1:6379/0",
        description="Redis connection URL",
    )

    # Security & Attestation Keys
    HMAC_SECRET_KEY: str = Field(
        default="apexmarket_super_secure_deterministic_hmac_secret_key_2026",
        description="Secret key for CSPRNG anchor sampling seed and per-shred server HMAC attestation",
    )

    # Financial & Circuit Breaker Limits (in Micro-Dollars: $1.00 = 1,000,000 micros)
    DEFAULT_HOURLY_SPEND_LIMIT_MICROS: int = Field(
        default=50_000_000,  # $50.00 / hour default circuit breaker
        description="Max allowed client spend per rolling hour before circuit breaker aborts",
    )
    MIN_PAYOUT_THRESHOLD_MICROS: int = Field(
        default=10_000_000,  # $10.00 min threshold
        description="Minimum withdrawable balance required to trigger automatic PayPal mass payout",
    )
    PROBATION_ESCROW_DAYS: int = Field(
        default=7,
        description="Rolling escrow hold in days for new untrusted spot nodes",
    )
    PLATFORM_TAKE_RATE_BPS: int = Field(
        default=1000,  # 10.00% (1000 basis points)
        description="ApexMarket platform take rate on net verified cost savings",
    )
    CANARY_OVERHEAD_RATE: float = Field(
        default=0.04,  # 4% canary injection
        description="Percentage of synthetic canary prompts injected per shred",
    )
    ANCHOR_AUDIT_RATE: float = Field(
        default=0.05,  # 5% anchor sampling
        description="Percentage of real prompts re-executed against the trusted Nebius anchor",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance."""
    return Settings()
