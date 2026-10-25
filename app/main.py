"""
ApexMarket: Application Entrypoint & FastAPI Server
Mounts API routers, manages async lifecycle, and provides healthcheck endpoints.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes_jobs import router as jobs_router
from app.api.routes_nodes import router as nodes_router, DEFAULT_SEEDED_NODES
from app.api.routes_telemetry import router as telemetry_router
from app.api.routes_ws import router as ws_router
from app.api.routes_mission_control import router as mission_control_router
from app.config import get_settings
from app.database import AsyncSessionLocal, close_database_connections

logger = logging.getLogger(__name__)
settings = get_settings()


async def seed_default_nodes_if_empty() -> None:
    """
    On application startup, checks whether the compute_nodes table contains zero records.
    If empty, automatically seeds default nodes (Nebius Anchor and Spot workers)
    so the dashboard topology, active provider counters, and telemetry light up immediately.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM compute_nodes"))
            count = result.scalar() or 0
            if count == 0:
                logger.info("Auto-seeding compute_nodes table with 3 default nodes.")
                for node in DEFAULT_SEEDED_NODES:
                    try:
                        await session.execute(
                            text("""
                                INSERT INTO compute_nodes (
                                    node_id, provider_name, endpoint_url, model_id,
                                    trust_tier, paypal_receiver_email, input_price_per_1m_micros,
                                    output_price_per_1m_micros, max_concurrent_requests
                                ) VALUES (
                                    :node_id, :provider_name, :endpoint_url, :model_id,
                                    CAST(:trust_tier AS node_trust_tier), :paypal_receiver_email,
                                    :input_price_per_1m_micros, :output_price_per_1m_micros,
                                    :max_concurrent_requests
                                )
                                ON CONFLICT (node_id) DO NOTHING
                            """),
                            node,
                        )
                    except Exception:
                        await session.rollback()
                        await session.execute(
                            text("""
                                INSERT INTO compute_nodes (
                                    node_id, provider_name, endpoint_url, model_id,
                                    trust_tier, paypal_receiver_email, input_price_per_1m_micros,
                                    output_price_per_1m_micros, max_concurrent_requests
                                ) VALUES (
                                    :node_id, :provider_name, :endpoint_url, :model_id,
                                    :trust_tier, :paypal_receiver_email,
                                    :input_price_per_1m_micros, :output_price_per_1m_micros,
                                    :max_concurrent_requests
                                )
                                ON CONFLICT (node_id) DO NOTHING
                            """),
                            node,
                        )
                await session.commit()
    except Exception as exc:
        logger.warning(
            "Startup auto-seeding skipped (database may be offline or initializing): %s",
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and graceful shutdown lifecycle."""
    await seed_default_nodes_if_empty()
    yield
    await close_database_connections()


app = FastAPI(
    title="ApexMarket",
    description="Empirical Multi-Provider Inference Arbitrage & Verified Escrow Settlement Engine",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router Registrations
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(nodes_router, prefix="/api/v1")
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(ws_router)
app.include_router(mission_control_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """System health check endpoint."""
    return {
        "status": "HEALTHY",
        "service": "apexmarket",
        "version": "3.0.0",
        "environment": settings.APP_ENV,
    }
