from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class CashRegisterOpen(BaseModel):
    opened_by: int
    opening_amount: Decimal = Field(ge=0)


class CashRegisterClose(BaseModel):
    closed_by: int
    closing_amount: Decimal = Field(ge=0)


class CashRegisterResponse(BaseModel):
    id: int
    opened_by: int
    closed_by: Optional[int]
    opening_amount: Decimal
    closing_amount: Optional[Decimal]
    expected_amount: Optional[Decimal]
    difference_amount: Optional[Decimal]
    status: str
    opened_at: datetime
    closed_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }