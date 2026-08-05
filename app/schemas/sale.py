from datetime import datetime
from decimal import Decimal
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class SaleItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    discount: Decimal = Field(default=0, ge=0)


class SaleCreate(BaseModel):
    cash_register_id: int
    user_id: int
    customer_id: Optional[int] = None
    payment_method_id: int
    discount: Decimal = Field(default=0, ge=0)
    notes: Optional[str] = None
    items: List[SaleItemCreate]


class SaleItemResponse(BaseModel):
    id: int
    sale_id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    subtotal: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class SaleResponse(BaseModel):
    id: int
    cash_register_id: int
    user_id: int
    customer_id: Optional[int] = None
    payment_method_id: int
    sale_number: str
    subtotal: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal
    notes: Optional[str]
    status: str
    created_at: datetime
    items: List[SaleItemResponse] = []

    class Config:
        from_attributes = True