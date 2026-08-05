from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.cash_movement import CashMovement
from app.models.cash_register import CashRegister
from app.models.sale import Sale
from app.models.user import User
from app.schemas.cash_register import CashRegisterClose
from app.schemas.cash_register import CashRegisterOpen
from app.schemas.cash_register import CashRegisterResponse


router = APIRouter(
    prefix="/cash-registers",
    tags=["Cash Registers"],
)


@router.get(
    "/",
    response_model=List[CashRegisterResponse],
)
def list_cash_registers():
    db: Session = SessionLocal()

    try:
        cash_registers = (
            db.query(CashRegister)
            .order_by(CashRegister.opened_at.desc())
            .all()
        )

        return cash_registers

    finally:
        db.close()


@router.get(
    "/active",
    response_model=CashRegisterResponse,
)
def get_active_cash_register():
    db: Session = SessionLocal()

    try:
        cash_register = (
            db.query(CashRegister)
            .filter(CashRegister.status == "open")
            .order_by(CashRegister.opened_at.desc())
            .first()
        )

        if cash_register is None:
            raise HTTPException(
                status_code=404,
                detail="No active cash register found",
            )

        return cash_register

    finally:
        db.close()


@router.get(
    "/{cash_register_id}",
    response_model=CashRegisterResponse,
)
def get_cash_register(cash_register_id: int):
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

        return cash_register

    finally:
        db.close()


@router.post(
    "/open",
    response_model=CashRegisterResponse,
)
def open_cash_register(payload: CashRegisterOpen):
    db: Session = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == payload.opened_by)
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        active_cash_register = (
            db.query(CashRegister)
            .filter(CashRegister.status == "open")
            .first()
        )

        if active_cash_register is not None:
            raise HTTPException(
                status_code=400,
                detail="There is already an open cash register",
            )

        cash_register = CashRegister(
            opened_by=payload.opened_by,
            opening_amount=payload.opening_amount,
            status="open",
        )

        db.add(cash_register)
        db.commit()
        db.refresh(cash_register)

        return cash_register

    finally:
        db.close()


@router.post(
    "/{cash_register_id}/close",
    response_model=CashRegisterResponse,
)
def close_cash_register(cash_register_id: int, payload: CashRegisterClose):
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

        if cash_register.status != "open":
            raise HTTPException(
                status_code=400,
                detail="Cash register is already closed",
            )

        user = (
            db.query(User)
            .filter(User.id == payload.closed_by)
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        sales_total = (
            db.query(func.coalesce(func.sum(Sale.total), 0))
            .filter(Sale.cash_register_id == cash_register_id)
            .filter(Sale.status == "completed")
            .scalar()
        )

        movements_total = (
            db.query(func.coalesce(func.sum(CashMovement.amount), 0))
            .filter(CashMovement.cash_register_id == cash_register_id)
            .scalar()
        )

        expected_amount = (
            Decimal(cash_register.opening_amount)
            + Decimal(sales_total)
            + Decimal(movements_total)
        )

        difference_amount = payload.closing_amount - expected_amount

        cash_register.closed_by = payload.closed_by
        cash_register.closing_amount = payload.closing_amount
        cash_register.expected_amount = expected_amount
        cash_register.difference_amount = difference_amount
        cash_register.status = "closed"
        cash_register.closed_at = datetime.utcnow()

        db.commit()
        db.refresh(cash_register)

        return cash_register

    finally:
        db.close()