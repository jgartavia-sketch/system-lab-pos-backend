"""add System Lab business finances
Revision ID: f260913fin01
Revises: f260913evt01
"""
from alembic import op
import sqlalchemy as sa
revision = "f260913fin01"
down_revision = "f260913evt01"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("business_finance_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("managed_clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("movement_type", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(14,2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CRC"),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("concept", sa.String(180), nullable=False),
        sa.Column("payment_method", sa.String(60), nullable=True),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for col in ["client_id","movement_type","currency","category","movement_date"]:
        op.create_index(f"ix_business_finance_movements_{col}", "business_finance_movements", [col])

def downgrade():
    for col in ["movement_date","category","currency","movement_type","client_id"]:
        op.drop_index(f"ix_business_finance_movements_{col}", table_name="business_finance_movements")
    op.drop_table("business_finance_movements")
