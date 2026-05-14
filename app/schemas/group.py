import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

# Import the enum from models - sharing enum avoids duplication and keeps DB/schema in sync
from app.db.models.group import MemberRole


class GroupCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Group name cannot be empty")
        if len(v) > 100:
            raise ValueError("Group name must be 100 characters or fewer")
        return v
    

class InviteMemberRequest(BaseModel):
    email: EmailStr


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str
    role: MemberRole
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    member_count: int
    created_at: datetime

    # from_attributes allows construction from ORM objects via model_validate()
    model_config = {"from_attributes": True}


class GroupDetailResponse(GroupResponse):
    """
    Extends GroupResponse with the full member list.
    Inheritance in Pydantic v2 works cleanly - all parent fields are included.
    """
    members: list[MemberResponse]