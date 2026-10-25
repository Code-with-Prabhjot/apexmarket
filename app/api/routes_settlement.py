"""
ApexMarket: Node Settlement Admin API Routes
Releases matured probation earnings so new nodes become payable after their hold.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_mission_control import require_admin
from app.config import get_settings
from app.database import get_db
from app.services.ledger_service import LedgerService

router = APIRouter(tags=["Settlement"])


@router.post(
    "/ledger/probation/release",
    dependencies=[Depends(require_admin)],
    summary="Release matured probation earnings",
)
async def release_probation(db: AsyncSession = Depends(get_db)):
    """Moves probation credits older than PROBATION_ESCROW_DAYS to node withdrawable balances."""
    result = await LedgerService.release_matured_probation(db, hold_days=get_settings().PROBATION_ESCROW_DAYS)
    await db.commit()
    return result
