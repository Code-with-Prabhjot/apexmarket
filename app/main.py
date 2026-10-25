"""
ApexMarket: Application Entrypoint & FastAPI Server
Mounts API routers, manages async lifecycle, and provides healthcheck endpoints.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_jobs import router as jobs_router
from app.api.routes_nodes import router as nodes_router
from app.api.routes_telemetry import router as telemetry_router
from app.api.routes_ws import router as ws_router
from app.api.routes_mission_control import router as mission_control_router
from app.config import get_settings
from app.database import close_database_connections

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and graceful shutdown lifecycle."""
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
