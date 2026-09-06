"""Tenant-isolated POS. Legacy tables remain untouched."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base
Base = declarative_base()

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
class Membership(Base):
    __tablename__ = 'pos_memberships'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('pos_accounts.id'), nullable=False)
    business_id = Column(Integer, ForeignKey('pos_businesses.id'), nullable=False)
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
    __table_args__ = (UniqueConstraint('business_id', 'request_key'),)
    label = Column(String(160), default='Mostrador', nullable=False)
    table_number = Column(Integer)
    status = Column(String(30), default='open', nullable=False)
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

from alembic import op
import secrets
revision = 'e260906pos01'
down_revision = '4b7d8e9f1a20'
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    Base.metadata.create_all(bind=bind)
    bind.execute(SigningKey.__table__.insert().values(id=1,secret=secrets.token_urlsafe(64)))
    bind.execute(Account.__table__.insert().values(id=1,email='jgartavia@gmail.com',name='José Artavia',password_hash=BOOTSTRAP_HASH,active=True,ceo=True,version=1,failed=0))
    bind.execute(Business.__table__.insert().values(id=1,name='Restaurante de prueba · System Lab',mode='restaurante',active=True,tables=10))
    bind.execute(Membership.__table__.insert().values(account_id=1,business_id=1))
    # Demo catalog exists only in the explicitly named test business.
    for pid,name,sku,price,cost in [(1,'Café demo','DEMO-CAFE',1000,300),(2,'Casado demo','DEMO-CASADO',3500,1500),(3,'Refresco demo','DEMO-REFRESCO',1500,500)]:
        bind.execute(Product.__table__.insert().values(id=pid,business_id=1,name=name,category='Demostración',sku=sku,price=price,cost=cost,tax_rate=13,stock=20,minimum=5,track_stock=True,active=True))
        bind.execute(Movement.__table__.insert().values(business_id=1,account_id=1,product_id=pid,kind='stock',amount=20,reason='Inventario inicial de demostración',created_at=now()))

    if bind.dialect.name == 'postgresql':
        from sqlalchemy import text
        for name in ('pos_accounts','pos_businesses','pos_products'):
            bind.execute(text("SELECT setval(pg_get_serial_sequence('"+name+"','id'), (SELECT MAX(id) FROM "+name+"))"))

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())

BOOTSTRAP_HASH = 'scrypt$033e8dee1f942b82cd43257e4151c51e$8fe8364770bc5f946064604de13f09458609d288915be1dc1c8d255fc854d6369f65441b0af4900bd571db019907e55b227ef1f68460e228884293604129502d'
