import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Settlement(Base):
    """
    Records a debt payment between two members of a group.
    Settlements do NOT modify ExpenseSplit records.
    Balance is recalculated in real-time as: sum(splits) - sum(settlements).
    This keeps a full audit trail - every transaction is traceable.
    """
    __tablename__ = "settlements"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    # payer = person who is paying off their debt
    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    # receiver = person who is owed money and receives the payment
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # DB-level constraint: amount must be positive, payer != receiver
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_amount_positive"),
        CheckConstraint("payer_id != receiver_id", name="ck_settlement_different_users")
    )

    # Two FKs to same table - must specify foreign_keys explicitly
    group: Mapped["Group"] = relationship("Group", back_populates="settlements") # type: ignore # noqa: F821
    payer: Mapped["User"] = relationship( # type: ignore # noqa: F821
        "User",
        foreign_keys=[payer_id],
        back_populates="settlements_paid"
    )
    receiver: Mapped["User"] = relationship( # type: ignore # noqa: F821
        "User",
        foreign_keys=[receiver_id],
        back_populates="settlements_received"
    )