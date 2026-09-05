"""add payment due date for automatic collection chain

Revision ID: c9f2a1d7e430
Revises: b8d42f6c1a20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9f2a1d7e430"
down_revision: Union[str, Sequence[str], None] = "b8d42f6c1a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("client_payments", sa.Column("due_date", sa.Date(), nullable=True))
    op.create_index("ix_client_payments_due_date", "client_payments", ["due_date"])
    op.execute(
        "UPDATE client_payments SET due_date = next_payment_date "
        "WHERE status != 'paid' AND due_date IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_client_payments_due_date", table_name="client_payments")
    op.drop_column("client_payments", "due_date")
