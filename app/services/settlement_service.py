import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.group import GroupMember
from app.db.models.settlement import Settlement
from app.schemas.settlement import SettlementCreate


async def create_settlement(
    db: AsyncSession,
    group_id: uuid.UUID,
    payer_id: uuid.UUID,
    data: SettlementCreate
) -> Settlement:
    """
    Record a debt payment from payer to receiver within a group.
    Does NOT modify any ExpenseSplit - balance recalculates from this record in real-time.
    """
    # --- Validate both users are members - one query, O(1) set lookup ----------------
    member_ids = await _get_member_ids(db, group_id)

    if payer_id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )
    if data.receiver_id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Receiver is not a member of this group"
        )
    
    # --- Service-level guard - better error message than DB IntegrityError -----------
    if payer_id == data.receiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payer and receiver cannot be the same person"
        )
    
    settlement = Settlement(
        group_id=group_id,
        payer_id=payer_id,
        receiver_id=data.receiver_id,
        amount=data.amount,
        note=data.note
    )
    db.add(settlement)
    await db.commit()

    # Re-fetch first so we have settlement.id for the task
    settlement = await _get_settlement_with_relations(db, settlement.id)

    try:
        from app.tasks.email_tasks import send_settlement_notification
        send_settlement_notification.delay(str(settlement.id))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Failed to queue settlement notification: {exc}")

    return settlement


async def get_group_settlements(
    db: AsyncSession,
    group_id: uuid.UUID,
    requester_id: uuid.UUID
) -> list[Settlement]:
    """
    List all settlements in the group, newest first.
    Any group member can view the full settlement history.
    """
    member_ids = await _get_member_ids(db, group_id)
    if requester_id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )
    
    result = await db.execute(
        select(Settlement)
        .where(Settlement.group_id == group_id)
        .options(
            selectinload(Settlement.payer),
            selectinload(Settlement.receiver)
        )
        .order_by(Settlement.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_settlements(
    db: AsyncSession,
    group_id: uuid.UUID,
    requester_id: uuid.UUID
) -> list[Settlement]:
    """
    List only settlements where the current user is the payer or receiver.
    Useful for a personal settlement history view.
    """
    member_ids = await _get_member_ids(db, group_id)
    if requester_id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )
    
    result = await db.execute(
        select(Settlement)
        .where(
            Settlement.group_id == group_id,
            # OR condition: current user is involved as either party
            (Settlement.payer_id == requester_id) 
            | (Settlement.receiver_id == requester_id)
        )
        .options(
            selectinload(Settlement.payer),
            selectinload(Settlement.receiver)
        )
        .order_by(Settlement.created_at.desc())
    )
    return list(result.scalars().all())


# --- Private helpers -----------------------------------------------------------------

async def _get_member_ids(
    db: AsyncSession,
    group_id: uuid.UUID
) -> set[uuid.UUID]:
    """Fetch all member user_ids for a group into a set for O(1) lookup."""
    result = await db.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )
    return set(result.scalars().all())


async def _get_settlement_with_relations(
    db: AsyncSession,
    settlement_id: uuid.UUID
) -> Settlement:
    """Fetch a settlement with payer and receiver user objects loaded."""
    result = await db.execute(
        select(Settlement)
        .where(Settlement.id == settlement_id)
        .options(
            selectinload(Settlement.payer),
            selectinload(Settlement.receiver)
        )
    )
    settlement = result.scalar_one_or_none()
    if settlement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found"
        )
    return settlement