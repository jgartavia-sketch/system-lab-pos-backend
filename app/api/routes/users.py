from typing import List

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserCreate
from app.schemas.user import UserResponse
from app.schemas.user import UserUpdate


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/",
    response_model=List[UserResponse],
)
def list_users():
    db: Session = SessionLocal()

    try:
        users = (
            db.query(User)
            .order_by(User.id.asc())
            .all()
        )

        return users

    finally:
        db.close()


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(user_id: int):
    db: Session = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado.",
            )

        return user

    finally:
        db.close()


@router.post(
    "/",
    response_model=UserResponse,
)
def create_user(payload: UserCreate):
    db: Session = SessionLocal()

    try:
        existing_user = (
            db.query(User)
            .filter(User.email == payload.email)
            .first()
        )

        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="El correo ya está registrado.",
            )

        role = (
            db.query(Role)
            .filter(Role.id == payload.role_id)
            .first()
        )

        if not role:
            raise HTTPException(
                status_code=404,
                detail="Rol no encontrado.",
            )

        user = User(
            role_id=payload.role_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            password_hash=get_password_hash(
                payload.password
            ),
            phone=payload.phone,
            is_active=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    finally:
        db.close()


@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
def update_user(
    user_id: int,
    payload: UserUpdate,
):
    db: Session = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado.",
            )

        if payload.email and payload.email != user.email:
            existing_user = (
                db.query(User)
                .filter(User.email == payload.email)
                .first()
            )

            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail="El correo ya está registrado.",
                )

            user.email = payload.email

        if payload.role_id is not None:
            role = (
                db.query(Role)
                .filter(Role.id == payload.role_id)
                .first()
            )

            if not role:
                raise HTTPException(
                    status_code=404,
                    detail="Rol no encontrado.",
                )

            user.role_id = payload.role_id

        if payload.first_name is not None:
            user.first_name = payload.first_name

        if payload.last_name is not None:
            user.last_name = payload.last_name

        if payload.phone is not None:
            user.phone = payload.phone

        if payload.is_active is not None:
            user.is_active = payload.is_active

        db.commit()
        db.refresh(user)

        return user

    finally:
        db.close()


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
)
def update_user_status(
    user_id: int,
    is_active: bool,
):
    db: Session = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado.",
            )

        user.is_active = is_active

        db.commit()
        db.refresh(user)

        return user

    finally:
        db.close()