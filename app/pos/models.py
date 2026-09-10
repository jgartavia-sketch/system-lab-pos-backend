"""Tenant-isolated POS. Legacy tables remain untouched."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric, DateTime, JSON, UniqueConstraint
from app.db.database import Base as LegacyBase
from sqlalchemy.orm import declarative_base
# Separate mapper registry avoids collisions with legacy Product/Customer classes.
Base = declarative_base(metadata=LegacyBase.metadata)

def now(): return datetime.now(timezone.utc)
class Account(Base):
    __tablename__ = 'pos_accounts'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(160), nullable=False)
    password_hash = Column(String(256), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    ceo = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True))
class Business(Base):
    __tablename__ = 'pos_businesses'
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    mode = Column(String(30), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    tables = Column(Integer, default=10, nullable=False)
    service_rate = Column(Numeric(5,2), default=0, nullable=False)
class Membership(Base):
    __tablename__ = 'pos_memberships'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False)
    role = Column(String(20), default='waiter', nullable=False)
    can_pay = Column(Boolean, default=True, nullable=False)
    pin_hash = Column(String(256))
    pin_failed = Column(Integer, default=0, nullable=False)
    pin_locked_until = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('account_id', 'business_id'),)
class Product(Base):
    __tablename__ = 'pos_products'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    category = Column(String(80), default='General', nullable=False)
    sku = Column(String(100), nullable=False)
    price = Column(Numeric(14,2), nullable=False)
    cost = Column(Numeric(14,2), default=0, nullable=False)
    tax_rate = Column(Numeric(5,2), default=0, nullable=False)
    stock = Column(Numeric(14,3), default=0, nullable=False)
    minimum = Column(Numeric(14,3), default=0, nullable=False)
    track_stock = Column(Boolean, default=True, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    packaging_fee = Column(Numeric(14,2), default=0, nullable=False)
    cost_known = Column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint('business_id', 'sku'),)
class Customer(Base):
    __tablename__ = 'pos_customers'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    phone = Column(String(40), default='')
    email = Column(String(255), default='')
class Register(Base):
    __tablename__ = 'pos_registers'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    opened_by = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    closed_by = Column(Integer, ForeignKey('pos_accounts.id'))
    opening = Column(Numeric(14,2), nullable=False)
    closing = Column(Numeric(14,2))
    expected = Column(Numeric(14,2))
    difference = Column(Numeric(14,2))
    opened_at = Column(DateTime(timezone=True), default=now, nullable=False)
    closed_at = Column(DateTime(timezone=True))
class Order(Base):
    __tablename__ = 'pos_orders'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    customer_id = Column(Integer, ForeignKey('pos_customers.id'))
    register_id = Column(Integer, ForeignKey('pos_registers.id'))
    request_key = Column(String(36), nullable=False)
    request_digest = Column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint('business_id', 'request_key'), UniqueConstraint('business_id', 'external_id'))
    source_channel = Column(String(20), default='pos', nullable=False)
    fulfillment = Column(String(20), default='dine_in', nullable=False)
    external_id = Column(String(80))
    packaging_total = Column(Numeric(14,2), default=0, nullable=False)
    service_total = Column(Numeric(14,2), default=0, nullable=False)
    label = Column(String(160), default='Mostrador', nullable=False)
    table_number = Column(Integer)
    status = Column(String(30), default='open', nullable=False)
    kitchen_status = Column(String(20))
    revision = Column(Integer, default=1, nullable=False)
    notes = Column(String(2000), default='', nullable=False)
    items = Column(JSON, default=list, nullable=False)
    subtotal = Column(Numeric(14,2), default=0, nullable=False)
    discount = Column(Numeric(14,2), default=0, nullable=False)
    tax = Column(Numeric(14,2), default=0, nullable=False)
    total = Column(Numeric(14,2), default=0, nullable=False)
    payment_method = Column(String(30))
    received = Column(Numeric(14,2))
    change = Column(Numeric(14,2))
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    paid_at = Column(DateTime(timezone=True))
class Movement(Base):
    __tablename__ = 'pos_movements'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    register_id = Column(Integer, ForeignKey('pos_registers.id'))
    product_id = Column(Integer, ForeignKey('pos_products.id'))
    order_id = Column(Integer, ForeignKey('pos_orders.id'))
    kind = Column(String(30), nullable=False)
    amount = Column(Numeric(14,3), nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
class Appointment(Base):
    __tablename__ = 'pos_appointments'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey('pos_customers.id'), nullable=False)
    title = Column(String(200), nullable=False)
    at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(30), default='pending', nullable=False)
    notes = Column(String(2000), default='')
class SigningKey(Base):
    __tablename__ = 'pos_signing_keys'
    id = Column(Integer, primary_key=True)
    secret = Column(String(128), nullable=False)

class Audit(Base):
    __tablename__ = 'pos_audit'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    approver_id = Column(Integer, ForeignKey('pos_accounts.id'))
    order_id = Column(Integer, ForeignKey('pos_orders.id'))
    action = Column(String(50), nullable=False)
    detail = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)

class FinancialEntry(Base):
    __tablename__ = 'pos_financial_entries'
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    request_key = Column(String(36), nullable=False)
    request_digest = Column(String(64), nullable=False)
    kind = Column(String(30), nullable=False)
    amount = Column(Numeric(14,2), nullable=False)
    category = Column(String(80), nullable=False)
    method = Column(String(20), nullable=False)
    reason = Column(String(500), nullable=False)
    supplier = Column(String(160), default='', nullable=False)
    reference = Column(String(100), default='', nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    cash_movement_id = Column(Integer, ForeignKey('pos_movements.id'), unique=True)
    void_movement_id = Column(Integer, ForeignKey('pos_movements.id'), unique=True)
    voided_at = Column(DateTime(timezone=True))
    void_reason = Column(String(500))
    __table_args__ = (UniqueConstraint('business_id', 'request_key'),)

class ConnectLink(Base):
    __tablename__ = 'pos_connect_links'
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), primary_key=True)
    provider = Column(String(30), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
