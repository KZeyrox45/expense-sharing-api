import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, get_db
from app.db.models.user import User
from app.schemas.group import (
    GroupCreate,
    GroupDetailResponse,
    GroupResponse,
    InviteMemberRequest,
    MemberResponse
)
from app.schemas.balance import GroupBalanceResponse
from app.services import group_service, balance_service

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.post(
    "",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new group"
)
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    group = await group_service.create_group(db, current_user.id, data)
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        created_by=group.created_by,
        member_count=1,     # Creator is the only member at this point
        created_at=group.created_at
    )


@router.get(
    "",
    response_model=list[GroupResponse],
    summary="List all groups the current user belongs to"
)
async def list_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    groups = await group_service.get_user_groups(db, current_user.id)
    return [
        GroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            created_by=g.created_by,
            member_count=len(g.members),    # Loaded via selectinload in service
            created_at=g.created_at
        )
        for g in groups
    ]


@router.get(
    "/{group_id}",
    response_model=GroupDetailResponse,
    summary="Get group detail including full member list"
)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    group = await group_service.get_group_detail(db, group_id, current_user.id)
    return GroupDetailResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        created_by=group.created_by,
        member_count=len(group.members),
        created_at=group.created_at,
        members=[
            MemberResponse(
                user_id=m.user_id,
                username=m.user.username,
                email=m.user.email,
                role=m.role,
                joined_at=m.joined_at
            )
            for m in group.members
        ]
    )


@router.post(
    "/{group_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to the group by email (admin only)"
)
async def invite_member(
    group_id: uuid.UUID,
    data: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    membership = await group_service.invite_member(
        db, group_id, current_user.id, data.email
    )
    # membership.user is loaded by the service via selectinload
    return MemberResponse(
        user_id=membership.user_id,
        username=membership.user.username,
        email=membership.user.email,
        role=membership.role,
        joined_at=membership.joined_at
    )


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the group (admin only)"
)
async def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    await group_service.remove_member(db, group_id, user_id, current_user.id)


@router.delete(
    "/{group_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave the group voluntarily"
)
async def leave_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    await group_service.leave_group(db, group_id, current_user.id)


@router.get(
    "/{group_id}/balances",
    response_model=GroupBalanceResponse,
    summary="Get net balances and simplified debt transactions for a group",
)
async def get_group_balances(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await balance_service.get_group_balances(db, group_id, current_user.id)