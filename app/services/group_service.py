import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.group import Group, GroupMember, MemberRole
from app.db.models.user import User
from app.schemas.group import GroupCreate


async def create_group(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: GroupCreate
) -> Group:
    """
    Create a new group and automatically add the creator as admin.
    Uses flush() to get the group.id before committing,
    so both inserts share one transaction.
    """
    group = Group(
        name=data.name,
        description=data.description,
        created_by=user_id
    )
    db.add(group)
    # flush() sends INSERT to DB and populates group.id without committing.
    # Needed so we can reference group.id in the GroupMember insert below.
    await db.flush()

    # Creator is automatically the first admin
    membership = GroupMember(
        group_id=group.id,
        user_id=user_id,
        role=MemberRole.admin
    )
    db.add(membership)
    await db.commit()
    await db.refresh(group)
    return group


async def get_user_groups(
    db: AsyncSession,
    user_id: uuid.UUID
) -> list[Group]:
    """
    Return all groups the user belongs to, with members loaded for count.
    Ordered newest first.
    """
    stmt = (
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user_id)
        # Load members so router can compute len(group.members) without extra queries
        .options(selectinload(Group.members))
        .order_by(Group.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_group_detail(
    db: AsyncSession,
    group_id: uuid.UUID,
    user_id: uuid.UUID
) -> Group:
    """
    Return group with full member list (including each member's user data).
    Raises 403 if user is not a member (intentionally - see module docstring).
    """
    await _require_membership(db, group_id, user_id)

    stmt = (
        select(Group)
        .where(Group.id == group_id)
        .options(
            # Two-level eager load: Group.members -> GroupMember.user
            # selectinload runs 2 separate queries instead of a JOIN
            # to avoid row duplication with one-to-many
            selectinload(Group.members).selectinload(GroupMember.user)
        )
    )
    result = await db.execute(stmt)
    group = result.scalar_one_or_none()

    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


async def invite_member(
    db: AsyncSession,
    group_id: uuid.UUID,
    requester_id: uuid.UUID,
    email: str
) -> GroupMember:
    """
    Add a user (found by email) to the group.
    Only admins can invite. Returns the new membership with user data loaded.
    """
    await _require_role(db, group_id, requester_id, MemberRole.admin)

    # Find target user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found with that email address"
        )
    
    # Prevent duplicate membership
    existing = await _get_membership(db, group_id, user.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this group"
        )
    
    membership = GroupMember(
        group_id=group_id,
        user_id=user.id,
        role=MemberRole.member
    )
    db.add(membership)
    await db.commit()

    # Re-fetch with user relationship loaded for the response
    stmt = (
        select(GroupMember)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user.id
        )
        .options(selectinload(GroupMember.user))
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def remove_member(
    db: AsyncSession,
    group_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requester_id: uuid.UUID
) -> None:
    """
    Remove a member from the group (admin only).
    Blocks removal of the last admin to prevent orphaned groups.
    """
    await _require_role(db, group_id, requester_id, MemberRole.admin)

    target = await _get_membership(db, group_id, target_user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user is not a member of this group",
        )

    # Guard: cannot remove the last admin
    if target.role == MemberRole.admin:
        admin_count = await _count_admins(db, group_id)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the only admin. Promote another member first.",
            )

    await db.delete(target)
    await db.commit()


async def leave_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Allow a user to voluntarily leave a group.
    Blocks departure if the user is the sole remaining admin.
    """
    membership = await _get_membership(db, group_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a member of this group",
        )

    if membership.role == MemberRole.admin:
        admin_count = await _count_admins(db, group_id)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are the only admin. Promote another member before leaving.",
            )

    await db.delete(membership)
    await db.commit()


# --- Private helpers ---------------------------------------------------------

async def _get_membership(
    db: AsyncSession,
    group_id: uuid.UUID,
    user_id: uuid.UUID
) -> GroupMember | None:
    """Fetch a GroupMember record, or None if not found."""
    result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _require_membership(
    db: AsyncSession,
    group_id: uuid.UUID,
    user_id: uuid.UUID
) -> GroupMember:
    """
    Raise 403 if the user is not a member of the group.
    Intentionally returns 403 even when the group does not exist,
    this prevents leaking whether a group ID is valid to non-members.
    """
    membership = await _get_membership(db, group_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )
    return membership


async def _require_role(
    db: AsyncSession,
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MemberRole
) -> GroupMember:
    """Raise 403 if the user does not hold the required role."""
    membership = await _require_membership(db, group_id, user_id)
    if membership.role != role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires '{role.value}' role"
        )
    return membership


async def _count_admins(db: AsyncSession, group_id: uuid.UUID) -> int:
    """Count the number of admins in a group."""
    result = await db.execute(
        select(func.count(GroupMember.user_id)).where(
            GroupMember.group_id == group_id,
            GroupMember.role == MemberRole.admin
        )
    )
    return result.scalar_one()