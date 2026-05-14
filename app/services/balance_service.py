import uuid
from collections import defaultdict
from decimal import ROUND_DOWN, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.expense import Expense
from app.db.models.group import GroupMember
from app.db.models.settlement import Settlement
from app.schemas.balance import DebtEntry, GroupBalanceResponse, UserNetBalance

# Amounts smaller than half a cent are treated as zero.
# Prevents Decimal rounding noise from creating phantom debts.
_THRESHOLD = Decimal("0.005")


async def get_group_balances(
    db: AsyncSession,
    group_id: uuid.UUID,
    requester_id: uuid.UUID,
) -> GroupBalanceResponse:
    """
    Full balance report for a group:
      1. Verify requester is a member.
      2. Load members, expenses, settlements from DB.
      3. Calculate per-user net balances (pure).
      4. Run debt simplification algorithm (pure).
      5. Enrich with usernames and return.
    """
    # --- Step 1: Load members (with user info for display) ---------------------
    members_result = await db.execute(
        select(GroupMember)
        .where(GroupMember.group_id == group_id)
        .options(selectinload(GroupMember.user))
    )
    members = members_result.scalars().all()

    member_ids = {m.user_id for m in members}
    if requester_id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Build lookup map: user_id -> username (used when building response)
    user_map: dict[uuid.UUID, str] = {m.user_id: m.user.username for m in members}

    # --- Step 2: Load all non-deleted expenses with payers and splits ----------
    expenses_result = await db.execute(
        select(Expense)
        .where(
            Expense.group_id == group_id,
            Expense.is_deleted.is_(False),
        )
        .options(
            selectinload(Expense.payers),
            selectinload(Expense.splits),
        )
    )
    expenses = expenses_result.scalars().all()

    # --- Step 3: Load all settlements for the group ----------------------------
    settlements_result = await db.execute(
        select(Settlement).where(Settlement.group_id == group_id)
    )
    settlements = settlements_result.scalars().all()

    # --- Step 4: Calculate net balances (pure function) ------------------------
    net = _calculate_net_balances(expenses, settlements, member_ids)

    # --- Step 5: Simplify debts (pure function) --------------------------------
    debt_tuples = _simplify_debts(net)

    # --- Step 6: Build response ------------------------------------------------
    net_balances = [
        UserNetBalance(
            user_id=uid,
            username=user_map[uid],
            net_amount=net.get(uid, Decimal("0")).quantize(Decimal("0.01")),
        )
        for uid in member_ids
    ]
    # Sort: creditors (positive) first, then debtors (negative), then settled
    net_balances.sort(key=lambda x: x.net_amount, reverse=True)

    simplified_debts = [
        DebtEntry(
            from_user_id=debtor_id,
            from_username=user_map[debtor_id],
            to_user_id=creditor_id,
            to_username=user_map[creditor_id],
            amount=amount,
        )
        for debtor_id, creditor_id, amount in debt_tuples
    ]

    is_settled = len(simplified_debts) == 0

    return GroupBalanceResponse(
        group_id=group_id,
        net_balances=net_balances,
        simplified_debts=simplified_debts,
        is_settled=is_settled,
    )


# --- Pure functions - no DB access, fully unit-testable -----------------------

def _calculate_net_balances(
    expenses: list,
    settlements: list,
    member_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Decimal]:
    """
    Calculate net balance for every member.

    Formula per user:
      net = sum(ExpensePayer.amount)     # cash paid upfront
           - sum(ExpenseSplit.amount)    # share of expenses owed
           + sum(Settlement paid out)   # debt payments made
           - sum(Settlement received)   # debt payments received

    Positive net → user is owed money (creditor).
    Negative net → user owes money (debtor).
    """
    # Initialize all members at zero so everyone appears in the result,
    # even those with no expenses.
    net: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for uid in member_ids:
        net[uid] = Decimal("0")

    for expense in expenses:
        for payer in expense.payers:
            net[payer.user_id] += payer.amount   # paid cash → owed back
        for split in expense.splits:
            net[split.user_id] -= split.amount   # owes this share

    for settlement in settlements:
        # payer paid off their debt → reduce what they owe
        net[settlement.payer_id] += settlement.amount
        # receiver got paid → reduce what they're owed
        net[settlement.receiver_id] -= settlement.amount

    return dict(net)


def _simplify_debts(
    net_balances: dict[uuid.UUID, Decimal],
) -> list[tuple[uuid.UUID, uuid.UUID, Decimal]]:
    """
    Greedy Min Cash Flow algorithm.

    Strategy: always match the largest creditor with the largest debtor.
    Each iteration settles at least one person completely → at most n-1 transactions.

    Time:  O(n²) - n = number of members with non-zero balance (always small)
    Space: O(n)

    Returns list of (debtor_id, creditor_id, amount).
    """
    # Working copy - filter out near-zero balances to avoid phantom debts
    balances: dict[uuid.UUID, Decimal] = {
        uid: amt
        for uid, amt in net_balances.items()
        if abs(amt) >= _THRESHOLD
    }

    results: list[tuple[uuid.UUID, uuid.UUID, Decimal]] = []

    while balances:
        # Find who is owed the most and who owes the most
        creditor_id = max(balances, key=lambda uid: balances[uid])
        debtor_id   = min(balances, key=lambda uid: balances[uid])

        credit = balances[creditor_id]  # positive
        debt   = balances[debtor_id]    # negative

        # Both near zero - all settled
        if credit < _THRESHOLD and abs(debt) < _THRESHOLD:
            break

        # Settle the smaller of the two amounts
        settle_amount = min(credit, abs(debt)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        results.append((debtor_id, creditor_id, settle_amount))

        # Update balances
        balances[creditor_id] -= settle_amount
        balances[debtor_id]   += settle_amount

        # Remove fully settled users for next iteration
        balances = {
            uid: amt
            for uid, amt in balances.items()
            if abs(amt) >= _THRESHOLD
        }

    return results