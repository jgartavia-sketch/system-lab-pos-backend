from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.payment_method import PaymentMethod
from app.schemas.payment_method import PaymentMethodCreate
from app.schemas.payment_method import PaymentMethodResponse
from app.schemas.payment_method import PaymentMethodStatusUpdate
from app.schemas.payment_method import PaymentMethodUpdate


router = APIRouter(
    prefix="/payment-methods",
    tags=["Payment Methods"],
)


@router.get(
    "/",
    response_model=List[PaymentMethodResponse],
)
def list_payment_methods():
    db: Session = SessionLocal()

    try:
        methods = (
            db.query(PaymentMethod)
            .order_by(PaymentMethod.name.asc())
            .all()
        )

        return methods

    finally:
        db.close()


@router.get(
    "/{payment_method_id}",
    response_model=PaymentMethodResponse,
)
def get_payment_method(payment_method_id: int):
    db: Session = SessionLocal()

    try:
        method = (
            db.query(PaymentMethod)
            .filter(PaymentMethod.id == payment_method_id)
            .first()
        )

        if not method:
            raise HTTPException(
                status_code=404,
                detail="Método de pago no encontrado.",
            )

        return method

    finally:
        db.close()


@router.post(
    "/",
    response_model=PaymentMethodResponse,
)
def create_payment_method(payload: PaymentMethodCreate):
    db: Session = SessionLocal()

    try:
        method = PaymentMethod(
            name=payload.name,
            description=payload.description,
        )

        db.add(method)
        db.commit()
        db.refresh(method)

        return method

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Ya existe un método de pago con ese nombre.",
        )

    finally:
        db.close()


@router.put(
    "/{payment_method_id}",
    response_model=PaymentMethodResponse,
)
def update_payment_method(
    payment_method_id: int,
    payload: PaymentMethodUpdate,
):
    db: Session = SessionLocal()

    try:
        method = (
            db.query(PaymentMethod)
            .filter(PaymentMethod.id == payment_method_id)
            .first()
        )

        if not method:
            raise HTTPException(
                status_code=404,
                detail="Método de pago no encontrado.",
            )

        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(method, field, value)

        db.commit()
        db.refresh(method)

        return method

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Ya existe un método de pago con ese nombre.",
        )

    finally:
        db.close()


@router.patch(
    "/{payment_method_id}/status",
    response_model=PaymentMethodResponse,
)
def update_payment_method_status(
    payment_method_id: int,
    payload: PaymentMethodStatusUpdate,
):
    db: Session = SessionLocal()

    try:
        method = (
            db.query(PaymentMethod)
            .filter(PaymentMethod.id == payment_method_id)
            .first()
        )

        if not method:
            raise HTTPException(
                status_code=404,
                detail="Método de pago no encontrado.",
            )

        method.is_active = payload.is_active

        db.commit()
        db.refresh(method)

        return method

    finally:
        db.close()