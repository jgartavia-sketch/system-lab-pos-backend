from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


@router.get("/sales-summary")
def get_sales_summary():
    db: Session = SessionLocal()

    try:
        total_sales = (
            db.query(func.count(Sale.id))
            .filter(Sale.status == "completed")
            .scalar()
        )

        subtotal = (
            db.query(func.coalesce(func.sum(Sale.subtotal), 0))
            .filter(Sale.status == "completed")
            .scalar()
        )

        tax = (
            db.query(func.coalesce(func.sum(Sale.tax), 0))
            .filter(Sale.status == "completed")
            .scalar()
        )

        discount = (
            db.query(func.coalesce(func.sum(Sale.discount), 0))
            .filter(Sale.status == "completed")
            .scalar()
        )

        total = (
            db.query(func.coalesce(func.sum(Sale.total), 0))
            .filter(Sale.status == "completed")
            .scalar()
        )

        return {
            "total_sales": total_sales,
            "subtotal": Decimal(subtotal),
            "tax": Decimal(tax),
            "discount": Decimal(discount),
            "total": Decimal(total),
        }

    finally:
        db.close()


@router.get("/top-products")
def get_top_products():
    db: Session = SessionLocal()

    try:
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                func.coalesce(func.sum(SaleItem.quantity), 0).label("quantity_sold"),
                func.coalesce(func.sum(SaleItem.subtotal), 0).label("total_sold"),
            )
            .join(SaleItem, SaleItem.product_id == Product.id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(Sale.status == "completed")
            .group_by(Product.id, Product.name)
            .order_by(func.sum(SaleItem.quantity).desc())
            .all()
        )

        return [
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "quantity_sold": Decimal(row.quantity_sold),
                "total_sold": Decimal(row.total_sold),
            }
            for row in results
        ]

    finally:
        db.close()


@router.get("/top-customers")
def get_top_customers():
    db: Session = SessionLocal()

    try:
        customer_name = func.concat(
            Customer.first_name,
            " ",
            func.coalesce(Customer.last_name, ""),
        )

        results = (
            db.query(
                Customer.id.label("customer_id"),
                customer_name.label("customer_name"),
                func.count(Sale.id).label("total_purchases"),
                func.coalesce(func.sum(Sale.total), 0).label("total_spent"),
            )
            .join(Sale, Sale.customer_id == Customer.id)
            .filter(Sale.status == "completed")
            .group_by(Customer.id, Customer.first_name, Customer.last_name)
            .order_by(func.sum(Sale.total).desc())
            .all()
        )

        return [
            {
                "customer_id": row.customer_id,
                "customer_name": row.customer_name.strip(),
                "total_purchases": row.total_purchases,
                "total_spent": Decimal(row.total_spent),
            }
            for row in results
        ]

    finally:
        db.close()


@router.get("/sales-by-day")
def get_sales_by_day():
    db: Session = SessionLocal()

    try:
        sale_day = cast(Sale.created_at, Date)

        results = (
            db.query(
                sale_day.label("date"),
                func.count(Sale.id).label("total_sales"),
                func.coalesce(func.sum(Sale.subtotal), 0).label("subtotal"),
                func.coalesce(func.sum(Sale.tax), 0).label("tax"),
                func.coalesce(func.sum(Sale.discount), 0).label("discount"),
                func.coalesce(func.sum(Sale.total), 0).label("total"),
            )
            .filter(Sale.status == "completed")
            .group_by(sale_day)
            .order_by(sale_day.desc())
            .all()
        )

        return [
            {
                "date": row.date,
                "total_sales": row.total_sales,
                "subtotal": Decimal(row.subtotal),
                "tax": Decimal(row.tax),
                "discount": Decimal(row.discount),
                "total": Decimal(row.total),
            }
            for row in results
        ]

    finally:
        db.close()


@router.get("/sales-by-month")
def get_sales_by_month():
    db: Session = SessionLocal()

    try:
        sale_month = func.to_char(Sale.created_at, "YYYY-MM")

        results = (
            db.query(
                sale_month.label("month"),
                func.count(Sale.id).label("total_sales"),
                func.coalesce(func.sum(Sale.subtotal), 0).label("subtotal"),
                func.coalesce(func.sum(Sale.tax), 0).label("tax"),
                func.coalesce(func.sum(Sale.discount), 0).label("discount"),
                func.coalesce(func.sum(Sale.total), 0).label("total"),
            )
            .filter(Sale.status == "completed")
            .group_by(sale_month)
            .order_by(sale_month.desc())
            .all()
        )

        return [
            {
                "month": row.month,
                "total_sales": row.total_sales,
                "subtotal": Decimal(row.subtotal),
                "tax": Decimal(row.tax),
                "discount": Decimal(row.discount),
                "total": Decimal(row.total),
            }
            for row in results
        ]

    finally:
        db.close()


@router.get("/low-stock-products")
def get_low_stock_products():
    db: Session = SessionLocal()

    try:
        products = (
            db.query(Product)
            .filter(Product.is_active == True)
            .filter(Product.stock_quantity <= Product.minimum_stock)
            .order_by(Product.stock_quantity.asc(), Product.name.asc())
            .all()
        )

        return [
            {
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "barcode": product.barcode,
                "stock_quantity": Decimal(product.stock_quantity),
                "minimum_stock": Decimal(product.minimum_stock),
            }
            for product in products
        ]

    finally:
        db.close()