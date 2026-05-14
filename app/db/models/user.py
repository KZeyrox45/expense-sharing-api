from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,     # Index for fast lookup during login
        nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Relationships - defined after other models exist
    # back_populates must match the attribute name on the other side
    group_memberships: Mapped[list["GroupMember"]] = relationship( # type: ignore # noqa: F821
        "GroupMember",
        back_populates="user",
        cascade="all, delete-orphan",  # Delete memberships when user deleted
    )
    expense_payers: Mapped[list["ExpensePayer"]] = relationship( # type: ignore # noqa: F821
        "ExpensePayer",
        back_populates="user",
    )
    expense_splits: Mapped[list["ExpenseSplit"]] = relationship( # type: ignore # noqa: F821
        "ExpenseSplit",
        back_populates="user",
    )
    # Two relationships to Settlement, must specify foreign_keys explicitly
    settlements_paid: Mapped[list["Settlement"]] = relationship( # type: ignore # noqa: F821
        "Settlement",
        foreign_keys="Settlement.payer_id",
        back_populates="payer",
    )
    settlements_received: Mapped[list["Settlement"]] = relationship( # type: ignore # noqa: F821
        "Settlement",
        foreign_keys="Settlement.receiver_id",
        back_populates="receiver",
    )