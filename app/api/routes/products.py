from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.schemas.product import ProductCreate
from app.schemas.product import ProductResponse
from app.schemas.product import ProductStatusUpdate
from app.schemas.product import ProductUpdate


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


@router.get(
    "/",
    response_model=List[ProductResponse],
)
def list_products():
    db: Session = SessionLocal()

    try:
        products = (
            db.query(Product)
            .order_by(Product.name.asc())
            .all()
        )

        return products

    finally:
        db.close()


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
def get_product(product_id: int):
    db: Session = SessionLocal()

    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        return product

    finally:
        db.close()


@router.post(
    "/",
    response_model=ProductResponse,
)
def create_product(payload: ProductCreate):
    db: Session = SessionLocal()

    try:
        category = (
            db.query(Category)
            .filter(Category.id == payload.category_id)
            .first()
        )

        if category is None:
            raise HTTPException(
                status_code=404,
                detail="Category not found",
            )

        if payload.sku:
            existing_sku = (
                db.query(Product)
                .filter(Product.sku == payload.sku)
                .first()
            )

            if existing_sku is not None:
                raise HTTPException(
                    status_code=400,
                    detail="SKU already exists",
                )

        if payload.barcode:
            existing_barcode = (
                db.query(Product)
                .filter(Product.barcode == payload.barcode)
                .first()
            )

            if existing_barcode is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Barcode already exists",
                )

        product = Product(
            name=payload.name,
            description=payload.description,
            sku=payload.sku,
            barcode=payload.barcode,
            category_id=payload.category_id,
            cost=payload.cost,
            price=payload.price,
            stock_quantity=payload.stock_quantity,
            minimum_stock=payload.minimum_stock,
            image_url=payload.image_url,
        )

        db.add(product)
        db.commit()
        db.refresh(product)

        return product

    finally:
        db.close()


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
)
def update_product(product_id: int, payload: ProductUpdate):
    db: Session = SessionLocal()

    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        update_data = payload.model_dump(exclude_unset=True)

        if "category_id" in update_data:
            category = (
                db.query(Category)
                .filter(Category.id == update_data["category_id"])
                .first()
            )

            if category is None:
                raise HTTPException(
                    status_code=404,
                    detail="Category not found",
                )

        if "sku" in update_data and update_data["sku"]:
            existing_sku = (
                db.query(Product)
                .filter(Product.sku == update_data["sku"])
                .filter(Product.id != product_id)
                .first()
            )

            if existing_sku is not None:
                raise HTTPException(
                    status_code=400,
                    detail="SKU already exists",
                )

        if "barcode" in update_data and update_data["barcode"]:
            existing_barcode = (
                db.query(Product)
                .filter(Product.barcode == update_data["barcode"])
                .filter(Product.id != product_id)
                .first()
            )

            if existing_barcode is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Barcode already exists",
                )

        for field, value in update_data.items():
            setattr(product, field, value)

        db.commit()
        db.refresh(product)

        return product

    finally:
        db.close()


@router.patch(
    "/{product_id}/status",
    response_model=ProductResponse,
)
def update_product_status(product_id: int, payload: ProductStatusUpdate):
    db: Session = SessionLocal()

    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        product.is_active = payload.is_active

        db.commit()
        db.refresh(product)

        return product

    finally:
        db.close()