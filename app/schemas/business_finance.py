from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class FinanceMovementCreate(BaseModel):
    client_id: int | None = None
    movement_type: Literal["income", "expense"]
    amount: Decimal = Field(gt=0)
    currency: Literal["CRC", "USD"] = "CRC"
    category: str = Field(min_length=2, max_length=100)
    concept: str = Field(min_length=2, max_length=180)
    payment_method: str | None = Field(default=None, max_length=60)
    movement_date: date
    notes: str | None = None

class FinanceMovementResponse(FinanceMovementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime

class FinanceSummary(BaseModel):
    income: Decimal
    expenses: Decimal
    profit: Decimal
    movement_count: int
