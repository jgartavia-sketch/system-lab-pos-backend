from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.cash_register import CashRegister
from app.models.customer import Customer
from app.models.inventory_movement import InventoryMovement
from app.models.payment_method import PaymentMethod
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.user import User
from app.schemas.sale import SaleCreate
from app.schemas.sale import SaleResponse


router = APIRouter(
    prefix="/sales",
    tags=["Sales"],
)


TAX_RATE = Decimal("0.13")


def generate_sale_number() -> str:
    return f"SALE-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def build_sale_response(db: Session, sale: Sale):
    items = (
        db.query(SaleItem)
        .filter(SaleItem.sale_id == sale.id)
        .order_by(SaleItem.id.asc())
        .all()
    )

    return {
        "id": sale.id,
        "cash_register_id": sale.cash_register_id,
        "user_id": sale.user_id,
        "customer_id": sale.customer_id,
        "payment_method_id": sale.payment_method_id,
        "sale_number": sale.sale_number,
        "subtotal": sale.subtotal,
        "tax": sale.tax,
        "discount": sale.discount,
        "total": sale.total,
        "notes": sale.notes,
        "status": sale.status,
        "created_at": sale.created_at,
        "items": items,
    }


@router.get(
    "/",
    response_model=List[SaleResponse],
)
def list_sales():
    db: Session = SessionLocal()

    try:
        sales = (
            db.query(Sale)
            .order_by(Sale.created_at.desc())
            .all()
        )

        return [
            build_sale_response(db, sale)
            for sale in sales
        ]

    finally:
        db.close()


@router.get(
    "/{sale_id}",
    response_model=SaleResponse,
)
def get_sale(sale_id: int):
    db: Session = SessionLocal()

    try:
        sale = (
            db.query(Sale)
            .filter(Sale.id == sale_id)
            .first()
        )

        if not sale:
            raise HTTPException(
                status_code=404,
                detail="Venta no encontrada.",
            )

        return build_sale_response(db, sale)

    finally:
        db.close()


@router.post(
    "/",
    response_model=SaleResponse,
)
def create_sale(payload: SaleCreate):
    db: Session = SessionLocal()

    try:
        if not payload.items:
            raise HTTPException(
                status_code=400,
                detail="La venta debe tener al menos un producto.",
            )

        cash_register = (
            db.query(CashRegister)
            .filter(CashRegister.id == payload.cash_register_id)
            .first()
        )

        if not cash_register:
            raise HTTPException(
                status_code=404,
                detail="Caja no encontrada.",
            )

        if cash_register.status != "open":
            raise HTTPException(
                status_code=400,
                detail="La caja seleccionada no está abierta.",
            )

        user = (
            db.query(User)
            .filter(User.id == payload.user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado.",
            )

        if payload.customer_id is not None:
            customer = (
                db.query(Customer)
                .filter(Customer.id == payload.customer_id)
                .first()
            )

            if not customer:
                raise HTTPException(
                    status_code=404,
                    detail="Cliente no encontrado.",
                )

            if not customer.is_active:
                raise HTTPException(
                    status_code=400,
                    detail="El cliente está inactivo.",
                )

        payment_method = (
            db.query(PaymentMethod)
            .filter(PaymentMethod.id == payload.payment_method_id)
            .first()
        )

        if not payment_method:
            raise HTTPException(
                status_code=404,
                detail="Método de pago no encontrado.",
            )

        if not payment_method.is_active:
            raise HTTPException(
                status_code=400,
                detail="El método de pago está inactivo.",
            )

        subtotal = Decimal("0.00")
        sale_items_data = []
        stock_requested_by_product = {}

        for item in payload.items:
            quantity = Decimal(item.quantity)

            if quantity <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"La cantidad del producto con ID {item.product_id} debe ser mayor a cero.",
                )

            item_discount = Decimal(item.discount)

            if item_discount < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"El descuento del producto con ID {item.product_id} no puede ser negativo.",
                )

            product = (
                db.query(Product)
                .filter(Product.id == item.product_id)
                .with_for_update()
                .first()
            )

            if not product:
                raise HTTPException(
                    status_code=404,
                    detail=f"Producto con ID {item.product_id} no encontrado.",
                )

            if not product.is_active:
                raise HTTPException(
                    status_code=400,
                    detail=f"Producto con ID {item.product_id} está inactivo.",
                )

            current_requested_quantity = stock_requested_by_product.get(
                product.id,
                Decimal("0.00"),
            )

            total_requested_quantity = current_requested_quantity + quantity
            available_stock = Decimal(product.stock_quantity or 0)

            if total_requested_quantity > available_stock:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Stock insuficiente para el producto '{product.name}'. "
                        f"Disponible: {available_stock}. "
                        f"Solicitado: {total_requested_quantity}."
                    ),
                )

            stock_requested_by_product[product.id] = total_requested_quantity

            unit_price = Decimal(product.price)
            item_subtotal = (unit_price * quantity) - item_discount

            if item_subtotal < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"El descuento del producto con ID {item.product_id} no puede superar su subtotal.",
                )

            subtotal += item_subtotal

            sale_items_data.append(
                {
                    "product": product,
                    "product_id": product.id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount": item_discount,
                    "subtotal": item_subtotal,
                }
            )

        sale_discount = Decimal(payload.discount)

        if sale_discount < 0:
            raise HTTPException(
                status_code=400,
                detail="El descuento general no puede ser negativo.",
            )

        if sale_discount > subtotal:
            raise HTTPException(
                status_code=400,
                detail="El descuento general no puede superar el subtotal de la venta.",
            )

        taxable_amount = subtotal - sale_discount
        tax = taxable_amount * TAX_RATE
        total = taxable_amount + tax

        sale = Sale(
            cash_register_id=payload.cash_register_id,
            user_id=payload.user_id,
            customer_id=payload.customer_id,
            payment_method_id=payload.payment_method_id,
            sale_number=generate_sale_number(),
            subtotal=subtotal,
            tax=tax,
            discount=sale_discount,
            total=total,
            notes=payload.notes,
            status="completed",
        )

        db.add(sale)
        db.flush()

        for item_data in sale_items_data:
            product = item_data["product"]

            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                discount=item_data["discount"],
                subtotal=item_data["subtotal"],
            )

            product.stock_quantity = Decimal(product.stock_quantity or 0) - item_data["quantity"]

            inventory_movement = InventoryMovement(
                product_id=item_data["product_id"],
                user_id=payload.user_id,
                movement_type="exit",
                quantity=item_data["quantity"],
                reason="Venta",
                reference_type="sale",
                reference_id=sale.id,
                notes=f"Salida automática por venta {sale.sale_number}.",
            )

            db.add(sale_item)
            db.add(inventory_movement)

        db.commit()
        db.refresh(sale)

        return build_sale_response(db, sale)

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()