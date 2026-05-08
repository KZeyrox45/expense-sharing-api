import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SplitType(str, enum.Enum):
    """
    equal: Divide total equally among all members in splits list
    exact: Each member owes a specific fixed amount
    percentage: Each member owes a percentage of total (must sum to 100)
    shares: Each member has shares (e.g. 2:1:1), amounts calculated proportionally
    """
    equal = "equal"
    exact = "exact"
    percentage = "percentage"
    shares = "shares"


class Expense(Base):
    __tablename__ = "expenses"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True          # Heavy query: GET /groups/{id}/expenses filters by group_id
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    # Numeric(precision, scale): precision=total digits, scale=decimal digits
    # Numeric(12, 2) supports up to 9,999,999,999.99
    # NEVER use Float for monetary values - binary float arithmetic is imprecise
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    split_type: Mapped[SplitType] = mapped_column(
        Enum(SplitType, name="split_type"),
        nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    # date_happened = when the expense happened (user-provided)
    # created_at (from Base) = when the record was inserted
    date_happened: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="expenses") # type: ignore # noqa: F821
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by]) # type: ignore # noqa: F821
    payers: Mapped[list["ExpensePayer"]] = relationship(
        "ExpensePayer",
        back_populates="expense",
        cascade="all, delete-orphan",  # Delete payers when expense deleted
    )
    splits: Mapped[list["ExpenseSplit"]] = relationship(
        "ExpenseSplit",
        back_populates="expense",
        cascade="all, delete-orphan",
    )


class ExpensePayer(Base):
    """
    Who actually paid cash for this expense.
    Multiple people can share the upfront payment.
    Example: A paid 200k, B paid 100k for a 300k dinner.
    """
    __tablename__ = "expense_payers"

    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    # How much this person paid upfront
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relationships
    expense: Mapped["Expense"] = relationship("Expense", back_populates="payers")
    user: Mapped["User"] = relationship("User", back_populates="expense_payers") # type: ignore # noqa: F821


class ExpenseSplit(Base):
    """
    How much each person owes for this expense (after split calculation).
    This is the OUTPUT of the split algorithm - stored for fast balance queries.
    """
    __tablename__ = "expense_splits"

    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    # Calculated amount this user owes (always populated regardless of split_type)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Raw input value - meaning depends on split_type:
    #   equal:      NULL (not needed, calculated from total/count)
    #   exact:      same as amount
    #   percentage: the percentage value (e.g. 33.33)
    #   shares:     the share count (e.g. 2 in a 2:1:1 split)
    split_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),     # 4 decimal places for percentage precision
        nullable=True
    )

    # Relationships
    expense: Mapped["Expense"] = relationship("Expense", back_populates="splits")
    user: Mapped["User"] = relationship("User", back_populates="expense_splits")  # type: ignore # noqa: F821
