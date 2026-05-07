# DeclarativeBase is the starting point for all SQL Alchemy models.
# All model classes will inherit from this Base.

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all database models.

    Use SQLAlchemy 2.0's DeclarativeBase (not the old declarative_base()).
    Mapped[] + mapped_column() is the new SQLAlchemy 2.0 syntax,
    type-safe and more compatible with mypy/pylance than the old Column().
    """

    # All models have UUID IDs (to avoid easily guessable sequential integer IDs).
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4      # Generate UUID in Python side, does not depend on DB
    )

    # All models have created_at (server_default = DB self set when INSERT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),   # Use DB time, not app time
        nullable=False
    )