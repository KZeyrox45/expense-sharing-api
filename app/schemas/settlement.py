import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class SettlementCreate(BaseModel):
    receiver_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("amount")
    @classmethod
    def validate_amount_precision(cls, v: Decimal) -> Decimal:
        """
        Rejects amounts with more than 2 decimal places.
        Consistent with the 'exact' split policy - monetary amounts must be unambiguous.
        """
        if v.quantize(Decimal("0.01")) != v:
            raise ValueError("Amount must have at most 2 decimal places")
        return v
    

class SettlementResponse(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    payer_id: uuid.UUID
    payer_username: str
    receiver_id: uuid.UUID
    receiver_username: str
    amount: Decimal
    note: str | None
    created_at: datetime