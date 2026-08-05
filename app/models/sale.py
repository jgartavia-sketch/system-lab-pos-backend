from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)

    cash_register_id = Column(
        Integer,
        ForeignKey("cash_registers.id"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=True,
        index=True,
    )

    payment_method_id = Column(
        Integer,
        ForeignKey("payment_methods.id"),
        nullable=False,
        index=True,
    )

    sale_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    subtotal = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    tax = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    discount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    total = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    notes = Column(
        Text,
        nullable=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="completed",
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    cash_register = relationship(
        "CashRegister",
        lazy="joined",
    )

    user = relationship(
        "User",
        lazy="joined",
    )

    customer = relationship(
        "Customer",
        lazy="joined",
    )

    payment_method = relationship(
        "PaymentMethod",
        lazy="joined",
    )