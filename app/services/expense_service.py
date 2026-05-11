import uuid
from decimal import ROUND_DOWN, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.expense import Expense, ExpensePayer, ExpenseSplit, SplitType
from app.db.models.group import GroupMember
from app.schemas.expense import ExpenseCreate, SplitInput


async def create_expense(
    db: AsyncSession,
    group_id: uuid.UUID,
    creator_id: uuid.UUID,
    data: ExpenseCreate
) -> Expense:
    # --- Step 1: Fetch all member IDs once - O(1) lookup later --------------------
    member_ids = await _get_member_ids(db, group_id)

    if creator_id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )
    
    # --- Step 2: Validate all payer and split users are group members -------------
    for payer in data.payers:
        if payer.user_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payer {payer.user_id} is not a member of this group",
            )
    for split in data.splits:
        if split.user_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Split user {split.user_id} is not a member of this group",
            )
        
    # --- Step 3: Validate payer amounts sum == total_amount -----------------------
    payer_total = sum(p.amount for p in data.payers)
    if payer_total != data.total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payer amounts sum to {payer_total}, expected {data.total_amount}",
        )
    
    # --- Step 4: Calculate split amounts (pure function, raises ValueError) -------
    try:
        split_results = _calculate_splits(data.total_amount, data.split_type, data.splits)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    # --- Step 5: Insert Expense + payers + splits in one transaction --------------
    expense = Expense(
        group_id=group_id,
        description=data.description,
        total_amount=data.total_amount,
        split_type=data.split_type,
        created_by=creator_id,
        date_happened=data.date_happened,
    )
    db.add(expense)
    # flush() to get expense.id without committing
    # so all three inserts share one atomic transaction
    await db.flush()

    for payer in data.payers:
        db.add(ExpensePayer(
            expense_id=expense.id,
            user_id=payer.user_id,
            amount=payer.amount,
        ))

    for user_id, amount, raw_value in split_results:
        db.add(ExpenseSplit(
            expense_id=expense.id,
            user_id=user_id,
            amount=amount,
            split_value=raw_value,
        ))

    await db.commit()

    # Re-fetch with all relationships loaded for the response
    return await _get_expense_with_relations(db, expense.id)


async def get_group_expenses(
    db: AsyncSession,
    group_id: uuid.UUID,
    requester_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[int, list[Expense]]:
    """Returns (total_count, page_of_expenses). Only non-deleted expenses."""
    member_ids = await _get_member_ids(db, group_id)
    if requester_id not in member_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this group")

    base_filter = (Expense.group_id == group_id, Expense.is_deleted.is_(False))

    # Count query - separate from data query for accuracy
    count_result = await db.execute(
        select(func.count(Expense.id)).where(*base_filter)
    )
    total = count_result.scalar_one()

    # Data query with pagination
    result = await db.execute(
        select(Expense)
        .where(*base_filter)
        .options(
            selectinload(Expense.payers).selectinload(ExpensePayer.user),
            selectinload(Expense.splits).selectinload(ExpenseSplit.user),
        )
        .order_by(Expense.date_happened.desc(), Expense.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return total, list(result.scalars().all())


async def get_expense_detail(
    db: AsyncSession,
    group_id: uuid.UUID,
    expense_id: uuid.UUID,
    requester_id: uuid.UUID,
) -> Expense:
    member_ids = await _get_member_ids(db, group_id)
    if requester_id not in member_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this group")

    expense = await _get_expense_with_relations(db, expense_id)

    if expense is None or expense.group_id != group_id or expense.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    return expense


async def delete_expense(
    db: AsyncSession,
    group_id: uuid.UUID,
    expense_id: uuid.UUID,
    requester_id: uuid.UUID,
) -> None:
    """
    Soft delete - set is_deleted=True instead of physical DELETE.
    Only the creator or a group admin may delete.
    """
    expense = await _get_expense_with_relations(db, expense_id)

    if expense is None or expense.group_id != group_id or expense.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    # Check requester is either the creator or a group admin
    is_creator = expense.created_by == requester_id

    if not is_creator:
        result = await db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == requester_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this group")
        from app.db.models.group import MemberRole
        if membership.role != MemberRole.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the expense creator or a group admin can delete this expense",
            )

    expense.is_deleted = True
    await db.commit()


# --- Private helpers ----------------------------------------------------------

async def _get_member_ids(db: AsyncSession, group_id: uuid.UUID) -> set[uuid.UUID]:
    """Fetch all member user_ids for a group into a Python set for O(1) lookup."""
    result = await db.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )
    return set(result.scalars().all())


async def _get_expense_with_relations(
    db: AsyncSession,
    expense_id: uuid.UUID,
) -> Expense | None:
    """Fetch an expense with payers and splits (and their users) loaded."""
    result = await db.execute(
        select(Expense)
        .where(Expense.id == expense_id)
        .options(
            # Two-level load: Expense.payers → ExpensePayer.user
            selectinload(Expense.payers).selectinload(ExpensePayer.user),
            selectinload(Expense.splits).selectinload(ExpenseSplit.user),
        )
    )
    return result.scalar_one_or_none()


def _calculate_splits(
    total: Decimal,
    split_type: SplitType,
    splits_input: list[SplitInput],
) -> list[tuple[uuid.UUID, Decimal, Decimal | None]]:
    """
    Pure function - no DB access, fully unit-testable.

    Returns list of (user_id, calculated_amount, raw_split_value).
    calculated_amount is always in 2 decimal places.
    The last person always absorbs rounding remainder to guarantee sum == total.

    Raises ValueError on invalid input (caller converts to HTTPException).
    """
    TWO_PLACES = Decimal("0.01")

    if split_type == SplitType.equal:
        count = len(splits_input)
        per_person = (total / count).quantize(TWO_PLACES, rounding=ROUND_DOWN)
        remainder = total - per_person * count

        results = []
        for i, s in enumerate(splits_input):
            # Last person absorbs the remainder to prevent penny disappearing
            amount = per_person + remainder if i == count - 1 else per_person
            results.append((s.user_id, amount, None))
        return results

    elif split_type == SplitType.exact:
        split_sum = sum(s.value for s in splits_input)  # type: ignore[union-attr]
        if split_sum != total:
            raise ValueError(
                f"Exact split amounts sum to {split_sum}, expected {total}"
            )
        return [(s.user_id, s.value, s.value) for s in splits_input]  # type: ignore[union-attr]

    elif split_type == SplitType.percentage:
        pct_sum = sum(s.value for s in splits_input)  # type: ignore[union-attr]
        # Allow small floating-point tolerance - use exact Decimal comparison
        if pct_sum != Decimal("100"):
            raise ValueError(
                f"Percentages must sum to exactly 100, got {pct_sum}"
            )

        amounts: list[Decimal] = []
        for s in splits_input[:-1]:
            amount = (total * s.value / Decimal("100")).quantize(  # type: ignore[union-attr]
                TWO_PLACES, rounding=ROUND_DOWN
            )
            amounts.append(amount)
        # Last person gets the remainder
        amounts.append(total - sum(amounts))

        return [
            (s.user_id, amt, s.value)
            for s, amt in zip(splits_input, amounts)
        ]

    elif split_type == SplitType.shares:
        total_shares = sum(s.value for s in splits_input)  # type: ignore[union-attr]
        if total_shares <= 0:
            raise ValueError("Total shares must be greater than 0")

        amounts = []
        for s in splits_input[:-1]:
            amount = (total * s.value / total_shares).quantize(  # type: ignore[union-attr]
                TWO_PLACES, rounding=ROUND_DOWN
            )
            amounts.append(amount)
        amounts.append(total - sum(amounts))

        return [
            (s.user_id, amt, s.value)
            for s, amt in zip(splits_input, amounts)
        ]

    else:
        raise ValueError(f"Unknown split_type: {split_type}")