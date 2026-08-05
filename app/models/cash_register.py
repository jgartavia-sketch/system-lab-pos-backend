from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class CashRegister(Base):
    __tablename__ = "cash_registers"

    id = Column(Integer, primary_key=True, index=True)

    opened_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    closed_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    opening_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    closing_amount = Column(
        Numeric(12, 2),
        nullable=True,
    )

    expected_amount = Column(
        Numeric(12, 2),
        nullable=True,
    )

    difference_amount = Column(
        Numeric(12, 2),
        nullable=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="open",
        index=True,
    )

    opened_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    closed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    opened_by_user = relationship(
        "User",
        foreign_keys=[opened_by],
        lazy="joined",
    )

    closed_by_user = relationship(
        "User",
        foreign_keys=[closed_by],
        lazy="joined",
    )

    movements = relationship(
        "CashMovement",
        back_populates="cash_register",
        cascade="all, delete-orphan",
    )