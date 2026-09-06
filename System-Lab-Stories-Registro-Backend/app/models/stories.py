from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class StoriesReader(Base):
    __tablename__ = "stories_readers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(180), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    referral_code = Column(String(16), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    outgoing_referrals = relationship(
        "StoriesReferral",
        foreign_keys="StoriesReferral.referrer_id",
        back_populates="referrer",
        cascade="all, delete-orphan",
    )
    incoming_referral = relationship(
        "StoriesReferral",
        foreign_keys="StoriesReferral.referred_reader_id",
        back_populates="referred_reader",
        uselist=False,
    )
    rewards = relationship("StoriesReward", back_populates="reader", cascade="all, delete-orphan")


class StoriesReferral(Base):
    __tablename__ = "stories_referrals"
    __table_args__ = (
        UniqueConstraint("referred_reader_id", name="uq_stories_referral_referred_reader"),
        CheckConstraint("referrer_id <> referred_reader_id", name="ck_stories_referral_not_self"),
    )

    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False, index=True)
    referred_reader_id = Column(Integer, ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    referrer = relationship("StoriesReader", foreign_keys=[referrer_id], back_populates="outgoing_referrals")
    referred_reader = relationship("StoriesReader", foreign_keys=[referred_reader_id], back_populates="incoming_referral")


class StoriesReward(Base):
    __tablename__ = "stories_rewards"
    __table_args__ = (
        UniqueConstraint("reader_id", "reward_number", name="uq_stories_reward_reader_number"),
        CheckConstraint("discount_percent = 50", name="ck_stories_reward_discount"),
    )

    id = Column(Integer, primary_key=True)
    reader_id = Column(Integer, ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False, index=True)
    reward_number = Column(Integer, nullable=False)
    discount_percent = Column(Integer, nullable=False, default=50)
    status = Column(String(20), nullable=False, default="available")
    redeemed_season_number = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)

    reader = relationship("StoriesReader", back_populates="rewards")
