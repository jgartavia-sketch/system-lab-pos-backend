"""add product print station and merge current migration heads

Revision ID: f260923prt01
Revises: e260909pos03, f260913fin01
"""
from alembic import op
import sqlalchemy as sa

revision = "f260923prt01"
down_revision = ("e260909pos03", "f260913fin01")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pos_products",
        sa.Column("print_station", sa.String(50), nullable=False, server_default="kitchen"),
    )
    # Existing drinks are routed to bar immediately. All other products retain
    # the backwards-compatible kitchen destination.
    op.execute(
        """
        UPDATE pos_products
        SET print_station = 'bar'
        WHERE lower(category) LIKE '%bebida%'
           OR lower(category) LIKE '%cóctel%'
           OR lower(category) LIKE '%coctel%'
           OR lower(category) = 'bar'
        """
    )


def downgrade():
    op.drop_column("pos_products", "print_station")
