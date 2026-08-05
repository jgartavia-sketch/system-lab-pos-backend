from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class PaymentMethodBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)


class PaymentMethodCreate(PaymentMethodBase):
    pass


class PaymentMethodUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)


class PaymentMethodResponse(PaymentMethodBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PaymentMethodStatusUpdate(BaseModel):
    is_active: bool