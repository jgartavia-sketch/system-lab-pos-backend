from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.customer import Customer
from app.models.sale import Sale
from app.schemas.customer import CustomerCreate
from app.schemas.customer import CustomerResponse
from app.schemas.customer import CustomerStatusUpdate
from app.schemas.customer import CustomerUpdate
from app.schemas.sale import SaleResponse
from app.api.routes.sales import build_sale_response


router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)


@router.get(
    "/",
    response_model=List[CustomerResponse],
)
def list_customers():
    db: Session = SessionLocal()

    try:
        customers = (
            db.query(Customer)
            .order_by(Customer.first_name.asc(), Customer.last_name.asc())
            .all()
        )

        return customers

    finally:
        db.close()


@router.get(
    "/{customer_id}/sales",
    response_model=List[SaleResponse],
)
def list_customer_sales(customer_id: int):
    db: Session = SessionLocal()

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado.",
            )

        sales = (
            db.query(Sale)
            .filter(Sale.customer_id == customer_id)
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
    "/{customer_id}",
    response_model=CustomerResponse,
)
def get_customer(customer_id: int):
    db: Session = SessionLocal()

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado.",
            )

        return customer

    finally:
        db.close()


@router.post(
    "/",
    response_model=CustomerResponse,
)
def create_customer(payload: CustomerCreate):
    db: Session = SessionLocal()

    try:
        customer = Customer(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone=payload.phone,
            identification_number=payload.identification_number,
            address=payload.address,
        )

        db.add(customer)
        db.commit()
        db.refresh(customer)

        return customer

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Ya existe un cliente con el mismo correo, teléfono o identificación.",
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
)
def update_customer(customer_id: int, payload: CustomerUpdate):
    db: Session = SessionLocal()

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado.",
            )

        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(customer, field, value)

        db.commit()
        db.refresh(customer)

        return customer

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Ya existe un cliente con el mismo correo, teléfono o identificación.",
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.patch(
    "/{customer_id}/status",
    response_model=CustomerResponse,
)
def update_customer_status(customer_id: int, payload: CustomerStatusUpdate):
    db: Session = SessionLocal()

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado.",
            )

        customer.is_active = payload.is_active

        db.commit()
        db.refresh(customer)

        return customer

    finally:
        db.close()