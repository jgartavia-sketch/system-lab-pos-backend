"""add client events calendar
Revision ID: f260913evt01
Revises: c9f2a1d7e430
"""
from alembic import op
import sqlalchemy as sa
revision = "f260913evt01"
down_revision = "c9f2a1d7e430"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("client_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_client_events_client_id", "client_events", ["client_id"])
    op.create_index("ix_client_events_event_date", "client_events", ["event_date"])

def downgrade():
    op.drop_index("ix_client_events_event_date", table_name="client_events")
    op.drop_index("ix_client_events_client_id", table_name="client_events")
    op.drop_table("client_events")
