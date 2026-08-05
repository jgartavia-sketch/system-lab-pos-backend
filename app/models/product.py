from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    category_id = Column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False,
        index=True,
    )

    sku = Column(String(100), unique=True, nullable=True, index=True)
    barcode = Column(String(100), unique=True, nullable=True, index=True)

    name = Column(String(180), nullable=False, index=True)
    description = Column(String(500), nullable=True)

    cost = Column(Numeric(12, 2), default=0, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)

    stock_quantity = Column(Numeric(12, 2), default=0, nullable=False)
    minimum_stock = Column(Numeric(12, 2), default=0, nullable=False)

    image_url = Column(String(500), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    category = relationship(
        "Category",
        back_populates="products",
    )