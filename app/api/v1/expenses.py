import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, get_db
from app.db.models.user import User
from app.schemas.expense import (
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseResponse,
    PayerResponse,
    SplitResponse,
)
from app.services import expense_service

router = APIRouter(prefix="/groups/{group_id}/expenses", tags=["Expenses"])


def _build_expense_response(expense) -> ExpenseResponse:
    """
    Build ExpenseResponse from a fully-loaded Expense ORM object.
    Extracted as a helper to avoid repeating in list and detail endpoints.
    """
    return ExpenseResponse(
        id=expense.id,
        group_id=expense.group_id,
        description=expense.description,
        total_amount=expense.total_amount,
        split_type=expense.split_type,
        date_happened=expense.date_happened,
        created_by=expense.created_by,
        created_at=expense.created_at,
        payers=[
            PayerResponse(
                user_id=p.user_id,
                username=p.user.username,
                amount=p.amount,
            )
            for p in expense.payers
        ],
        splits=[
            SplitResponse(
                user_id=s.user_id,
                username=s.user.username,
                amount=s.amount,
                split_value=s.split_value,
            )
            for s in expense.splits
        ],
    )


@router.post(
    "",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new expense to the group",
)
async def create_expense(
    group_id: uuid.UUID,
    data: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    expense = await expense_service.create_expense(db, group_id, current_user.id, data)
    return _build_expense_response(expense)


@router.get(
    "",
    response_model=ExpenseListResponse,
    summary="List expenses in a group (paginated, newest first)",
)
async def list_expenses(
    group_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    total, expenses = await expense_service.get_group_expenses(
        db, group_id, current_user.id, skip, limit
    )
    return ExpenseListResponse(
        total=total,
        items=[_build_expense_response(e) for e in expenses],
    )


@router.get(
    "/{expense_id}",
    response_model=ExpenseResponse,
    summary="Get expense detail",
)
async def get_expense(
    group_id: uuid.UUID,
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    expense = await expense_service.get_expense_detail(
        db, group_id, expense_id, current_user.id
    )
    return _build_expense_response(expense)


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an expense (creator or group admin only)",
)
async def delete_expense(
    group_id: uuid.UUID,
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    await expense_service.delete_expense(db, group_id, expense_id, current_user.id)