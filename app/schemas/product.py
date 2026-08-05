from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=180)
    description: Optional[str] = Field(default=None, max_length=500)

    sku: Optional[str] = Field(default=None, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)

    category_id: int

    cost: Decimal = Field(default=Decimal("0.00"), ge=0)
    price: Decimal = Field(..., ge=0)

    stock_quantity: Decimal = Field(default=Decimal("0.00"), ge=0)
    minimum_stock: Decimal = Field(default=Decimal("0.00"), ge=0)

    image_url: Optional[str] = Field(default=None, max_length=500)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=180)
    description: Optional[str] = Field(default=None, max_length=500)

    sku: Optional[str] = Field(default=None, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)

    category_id: Optional[int] = None

    cost: Optional[Decimal] = Field(default=None, ge=0)
    price: Optional[Decimal] = Field(default=None, ge=0)

    stock_quantity: Optional[Decimal] = Field(default=None, ge=0)
    minimum_stock: Optional[Decimal] = Field(default=None, ge=0)

    image_url: Optional[str] = Field(default=None, max_length=500)


class ProductResponse(ProductBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ProductStatusUpdate(BaseModel):
    is_active: bool