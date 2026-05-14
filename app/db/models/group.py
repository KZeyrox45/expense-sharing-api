import uuid
import enum
from datetime import datetime

from sqlalchemy import ForeignKey, String, DateTime, Enum, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Group(Base):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True       # Optional Field
    )
    # Who created this group - always an admin
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        # RESTRICT: cannot delete a user who created a group
        nullable=False
    )

    # Relationships
    creator: Mapped["User"] = relationship( # type: ignore # noqa: F821
        "User",
        foreign_keys=[created_by]
    )
    members: Mapped[list["GroupMember"]] = relationship(
        "GroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )
    expenses: Mapped[list["Expense"]] = relationship( # type: ignore # noqa: F821
        "Expense",
        back_populates="group",
    )
    settlements: Mapped[list["Settlement"]] = relationship( # type: ignore # noqa: F821
        "Settlement",
        back_populates="group",
    )


class MemberRole(str, enum.Enum):
    """
    str mixin: MemberRole.admin == "admin" -> works in JSON serialization
    and database comparisons without extra conversion.
    """
    admin = "admin"
    member = "member"


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        # CASCADE: delete membership when group is deleted
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role"),       # Named enum in PostgreSQL
        default=MemberRole.member,
        nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Unique constraints - one user can only be in a group once
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="group_memberships") # type: ignore # noqa: F821