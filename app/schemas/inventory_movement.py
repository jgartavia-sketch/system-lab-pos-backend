from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class InventoryMovementCreate(BaseModel):
    product_id: int
    user_id: int
    movement_type: str = Field(min_length=1, max_length=30)
    quantity: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=100)
    reference_type: Optional[str] = Field(default=None, max_length=50)
    reference_id: Optional[int] = None
    notes: Optional[str] = None


class InventoryMovementResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    movement_type: str
    quantity: Decimal
    reason: str
    reference_type: Optional[str]
    reference_id: Optional[int]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True