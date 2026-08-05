from typing import List

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.product import Product
from app.schemas.product import ProductResponse


router = APIRouter(
    prefix="/inventory-alerts",
    tags=["Inventory Alerts"],
)


@router.get(
    "/low-stock",
    response_model=List[ProductResponse],
)
def list_low_stock_products():
    db: Session = SessionLocal()

    try:
        products = (
            db.query(Product)
            .filter(Product.is_active == True)
            .filter(Product.stock_quantity > 0)
            .filter(Product.stock_quantity <= Product.minimum_stock)
            .order_by(Product.stock_quantity.asc(), Product.name.asc())
            .all()
        )

        return products

    finally:
        db.close()


@router.get(
    "/out-of-stock",
    response_model=List[ProductResponse],
)
def list_out_of_stock_products():
    db: Session = SessionLocal()

    try:
        products = (
            db.query(Product)
            .filter(Product.is_active == True)
            .filter(Product.stock_quantity == 0)
            .order_by(Product.name.asc())
            .all()
        )

        return products

    finally:
        db.close()