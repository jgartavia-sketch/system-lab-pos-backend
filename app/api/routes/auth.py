from datetime import datetime
from datetime import timezone

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.core.security import verify_password
from app.db.database import SessionLocal
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.auth import TokenResponse


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(payload: LoginRequest):
    db: Session = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == payload.email)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Credenciales inválidas.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Usuario inactivo.",
            )

        if not verify_password(
            payload.password,
            user.password_hash,
        ):
            raise HTTPException(
                status_code=401,
                detail="Credenciales inválidas.",
            )

        user.last_login_at = datetime.now(timezone.utc)
        db.commit()

        token = create_access_token(
            subject=str(user.id),
        )

        return TokenResponse(
            access_token=token,
        )

    finally:
        db.close()