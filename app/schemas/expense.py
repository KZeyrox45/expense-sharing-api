import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models.expense import SplitType


class PayerInput(BaseModel):
    user_id: uuid.UUID
    amount: Decimal = Field(gt=0, decimal_places=2)


class SplitInput(BaseModel):
    user_id: uuid.UUID
    # value meaning depends on split_type:
    #   equal      -> None (not required, ignored if provided)
    #   exact      -> the exact amount this user owes
    #   percentage -> percentage of total (e.g. 33.33)
    #   shares     -> share count (e.g. 2 in a 2:1:1 ratio)
    value: Decimal | None = Field(default=None, gt=0)


class ExpenseCreate(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    total_amount: Decimal = Field(gt=0, decimal_places=2)
    split_type: SplitType
    date_happened: date
    payers: list[PayerInput] = Field(min_length=1)
    splits: list[SplitInput] = Field(min_length=1)

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        return v.strip()
    
    @model_validator(mode="after")
    def validate_splits_have_value_when_needed(self) -> "ExpenseCreate":
        """
        For non-equal split types, every SplitInput must have a value.
        Checked here (not in SplitInput) because we need split_type context.
        """
        if self.split_type != SplitType.equal:
            for s in self.splits:
                if s.value is None:
                    raise ValueError(
                        f"split_type '{self.split_type}' requires a value for every split entry"
                    )
        return self
    
    @model_validator(mode="after")
    def validate_no_duplicate_users(self) -> "ExpenseCreate":
        payer_ids = [p.user_id for p in self.payers]
        split_ids = [s.user_id for s in self.splits]
        if len(payer_ids) != len(set(payer_ids)):
            raise ValueError("Duplicate user_id in payers")
        if len(split_ids) != len(set(split_ids)):
            raise ValueError("Duplicate user_id in splits")
        return self
    

# --- Response schemas ------------------------------------------------------------

class PayerResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    amount: Decimal


class SplitResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    amount: Decimal
    split_value: Decimal | None     # Raw input value stored for display


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    description: str
    total_amount: Decimal
    split_type: SplitType
    date_happened: date
    created_by: uuid.UUID
    payers: list[PayerResponse]
    splits: list[SplitResponse]
    created_at: datetime


class ExpenseListResponse(BaseModel):
    total: int          # Total count (for pagination UI)
    items: list[ExpenseResponse]