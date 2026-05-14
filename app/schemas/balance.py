import uuid
from decimal import Decimal

from pydantic import BaseModel


class UserNetBalance(BaseModel):
    """Net balance for one user in the group."""
    user_id: uuid.UUID
    username: str
    # positive = this user is owed money (creditor)
    # negative = this user owes money (debtor)
    # zero     = fully settled
    net_amount: Decimal


class DebtEntry(BaseModel):
    """A single simplified debt: from_user owes to_user this amount."""
    from_user_id: uuid.UUID
    from_username: str
    to_user_id: uuid.UUID
    to_username: str
    amount: Decimal


class GroupBalanceResponse(BaseModel):
    group_id: uuid.UUID
    # Per-user net balance (sorted: creditors first, then debtors)
    net_balances: list[UserNetBalance]
    # Minimum set of transactions to settle all debts
    simplified_debts: list[DebtEntry]
    # True when everyone's net balance is zero (or within rounding threshold)
    is_settled: bool