from decimal import Decimal
from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from app.schemas.inventory_movement import InventoryMovementCreate
from app.schemas.inventory_movement import InventoryMovementResponse


router = APIRouter(
    prefix="/inventory-movements",
    tags=["Inventory Movements"],
)


ALLOWED_MOVEMENT_TYPES = [
    "entry",
    "exit",
    "adjustment",
]


@router.get(
    "/",
    response_model=List[InventoryMovementResponse],
)
def list_inventory_movements():
    db: Session = SessionLocal()

    try:
        movements = (
            db.query(InventoryMovement)
            .order_by(InventoryMovement.created_at.desc())
            .all()
        )

        return movements

    finally:
        db.close()


@router.get(
    "/product/{product_id}",
    response_model=List[InventoryMovementResponse],
)
def list_inventory_movements_by_product(product_id: int):
    db: Session = SessionLocal()

    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado.",
            )

        movements = (
            db.query(InventoryMovement)
            .filter(InventoryMovement.product_id == product_id)
            .order_by(InventoryMovement.created_at.desc())
            .all()
        )

        return movements

    finally:
        db.close()


@router.post(
    "/",
    response_model=InventoryMovementResponse,
)
def create_inventory_movement(payload: InventoryMovementCreate):
    db: Session = SessionLocal()

    try:
        product = (
            db.query(Product)
            .filter(Product.id == payload.product_id)
            .with_for_update()
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado.",
            )

        if not product.is_active:
            raise HTTPException(
                status_code=400,
                detail="No se pueden registrar movimientos para un producto inactivo.",
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

        if payload.movement_type not in ALLOWED_MOVEMENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Tipo de movimiento inválido. Use: entry, exit o adjustment.",
            )

        quantity = Decimal(payload.quantity)

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="La cantidad del movimiento debe ser mayor a cero.",
            )

        current_stock = Decimal(product.stock_quantity or 0)

        if payload.movement_type == "entry":
            product.stock_quantity = current_stock + quantity

        elif payload.movement_type == "exit":
            if quantity > current_stock:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Stock insuficiente para salida de inventario. "
                        f"Disponible: {current_stock}. Solicitado: {quantity}."
                    ),
                )

            product.stock_quantity = current_stock - quantity

        elif payload.movement_type == "adjustment":
            product.stock_quantity = quantity

        movement = InventoryMovement(
            product_id=payload.product_id,
            user_id=payload.user_id,
            movement_type=payload.movement_type,
            quantity=quantity,
            reason=payload.reason,
            reference_type=payload.reference_type,
            reference_id=payload.reference_id,
            notes=payload.notes,
        )

        db.add(movement)
        db.commit()
        db.refresh(movement)

        return movement

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()