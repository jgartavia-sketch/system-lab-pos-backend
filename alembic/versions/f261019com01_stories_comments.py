"""Opiniones y respuestas de Stories; sin modificar tablas existentes."""
from alembic import op
import sqlalchemy as sa
revision = "f261019com01"
down_revision = "f260923prt01"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("stories_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reader_id", sa.Integer(), sa.ForeignKey("stories_readers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("stories_comments.id", ondelete="CASCADE")),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("rating", sa.Integer()),
        sa.Column("anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("character", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_stories_comment_rating"),
        sa.CheckConstraint("(parent_id IS NULL AND rating IS NOT NULL AND character IS NULL) OR (parent_id IS NOT NULL AND rating IS NULL)", name="ck_stories_comment_kind"))
    op.create_index("ix_stories_comments_reader_id", "stories_comments", ["reader_id"])
    op.create_index("ix_stories_comments_parent_id", "stories_comments", ["parent_id"])

def downgrade():
    op.drop_table("stories_comments")
