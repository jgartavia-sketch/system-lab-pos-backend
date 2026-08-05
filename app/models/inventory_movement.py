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


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    movement_type = Column(
        String(30),
        nullable=False,
        index=True,
    )

    quantity = Column(
        Numeric(12, 2),
        nullable=False,
    )

    reason = Column(
        String(100),
        nullable=False,
    )

    reference_type = Column(
        String(50),
        nullable=True,
        index=True,
    )

    reference_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    notes = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    product = relationship(
        "Product",
        lazy="joined",
    )

    user = relationship(
        "User",
        lazy="joined",
    )