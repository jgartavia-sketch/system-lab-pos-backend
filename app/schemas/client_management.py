from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ServiceDefinition(BaseModel):
    key: str
    label: str


class ManagedClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    website_url: str | None = Field(default=None, max_length=500)


class ServiceStatusUpdate(BaseModel):
    is_active: bool
    notes: str | None = Field(default=None, max_length=500)


class ServiceStatusResponse(ServiceStatusUpdate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    service_key: str
    updated_at: datetime


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str | None = None
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: date | None = None


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = None
    status: Literal["pending", "in_progress", "completed", "blocked"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    due_date: date | None = None


class MilestoneResponse(MilestoneCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    created_at: datetime
    updated_at: datetime


class PaymentCreate(BaseModel):
    product_service: str = Field(min_length=2, max_length=180)
    value: Decimal = Field(gt=0)
    currency: Literal["CRC", "USD"] = "CRC"
    status: Literal["pending", "paid", "overdue"] = "pending"
    period_start: date | None = None
    period_end: date | None = None
    payment_date: date | None = None
    next_payment_date: date | None = None
    detail: str | None = Field(default=None, max_length=500)


class PaymentUpdate(BaseModel):
    product_service: str | None = Field(default=None, min_length=2, max_length=180)
    value: Decimal | None = Field(default=None, gt=0)
    currency: Literal["CRC", "USD"] | None = None
    status: Literal["pending", "paid", "overdue"] | None = None
    period_start: date | None = None
    period_end: date | None = None
    payment_date: date | None = None
    next_payment_date: date | None = None
    detail: str | None = Field(default=None, max_length=500)


class PaymentResponse(PaymentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    created_at: datetime
    updated_at: datetime


class ManagedClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    website_url: str | None
    is_active: bool
    service_statuses: list[ServiceStatusResponse]
    milestones: list[MilestoneResponse]
    payments: list[PaymentResponse]


class ClientManagementDashboard(BaseModel):
    services: list[ServiceDefinition]
    clients: list[ManagedClientResponse]
