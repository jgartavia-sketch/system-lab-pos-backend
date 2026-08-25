from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class ManagedClient(Base):
    __tablename__ = "managed_clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(140), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    website_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    service_statuses = relationship("ClientServiceStatus", back_populates="client", cascade="all, delete-orphan")
    milestones = relationship("ProjectMilestone", back_populates="client", cascade="all, delete-orphan")
    payments = relationship("ClientPayment", back_populates="client", cascade="all, delete-orphan")


class ClientServiceStatus(Base):
    __tablename__ = "client_service_statuses"
    __table_args__ = (UniqueConstraint("client_id", "service_key", name="uq_client_service"),)

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False, index=True)
    service_key = Column(String(60), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=False)
    notes = Column(String(500), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    client = relationship("ManagedClient", back_populates="service_statuses")


class ProjectMilestone(Base):
    __tablename__ = "project_milestones"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    priority = Column(String(20), nullable=False, default="medium")
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    client = relationship("ManagedClient", back_populates="milestones")


class ClientPayment(Base):
    __tablename__ = "client_payments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False, index=True)
    product_service = Column(String(180), nullable=False)
    value = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="CRC")
    status = Column(String(20), nullable=False, default="pending", index=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    payment_date = Column(Date, nullable=True)
    next_payment_date = Column(Date, nullable=True)
    detail = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    client = relationship("ManagedClient", back_populates="payments")
