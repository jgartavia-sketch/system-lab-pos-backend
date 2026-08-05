from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class CustomerBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)

    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)

    identification_number: Optional[str] = Field(default=None, max_length=100)

    address: Optional[str] = Field(default=None, max_length=500)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)

    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)

    identification_number: Optional[str] = Field(default=None, max_length=100)

    address: Optional[str] = Field(default=None, max_length=500)


class CustomerResponse(CustomerBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CustomerStatusUpdate(BaseModel):
    is_active: bool