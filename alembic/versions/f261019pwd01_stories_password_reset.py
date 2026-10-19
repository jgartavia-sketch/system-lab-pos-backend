"""Recuperación de contraseña Stories y revocación de sesiones."""
from alembic import op
import sqlalchemy as sa
revision = "f261019pwd01"
down_revision = "f261019com01"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("stories_readers", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("stories_password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reader_id", sa.Integer(), sa.ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)))
    op.create_index("ix_stories_password_resets_reader_id", "stories_password_resets", ["reader_id"])

def downgrade():
    op.drop_table("stories_password_resets")
    op.drop_column("stories_readers", "session_version")
