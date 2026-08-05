"""create customers table

Revision ID: f558a85e5f1d
Revises: e61b3c197814
Create Date: 2026-06-06 13:28:32.272391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f558a85e5f1d"
down_revision: Union[str, Sequence[str], None] = "e61b3c197814"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("identification_number", sa.String(length=100), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_customers_email"),
        "customers",
        ["email"],
        unique=True,
    )

    op.create_index(
        op.f("ix_customers_first_name"),
        "customers",
        ["first_name"],
        unique=False,
    )

    op.create_index(
        op.f("ix_customers_id"),
        "customers",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_customers_identification_number"),
        "customers",
        ["identification_number"],
        unique=True,
    )

    op.create_index(
        op.f("ix_customers_last_name"),
        "customers",
        ["last_name"],
        unique=False,
    )

    op.create_index(
        op.f("ix_customers_phone"),
        "customers",
        ["phone"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_customers_phone"),
        table_name="customers",
    )

    op.drop_index(
        op.f("ix_customers_last_name"),
        table_name="customers",
    )

    op.drop_index(
        op.f("ix_customers_identification_number"),
        table_name="customers",
    )

    op.drop_index(
        op.f("ix_customers_id"),
        table_name="customers",
    )

    op.drop_index(
        op.f("ix_customers_first_name"),
        table_name="customers",
    )

    op.drop_index(
        op.f("ix_customers_email"),
        table_name="customers",
    )

    op.drop_table("customers")