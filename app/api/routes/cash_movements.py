from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.cash_movement import CashMovement
from app.models.cash_register import CashRegister
from app.models.user import User
from app.schemas.cash_movement import CashMovementCreate
from app.schemas.cash_movement import CashMovementResponse


router = APIRouter(
    prefix="/cash-movements",
    tags=["Cash Movements"],
)


@router.get(
    "/",
    response_model=List[CashMovementResponse],
)
def list_cash_movements():
    db: Session = SessionLocal()

    try:
        movements = (
            db.query(CashMovement)
            .order_by(CashMovement.created_at.desc())
            .all()
        )

        return movements

    finally:
        db.close()


@router.get(
    "/cash-register/{cash_register_id}",
    response_model=List[CashMovementResponse],
)
def list_cash_movements_by_cash_register(cash_register_id: int):
    db: Session = SessionLocal()

    try:
        cash_register = (
            db.query(CashRegister)
            .filter(CashRegister.id == cash_register_id)
            .first()
        )

        if cash_register is None:
            raise HTTPException(
                status_code=404,
                detail="Cash register not found",
            )

        movements = (
            db.query(CashMovement)
            .filter(CashMovement.cash_register_id == cash_register_id)
            .order_by(CashMovement.created_at.desc())
            .all()
        )

        return movements

    finally:
        db.close()


@router.post(
    "/",
    response_model=CashMovementResponse,
)
def create_cash_movement(payload: CashMovementCreate):
    db: Session = SessionLocal()

    try:
        cash_register = (
            db.query(CashRegister)
            .filter(CashRegister.id == payload.cash_register_id)
            .first()
        )

        if cash_register is None:
            raise HTTPException(
                status_code=404,
                detail="Cash register not found",
            )

        if cash_register.status != "open":
            raise HTTPException(
                status_code=400,
                detail="Cash register is closed",
            )

        user = (
            db.query(User)
            .filter(User.id == payload.user_id)
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        movement = CashMovement(
            cash_register_id=payload.cash_register_id,
            user_id=payload.user_id,
            movement_type=payload.movement_type,
            amount=payload.amount,
            description=payload.description,
        )

        db.add(movement)
        db.commit()
        db.refresh(movement)

        return movement

    finally:
        db.close()