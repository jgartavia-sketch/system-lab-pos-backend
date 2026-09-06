from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, ConfigDict
Mode = Literal['restaurante','heladeria','supermercado','taller','salon']
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, validate_default=True)
class Login(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
class Password(Strict):
    current: str = Field(max_length=128)
    password: str = Field(min_length=8, max_length=128)
class BusinessIn(Strict):
    name: str = Field(min_length=2, max_length=160)
    mode: Mode
    tables: int = Field(default=10, ge=0, le=200)
    active: bool = True
class AccountIn(Strict):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_ids: list[int] = Field(default_factory=list, max_length=100)
class AccessIn(Strict):
    active: bool
    business_ids: list[int] = Field(max_length=100)
class ProductIn(Strict):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(default='General', min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(ge=0, le=999999999, max_digits=12, decimal_places=2)
    cost: Decimal = Field(default=0, ge=0, le=999999999, decimal_places=2)
    tax_rate: Decimal = Field(default=0, ge=0, le=100, decimal_places=2)
    minimum: Decimal = Field(default=0, ge=0, le=999999999, decimal_places=3)
    track_stock: bool = True
    active: bool = True
class CustomerIn(Strict):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(default='', max_length=40)
    email: str = Field(default='', max_length=255)
class Amount(Strict):
    amount: Decimal = Field(ge=0, le=999999999, decimal_places=2)
class StockIn(Strict):
    kind: Literal['entry','exit','adjustment']
    quantity: Decimal = Field(ge=0, le=999999999, decimal_places=3)
    reason: str = Field(min_length=2, max_length=500)
class CashIn(Strict):
    kind: Literal['income','expense']
    amount: Decimal = Field(gt=0, le=999999999, decimal_places=2)
    reason: str = Field(min_length=2, max_length=500)
class ItemIn(Strict):
    product_id: int
    quantity: Decimal = Field(gt=0, le=999999, decimal_places=3)
class OrderIn(Strict):
    request_key: UUID | None = None
    label: str = Field(default='Mostrador', min_length=1, max_length=160)
    table_number: int | None = Field(default=None, ge=1, le=200)
    customer_id: int | None = None
    notes: str = Field(default='', max_length=2000)
    discount: Decimal = Field(default=0, ge=0, le=999999999, decimal_places=2)
    items: list[ItemIn] = Field(min_length=1, max_length=200)
class StateIn(Strict):
    status: Literal['queued','preparing','ready','cancelled']
class PayIn(Strict):
    method: Literal['cash','card','sinpe','transfer']
    received: Decimal = Field(default=0, ge=0, le=999999999, decimal_places=2)
class Reason(Strict):
    reason: str = Field(min_length=3, max_length=500)
class AppointmentIn(Strict):
    customer_id: int
    title: str = Field(min_length=1, max_length=200)
    at: datetime
    status: Literal['pending','confirmed','completed','cancelled'] = 'pending'
    notes: str = Field(default='', max_length=2000)

class ResetPassword(Strict):
    password: str = Field(min_length=8, max_length=128)
