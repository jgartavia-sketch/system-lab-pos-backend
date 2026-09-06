"""create stories readers, referrals and rewards

Revision ID: 4b7d8e9f1a20
Revises: c9f2a1d7e430
"""

from alembic import op
import sqlalchemy as sa


revision = "4b7d8e9f1a20"
down_revision = "c9f2a1d7e430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stories_readers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(length=180), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("referral_code", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_stories_readers_email"),
        sa.UniqueConstraint("referral_code", name="uq_stories_readers_referral_code"),
    )
    op.create_index("ix_stories_readers_email", "stories_readers", ["email"])
    op.create_index("ix_stories_readers_referral_code", "stories_readers", ["referral_code"])

    op.create_table(
        "stories_referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_reader_id", sa.Integer(), sa.ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("referrer_id <> referred_reader_id", name="ck_stories_referral_not_self"),
        sa.UniqueConstraint("referred_reader_id", name="uq_stories_referral_referred_reader"),
    )
    op.create_index("ix_stories_referrals_referrer_id", "stories_referrals", ["referrer_id"])
    op.create_index("ix_stories_referrals_status", "stories_referrals", ["status"])

    op.create_table(
        "stories_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reader_id", sa.Integer(), sa.ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reward_number", sa.Integer(), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="available"),
        sa.Column("redeemed_season_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("discount_percent = 50", name="ck_stories_reward_discount"),
        sa.UniqueConstraint("reader_id", "reward_number", name="uq_stories_reward_reader_number"),
    )
    op.create_index("ix_stories_rewards_reader_id", "stories_rewards", ["reader_id"])


def downgrade() -> None:
    op.drop_table("stories_rewards")
    op.drop_table("stories_referrals")
    op.drop_table("stories_readers")
