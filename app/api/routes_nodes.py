"""
ApexMarket: Compute Node Registry & Payout API Routes
Manages provider registration, trust tiers, balances, and node lifecycle.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import NodeRegistrationRequest, NodeResponse, NodeTrustTier

router = APIRouter(prefix="/nodes", tags=["Compute Nodes"])


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
    result = await db.execute(
        text("SELECT * FROM compute_nodes ORDER BY created_at DESC")
    )
    rows = result.fetchall()
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


@router.get(
    "/{node_id}",
    response_model=NodeResponse,
    summary="Get node details",
)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves single compute node record."""
    result = await db.execute(
        text("SELECT * FROM compute_nodes WHERE node_id = :node_id"),
        {"node_id": node_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found.",
        )
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
