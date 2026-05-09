# User-facing response schema - never expose hashed_password.

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    is_active: bool
    created_at: datetime

    # Pydantic v2: replace orm_mode = True from v1
    # Allows creating this schema directly from a SQLAlchemy model instance
    model_config = {"from_attributes": True}