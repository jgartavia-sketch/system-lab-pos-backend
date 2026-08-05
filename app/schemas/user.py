from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import EmailStr


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    role_id: int
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_id: Optional[int] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class UserResponse(BaseModel):
    id: int
    role_id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    role: Optional[RoleResponse] = None

    model_config = {
        "from_attributes": True
    }