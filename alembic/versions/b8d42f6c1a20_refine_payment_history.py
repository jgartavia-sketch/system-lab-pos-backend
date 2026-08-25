"""refine payment history and remove accidental client

Revision ID: b8d42f6c1a20
Revises: a7c91e2d4f10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d42f6c1a20"
down_revision: Union[str, Sequence[str], None] = "a7c91e2d4f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Este registro provino de interpretar literalmente "My" en el boceto.
    op.execute("DELETE FROM managed_clients WHERE slug = 'my'")

    op.alter_column("client_payments", "concept", new_column_name="product_service")
    op.alter_column("client_payments", "amount", new_column_name="value")
    op.alter_column("client_payments", "due_date", new_column_name="next_payment_date")
    op.alter_column(
        "client_payments",
        "paid_at",
        new_column_name="payment_date",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.Date(),
        postgresql_using="paid_at::date",
    )
    op.alter_column("client_payments", "notes", new_column_name="detail")
    op.add_column("client_payments", sa.Column("period_start", sa.Date(), nullable=True))
    op.add_column("client_payments", sa.Column("period_end", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("client_payments", "period_end")
    op.drop_column("client_payments", "period_start")
    op.alter_column("client_payments", "detail", new_column_name="notes")
    op.alter_column(
        "client_payments",
        "payment_date",
        new_column_name="paid_at",
        existing_type=sa.Date(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="payment_date::timestamp with time zone",
    )
    op.alter_column("client_payments", "next_payment_date", new_column_name="due_date")
    op.alter_column("client_payments", "value", new_column_name="amount")
    op.alter_column("client_payments", "product_service", new_column_name="concept")
    op.execute(
        "INSERT INTO managed_clients (name, slug, is_active) "
        "VALUES ('My', 'my', true) ON CONFLICT (slug) DO NOTHING"
    )
