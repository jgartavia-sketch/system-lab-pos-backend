"""add customer id to sales

Revision ID: d21586557b9b
Revises: f558a85e5f1d
Create Date: 2026-06-06 14:56:56.826075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d21586557b9b"
down_revision: Union[str, Sequence[str], None] = "f558a85e5f1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "sales",
        sa.Column("customer_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        op.f("ix_sales_customer_id"),
        "sales",
        ["customer_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_sales_customer_id_customers",
        "sales",
        "customers",
        ["customer_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "fk_sales_customer_id_customers",
        "sales",
        type_="foreignkey",
    )

    op.drop_index(
        op.f("ix_sales_customer_id"),
        table_name="sales",
    )

    op.drop_column("sales", "customer_id")