from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class CashMovementCreate(BaseModel):
    cash_register_id: int
    user_id: int
    movement_type: str = Field(min_length=1, max_length=30)
    amount: Decimal = Field(gt=0)
    description: Optional[str] = Field(default=None, max_length=1000)


class CashMovementResponse(BaseModel):
    id: int
    cash_register_id: int
    user_id: int
    movement_type: str
    amount: Decimal
    description: Optional[str]
    created_at: datetime

    model_config = {
        "from_attributes": True
    }