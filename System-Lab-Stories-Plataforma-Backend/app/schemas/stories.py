from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class ReaderRegisterRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=180)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=50)
    password: str = Field(min_length=8, max_length=72)
    referral_code: str | None = Field(default=None, max_length=16)

    @field_validator("full_name", "phone")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Este campo es obligatorio.")
        return value


class ReaderLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ReaderProfile(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str
    referral_code: str
    created_at: datetime


class ReaderAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    reader: ReaderProfile


class ReferralSummary(BaseModel):
    referral_code: str
    pending: int
    confirmed: int
    confirmed_toward_next_reward: int
    referrals_needed_for_next_reward: int
    available_rewards: int
    total_rewards_earned: int
    discount_percent_per_reward: int = 50


class ChapterSummary(BaseModel):
    number: int
    title: str
    status: str
    release_at: datetime | None = None
    can_read: bool = False
    can_download_pdf: bool = False


class SeasonSummary(BaseModel):
    number: int
    title: str
    access: str
    price_public: bool = False
    chapters: list[ChapterSummary]


class StorySummary(BaseModel):
    slug: str
    title: str
    tagline: str
    cover_url: str
    status: str
    seasons: list[SeasonSummary]


class ReaderDashboard(BaseModel):
    reader: ReaderProfile
    referrals: ReferralSummary
    stories: list[StorySummary]
