import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, get_db
from app.db.models.user import User
from app.schemas.settlement import SettlementCreate, SettlementResponse
from app.services import settlement_service

router = APIRouter(prefix="/groups/{group_id}/settlements", tags=["Settlements"])


def _build_settlement_response(settlement) -> SettlementResponse:
    """Build SettlementResponse from a fully-loaded Settlement ORM object."""
    return SettlementResponse(
        id=settlement.id,
        group_id=settlement.group_id,
        payer_id=settlement.payer_id,
        payer_username=settlement.payer.username,
        receiver_id=settlement.receiver_id,
        receiver_username=settlement.receiver.username,
        amount=settlement.amount,
        note=settlement.note,
        created_at=settlement.created_at
    )


@router.post(
    "",
    response_model=SettlementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a debt payment from the current user to another member"
)
async def create_settlement(
    group_id: uuid.UUID,
    data: SettlementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    settlement = await settlement_service.create_settlement(
        db, group_id, current_user.id, data
    )
    return _build_settlement_response(settlement)


@router.get(
    "",
    response_model=list[SettlementResponse],
    summary="List all settlements in the group (newest first)"
)
async def list_group_settlements(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    settlements = await settlement_service.get_group_settlements(
        db, group_id, current_user.id
    )
    return [_build_settlement_response(s) for s in settlements]


@router.get(
    "/mine",
    response_model=list[SettlementResponse],
    summary="List settlements where the current user is payer or receiver",
)
async def list_my_settlements(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    settlements = await settlement_service.get_user_settlements(
        db, group_id, current_user.id
    )
    return [_build_settlement_response(s) for s in settlements]