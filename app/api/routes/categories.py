from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.category import Category
from app.schemas.category import CategoryCreate
from app.schemas.category import CategoryResponse
from app.schemas.category import CategoryUpdate


router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


@router.get(
    "/",
    response_model=List[CategoryResponse],
)
def list_categories():
    db: Session = SessionLocal()

    try:
        categories = (
            db.query(Category)
            .order_by(Category.display_order.asc(), Category.name.asc())
            .all()
        )

        return categories

    finally:
        db.close()


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
)
def get_category(category_id: int):
    db: Session = SessionLocal()

    try:
        category = (
            db.query(Category)
            .filter(Category.id == category_id)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Categoría no encontrada.",
            )

        return category

    finally:
        db.close()


@router.post(
    "/",
    response_model=CategoryResponse,
)
def create_category(payload: CategoryCreate):
    db: Session = SessionLocal()

    try:
        existing_category = (
            db.query(Category)
            .filter(Category.name == payload.name)
            .first()
        )

        if existing_category:
            raise HTTPException(
                status_code=400,
                detail="La categoría ya existe.",
            )

        category = Category(
            name=payload.name,
            description=payload.description,
            display_order=payload.display_order,
            is_active=True,
        )

        db.add(category)
        db.commit()
        db.refresh(category)

        return category

    finally:
        db.close()


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
):
    db: Session = SessionLocal()

    try:
        category = (
            db.query(Category)
            .filter(Category.id == category_id)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Categoría no encontrada.",
            )

        if payload.name and payload.name != category.name:
            existing_category = (
                db.query(Category)
                .filter(Category.name == payload.name)
                .first()
            )

            if existing_category:
                raise HTTPException(
                    status_code=400,
                    detail="La categoría ya existe.",
                )

            category.name = payload.name

        if payload.description is not None:
            category.description = payload.description

        if payload.display_order is not None:
            category.display_order = payload.display_order

        if payload.is_active is not None:
            category.is_active = payload.is_active

        db.commit()
        db.refresh(category)

        return category

    finally:
        db.close()


@router.patch(
    "/{category_id}/status",
    response_model=CategoryResponse,
)
def update_category_status(
    category_id: int,
    is_active: bool,
):
    db: Session = SessionLocal()

    try:
        category = (
            db.query(Category)
            .filter(Category.id == category_id)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Categoría no encontrada.",
            )

        category.is_active = is_active

        db.commit()
        db.refresh(category)

        return category

    finally:
        db.close()