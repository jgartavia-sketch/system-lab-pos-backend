from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func
from app.db.database import Base

class BusinessFinanceMovement(Base):
    __tablename__ = "business_finance_movements"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("managed_clients.id", ondelete="SET NULL"), nullable=True, index=True)
    movement_type = Column(String(10), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="CRC", index=True)
    category = Column(String(100), nullable=False, index=True)
    concept = Column(String(180), nullable=False)
    payment_method = Column(String(60), nullable=True)
    movement_date = Column(Date, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
