"""
ApexMarket: Compute Node Registry & Payout API Routes
Manages provider registration, trust tiers, balances, and node lifecycle.
"""

from datetime import datetime, timezone
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import NodeRegistrationRequest, NodeResponse, NodeTrustTier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["Compute Nodes"])

DEFAULT_SEEDED_NODES: List[Dict[str, Any]] = [
    {
        "node_id": "nebius-nemotron-anchor",
        "provider_name": "Nebius Token Factory",
        "model_id": "nvidia/nemotron-3-nano-30b-a3b",
        "trust_tier": "ANCHOR",
        "input_price_per_1m_micros": 60000,
        "output_price_per_1m_micros": 240000,
        "max_concurrent_requests": 20,
        "endpoint_url": "https://api.tokenfactory.nebius.com/v1",
        "paypal_receiver_email": "anchor@nebius.com",
    },
    {
        "node_id": "runpod-h100-spot-01",
        "provider_name": "RunPod PCIe H100",
        "model_id": "nvidia/nemotron-3-nano-30b-a3b",
        "trust_tier": "PROBATION_SPOT",
        "input_price_per_1m_micros": 40000,
        "output_price_per_1m_micros": 180000,
        "max_concurrent_requests": 10,
        "endpoint_url": "http://localhost:8001/v1",
        "paypal_receiver_email": "spot1@runpod.io",
    },
    {
        "node_id": "community-spot-02",
        "provider_name": "Community H100 Spot",
        "model_id": "nvidia/nemotron-3-nano-30b-a3b",
        "trust_tier": "PROBATION_SPOT",
        "input_price_per_1m_micros": 35000,
        "output_price_per_1m_micros": 160000,
        "max_concurrent_requests": 8,
        "endpoint_url": "http://localhost:8002/v1",
        "paypal_receiver_email": "spot2@community.io",
    },
]


def _build_default_node_responses() -> List[NodeResponse]:
    now = datetime.now(timezone.utc)
    return [
        NodeResponse(
            node_id=n["node_id"],
            provider_name=n["provider_name"],
            endpoint_url=n["endpoint_url"],
            model_id=n["model_id"],
            trust_tier=NodeTrustTier(n["trust_tier"]),
            paypal_receiver_email=n["paypal_receiver_email"],
            input_price_per_1m_micros=n["input_price_per_1m_micros"],
            output_price_per_1m_micros=n["output_price_per_1m_micros"],
            max_concurrent_requests=n["max_concurrent_requests"],
            pending_probation_micros=0,
            withdrawable_micros=0,
            payout_pending_micros=0,
            is_active=True,
            created_at=now,
        )
        for n in DEFAULT_SEEDED_NODES
    ]


@router.post(
    "",
    response_model=NodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new compute node",
)
async def register_node(
    request: NodeRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Registers an inference node into the compute network."""
    existing = await db.execute(
        text("SELECT node_id FROM compute_nodes WHERE node_id = :node_id"),
        {"node_id": request.node_id},
    )
    if existing.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node '{request.node_id}' is already registered.",
        )

    await db.execute(
        text("""
            INSERT INTO compute_nodes (
                node_id, provider_name, endpoint_url, model_id,
                trust_tier, paypal_receiver_email, input_price_per_1m_micros,
                output_price_per_1m_micros, max_concurrent_requests
            ) VALUES (
                :node_id, :provider_name, :endpoint_url, :model_id,
                :trust_tier, :paypal_receiver_email, :input_price,
                :output_price, :max_concurrent
            )
        """),
        {
            "node_id": request.node_id,
            "provider_name": request.provider_name,
            "endpoint_url": request.endpoint_url,
            "model_id": request.model_id,
            "trust_tier": request.trust_tier.value,
            "paypal_receiver_email": request.paypal_receiver_email,
            "input_price": request.input_price_per_1m_micros,
            "output_price": request.output_price_per_1m_micros,
            "max_concurrent": request.max_concurrent_requests,
        },
    )
    await db.commit()

    result = await db.execute(
        text("SELECT * FROM compute_nodes WHERE node_id = :node_id"),
        {"node_id": request.node_id},
    )
    row = result.fetchone()
    return NodeResponse(
        node_id=row.node_id,
        provider_name=row.provider_name,
        endpoint_url=row.endpoint_url,
        model_id=row.model_id,
        trust_tier=NodeTrustTier(row.trust_tier),
        paypal_receiver_email=row.paypal_receiver_email,
        input_price_per_1m_micros=row.input_price_per_1m_micros,
        output_price_per_1m_micros=row.output_price_per_1m_micros,
        max_concurrent_requests=row.max_concurrent_requests,
        pending_probation_micros=row.pending_probation_micros,
        withdrawable_micros=row.withdrawable_micros,
        payout_pending_micros=row.payout_pending_micros,
        is_active=row.is_active,
        created_at=row.created_at,
    )


@router.get(
    "",
    response_model=List[NodeResponse],
    summary="List all registered compute nodes",
)
async def list_nodes(db: AsyncSession = Depends(get_db)):
    """Lists all active and inactive compute nodes with balance information."""
    try:
        result = await db.execute(
            text("SELECT * FROM compute_nodes ORDER BY created_at DESC")
        )
        rows = result.fetchall()
        if rows:
            return [
                NodeResponse(
                    node_id=row.node_id,
                    provider_name=row.provider_name,
                    endpoint_url=row.endpoint_url,
                    model_id=row.model_id,
                    trust_tier=NodeTrustTier(row.trust_tier),
                    paypal_receiver_email=row.paypal_receiver_email,
                    input_price_per_1m_micros=row.input_price_per_1m_micros,
                    output_price_per_1m_micros=row.output_price_per_1m_micros,
                    max_concurrent_requests=row.max_concurrent_requests,
                    pending_probation_micros=row.pending_probation_micros,
                    withdrawable_micros=row.withdrawable_micros,
                    payout_pending_micros=row.payout_pending_micros,
                    is_active=row.is_active,
                    created_at=row.created_at,
                )
                for row in rows
            ]
    except Exception as exc:
        logger.warning("Database query failed in list_nodes: %s", exc)

    return _build_default_node_responses()


@router.get(
    "/{node_id}",
    response_model=NodeResponse,
    summary="Get node details",
)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves single compute node record."""
    try:
        result = await db.execute(
            text("SELECT * FROM compute_nodes WHERE node_id = :node_id"),
            {"node_id": node_id},
        )
        row = result.fetchone()
        if row:
            return NodeResponse(
                node_id=row.node_id,
                provider_name=row.provider_name,
                endpoint_url=row.endpoint_url,
                model_id=row.model_id,
                trust_tier=NodeTrustTier(row.trust_tier),
                paypal_receiver_email=row.paypal_receiver_email,
                input_price_per_1m_micros=row.input_price_per_1m_micros,
                output_price_per_1m_micros=row.output_price_per_1m_micros,
                max_concurrent_requests=row.max_concurrent_requests,
                pending_probation_micros=row.pending_probation_micros,
                withdrawable_micros=row.withdrawable_micros,
                payout_pending_micros=row.payout_pending_micros,
                is_active=row.is_active,
                created_at=row.created_at,
            )
    except Exception as exc:
        logger.warning("Database query failed in get_node(%s): %s", node_id, exc)

    fallback = next((n for n in DEFAULT_SEEDED_NODES if n["node_id"] == node_id), None)
    if fallback:
        return NodeResponse(
            node_id=fallback["node_id"],
            provider_name=fallback["provider_name"],
            endpoint_url=fallback["endpoint_url"],
            model_id=fallback["model_id"],
            trust_tier=NodeTrustTier(fallback["trust_tier"]),
            paypal_receiver_email=fallback["paypal_receiver_email"],
            input_price_per_1m_micros=fallback["input_price_per_1m_micros"],
            output_price_per_1m_micros=fallback["output_price_per_1m_micros"],
            max_concurrent_requests=fallback["max_concurrent_requests"],
            pending_probation_micros=0,
            withdrawable_micros=0,
            payout_pending_micros=0,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Node '{node_id}' not found.",
    )
