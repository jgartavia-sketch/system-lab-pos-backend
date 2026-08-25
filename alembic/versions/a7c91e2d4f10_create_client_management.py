"""create client management dashboard tables

Revision ID: a7c91e2d4f10
Revises: d21586557b9b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c91e2d4f10"
down_revision: Union[str, Sequence[str], None] = "d21586557b9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_managed_clients_name", "managed_clients", ["name"])
    op.create_index("ix_managed_clients_slug", "managed_clients", ["slug"])

    op.create_table(
        "client_service_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_key", sa.String(60), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("client_id", "service_key", name="uq_client_service"),
    )
    op.create_index("ix_client_service_statuses_client_id", "client_service_statuses", ["client_id"])
    op.create_index("ix_client_service_statuses_service_key", "client_service_statuses", ["service_key"])

    op.create_table(
        "project_milestones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(20), server_default="medium", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_project_milestones_client_id", "project_milestones", ["client_id"])
    op.create_index("ix_project_milestones_status", "project_milestones", ["status"])

    op.create_table(
        "client_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("managed_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept", sa.String(180), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="CRC", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_client_payments_client_id", "client_payments", ["client_id"])
    op.create_index("ix_client_payments_status", "client_payments", ["status"])

    clients = sa.table(
        "managed_clients",
        sa.column("name", sa.String), sa.column("slug", sa.String), sa.column("website_url", sa.String),
    )
    op.bulk_insert(clients, [
        {"name": "Shirley's", "slug": "shirleys", "website_url": "https://www.shirleyscr.com"},
        {"name": "Taller Automotriz Jamiro", "slug": "jamiro", "website_url": "https://www.jamirosc.com"},
        {"name": "AgroMind", "slug": "agromind", "website_url": "https://www.agromindcr.es"},
        {"name": "Zenit Salon", "slug": "zenit", "website_url": "https://zenitsalon.com"},
        {"name": "Bryan Villalobos", "slug": "bryan-villalobos", "website_url": "https://www.bryanvillalobos.com"},
        {"name": "System Lab", "slug": "system-lab", "website_url": "https://www.systemlabcr.com"},
        {"name": "My", "slug": "my", "website_url": None},
    ])


def downgrade() -> None:
    op.drop_table("client_payments")
    op.drop_table("project_milestones")
    op.drop_table("client_service_statuses")
    op.drop_index("ix_managed_clients_slug", table_name="managed_clients")
    op.drop_index("ix_managed_clients_name", table_name="managed_clients")
    op.drop_table("managed_clients")
