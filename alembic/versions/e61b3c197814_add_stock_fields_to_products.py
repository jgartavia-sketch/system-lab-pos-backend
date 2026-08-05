"""add stock fields to products

Revision ID: e61b3c197814
Revises: 33254529fd61
Create Date: 2026-06-06 11:12:53.046735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e61b3c197814"
down_revision: Union[str, Sequence[str], None] = "33254529fd61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "stock_quantity",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "products",
        sa.Column(
            "minimum_stock",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "minimum_stock")
    op.drop_column("products", "stock_quantity")