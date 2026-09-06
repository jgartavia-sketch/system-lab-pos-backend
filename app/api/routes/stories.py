import secrets
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, get_password_hash, verify_password
from app.core.config import settings
from app.db.database import get_db
from app.models.stories import StoriesReader, StoriesReferral, StoriesReward
from app.schemas.stories import (
    ReaderAuthResponse,
    ReaderDashboard,
    ReaderLoginRequest,
    ReaderProfile,
    ReaderRegisterRequest,
    ReferralSummary,
    ChapterContent,
    ChapterSummary,
    SeasonSummary,
    StorySummary,
)


router = APIRouter(prefix="/stories", tags=["System Lab Stories"])

STORY_SLUG = "the-voyager-space-hotel"
PREVIEW_EMAILS = {
    email.strip().lower()
    for email in settings.STORIES_PREVIEW_EMAILS.split(",")
    if email.strip()
}
CHAPTER_ONE_PATH = Path(__file__).resolve().parents[2] / "content" / "voyager_chapter_1.json"
CHAPTER_ONE_IMAGES_PATH = Path(__file__).resolve().parents[2] / "content" / "voyager_chapter_1_images"
CHAPTER_ONE_IMAGES = {
    "horizon-academy": "horizon-academy.jpeg",
    "scene-1-classroom": "scene-1-classroom.png",
    "scene-2": "scene-2.png",
    "scene-3-room": "scene-3-room.png",
    "scene-3-bus": "scene-3-bus.png",
    "scene-3-frank": "scene-3-frank.png",
    "scene-4-entrance": "scene-4-entrance.png",
    "scene-4-experiment": "scene-4-experiment.png",
    "scene-4-failure": "scene-4-failure.png",
    "scene-4-final": "scene-4-final.png",
    "chapter-final": "chapter-final.png",
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def has_preview_access(reader: StoriesReader) -> bool:
    return normalize_email(reader.email) in PREVIEW_EMAILS


def new_referral_code(db: Session) -> str:
    while True:
        code = secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:8]
        if not db.query(StoriesReader.id).filter(StoriesReader.referral_code == code).first():
            return code


def reader_profile(reader: StoriesReader) -> ReaderProfile:
    return ReaderProfile(
        id=reader.id,
        full_name=reader.full_name,
        email=reader.email,
        phone=reader.phone,
        referral_code=reader.referral_code,
        created_at=reader.created_at,
    )


def current_reader(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> StoriesReader:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Debés iniciar sesión.")
    payload = decode_access_token(authorization.split(" ", 1)[1])
    subject = payload.get("sub") if payload else None
    if not subject or not subject.startswith("stories:"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o vencida.")
    try:
        reader_id = int(subject.split(":", 1)[1])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida.") from exc
    reader = db.query(StoriesReader).filter(StoriesReader.id == reader_id).first()
    if not reader or not reader.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cuenta no disponible.")
    return reader


def referral_summary(db: Session, reader: StoriesReader) -> ReferralSummary:
    pending = db.query(func.count(StoriesReferral.id)).filter(
        StoriesReferral.referrer_id == reader.id,
        StoriesReferral.status == "pending",
    ).scalar() or 0
    confirmed = db.query(func.count(StoriesReferral.id)).filter(
        StoriesReferral.referrer_id == reader.id,
        StoriesReferral.status == "confirmed",
    ).scalar() or 0
    total_rewards = confirmed // 5
    available_rewards = db.query(func.count(StoriesReward.id)).filter(
        StoriesReward.reader_id == reader.id,
        StoriesReward.status == "available",
    ).scalar() or 0
    progress = confirmed % 5
    return ReferralSummary(
        referral_code=reader.referral_code,
        pending=pending,
        confirmed=confirmed,
        confirmed_toward_next_reward=progress,
        referrals_needed_for_next_reward=5 - progress,
        available_rewards=available_rewards,
        total_rewards_earned=total_rewards,
    )


def confirm_incoming_referral(db: Session, reader: StoriesReader) -> None:
    referral = db.query(StoriesReferral).filter(
        StoriesReferral.referred_reader_id == reader.id,
        StoriesReferral.status == "pending",
    ).with_for_update().first()
    if not referral:
        return
    referral.status = "confirmed"
    referral.confirmed_at = datetime.now(timezone.utc)
    confirmed = db.query(func.count(StoriesReferral.id)).filter(
        StoriesReferral.referrer_id == referral.referrer_id,
        StoriesReferral.status == "confirmed",
    ).scalar() or 0
    reward_number = confirmed // 5
    if confirmed % 5 == 0 and reward_number > 0:
        exists = db.query(StoriesReward.id).filter(
            StoriesReward.reader_id == referral.referrer_id,
            StoriesReward.reward_number == reward_number,
        ).first()
        if not exists:
            db.add(StoriesReward(reader_id=referral.referrer_id, reward_number=reward_number))
    db.commit()


@router.post("/auth/register", response_model=ReaderAuthResponse, status_code=status.HTTP_201_CREATED)
def register_reader(payload: ReaderRegisterRequest, db: Session = Depends(get_db)):
    email = normalize_email(payload.email)
    if db.query(StoriesReader.id).filter(func.lower(StoriesReader.email) == email).first():
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con este correo.")

    referrer = None
    if payload.referral_code:
        referral_code = payload.referral_code.strip().upper()
        referrer = db.query(StoriesReader).filter(StoriesReader.referral_code == referral_code).first()
        if not referrer:
            raise HTTPException(status_code=400, detail="El código de referido no es válido.")

    reader = StoriesReader(
        full_name=payload.full_name.strip(),
        email=email,
        phone=payload.phone.strip(),
        password_hash=get_password_hash(payload.password),
        referral_code=new_referral_code(db),
    )
    db.add(reader)
    try:
        db.flush()
        if referrer:
            db.add(StoriesReferral(referrer_id=referrer.id, referred_reader_id=reader.id))
        db.commit()
        db.refresh(reader)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No fue posible crear la cuenta.") from exc

    token = create_access_token(subject=f"stories:{reader.id}")
    return ReaderAuthResponse(access_token=token, reader=reader_profile(reader))


@router.post("/auth/login", response_model=ReaderAuthResponse)
def login_reader(payload: ReaderLoginRequest, db: Session = Depends(get_db)):
    reader = db.query(StoriesReader).filter(func.lower(StoriesReader.email) == normalize_email(payload.email)).first()
    if not reader or not verify_password(payload.password, reader.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    if not reader.is_active:
        raise HTTPException(status_code=403, detail="Esta cuenta está inactiva.")
    reader.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token(subject=f"stories:{reader.id}")
    return ReaderAuthResponse(access_token=token, reader=reader_profile(reader))


@router.get("/auth/me", response_model=ReaderProfile)
def me(reader: StoriesReader = Depends(current_reader)):
    return reader_profile(reader)


@router.get("/account", response_model=ReaderDashboard)
def account(reader: StoriesReader = Depends(current_reader), db: Session = Depends(get_db)):
    preview_access = has_preview_access(reader)
    return ReaderDashboard(
        reader=reader_profile(reader),
        referrals=referral_summary(db, reader),
        stories=[
            StorySummary(
                slug=STORY_SLUG,
                title="The Voyager Space Hotel",
                tagline="Hay destinos que se visitan. Otros cambian para siempre a quienes llegan.",
                cover_url="/images/voyager/hero-voyager-space-hotel.webp",
                status="coming_soon",
                seasons=[
                    SeasonSummary(
                        number=1,
                        title="Temporada 1",
                        access="granted",
                        chapters=[
                            ChapterSummary(
                                number=1,
                                title="El ruido del salón",
                                status="preview" if preview_access else "coming_soon",
                                can_read=preview_access,
                            ),
                            *[
                                ChapterSummary(
                                    number=number,
                                    title="Título por revelar",
                                    status="coming_soon",
                                    can_read=False,
                                )
                                for number in range(2, 7)
                            ],
                        ],
                    )
                ],
            )
        ],
    )


@router.get(
    "/{story_slug}/seasons/{season_number}/chapters/{chapter_number}",
    response_model=ChapterContent,
)
def read_chapter(
    story_slug: str,
    season_number: int,
    chapter_number: int,
    reader: StoriesReader = Depends(current_reader),
    db: Session = Depends(get_db),
):
    if story_slug != STORY_SLUG or season_number != 1 or chapter_number != 1:
        raise HTTPException(status_code=404, detail="Este capítulo todavía no está disponible.")
    if not has_preview_access(reader):
        raise HTTPException(status_code=403, detail="Este capítulo se encuentra en acceso anticipado.")
    if not CHAPTER_ONE_PATH.exists():
        raise HTTPException(status_code=503, detail="El contenido del capítulo no está disponible.")

    confirm_incoming_referral(db, reader)
    with CHAPTER_ONE_PATH.open(encoding="utf-8") as chapter_file:
        return ChapterContent.model_validate(json.load(chapter_file))


@router.get("/{story_slug}/seasons/{season_number}/chapters/{chapter_number}/images/{image_id}")
def read_chapter_image(
    story_slug: str,
    season_number: int,
    chapter_number: int,
    image_id: str,
    reader: StoriesReader = Depends(current_reader),
):
    if story_slug != STORY_SLUG or season_number != 1 or chapter_number != 1:
        raise HTTPException(status_code=404, detail="Imagen no disponible.")
    if not has_preview_access(reader):
        raise HTTPException(status_code=403, detail="Esta ilustración se encuentra en acceso anticipado.")
    filename = CHAPTER_ONE_IMAGES.get(image_id)
    if not filename:
        raise HTTPException(status_code=404, detail="Imagen no disponible.")
    image_path = CHAPTER_ONE_IMAGES_PATH / filename
    if not image_path.exists():
        raise HTTPException(status_code=503, detail="La ilustración no está disponible.")
    return FileResponse(image_path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/auth/confirm-reading-access", status_code=status.HTTP_204_NO_CONTENT)
def confirm_reading_access(reader: StoriesReader = Depends(current_reader), db: Session = Depends(get_db)):
    """Se invocará al abrir legítimamente el primer capítulo publicado."""
    confirm_incoming_referral(db, reader)
