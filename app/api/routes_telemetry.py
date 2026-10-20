"""
ApexMarket: Telemetry & Quality Metrics API Routes
Provides live snapshots of rolling TTFT, throughput, and error rates across all nodes.
"""

from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_redis_client
from app.schemas import NodeTelemetrySnapshot
from app.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Monitoring"])


@router.get(
    "",
    response_model=List[NodeTelemetrySnapshot],
    summary="Get live telemetry snapshots for all active nodes",
)
async def get_all_telemetry(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """Returns real-time rolling metrics (TTFT, TPS, error rates) for all active compute nodes."""
    return await TelemetryService.get_all_snapshots(db=db, redis=redis)


@router.get(
    "/{node_id}",
    response_model=Dict[str, float],
    summary="Get 50-request rolling window metrics for a specific node",
)
async def get_node_telemetry(
    node_id: str,
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """Calculates p50, p95 TTFT, generation speed, and error rate for a specific node from Redis."""
    health = await TelemetryService.get_node_health(redis=redis, node_id=node_id)
    return health
