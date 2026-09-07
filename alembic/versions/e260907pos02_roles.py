"""Roles por local y auditoría de autorizaciones; conserva cuentas y ventas."""
from alembic import op
import sqlalchemy as sa
revision = 'e260907pos02'
down_revision = 'e260906pos01'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('pos_orders', sa.Column('kitchen_status', sa.String(20)))
    op.add_column('pos_orders', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.execute("UPDATE pos_orders SET kitchen_status = status WHERE status IN ('queued','preparing','ready')")
    op.add_column('pos_memberships', sa.Column('role', sa.String(20), nullable=False, server_default='waiter'))
    op.add_column('pos_memberships', sa.Column('can_pay', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('pos_memberships', sa.Column('pin_hash', sa.String(256)))
    op.add_column('pos_memberships', sa.Column('pin_failed', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('pos_memberships', sa.Column('pin_locked_until', sa.DateTime(timezone=True)))
    # Existing memberships were explicitly granted by System Lab to its customers.
    op.execute("UPDATE pos_memberships SET role = 'owner'")
    op.create_table('pos_audit',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('pos_businesses.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('pos_accounts.id'), nullable=False),
        sa.Column('approver_id', sa.Integer(), sa.ForeignKey('pos_accounts.id')),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('pos_orders.id')),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_pos_audit_business_id', 'pos_audit', ['business_id'])

def downgrade():
    op.drop_column('pos_orders','revision')
    op.drop_column('pos_orders','kitchen_status')
    op.drop_table('pos_audit')
    for column in ('pin_locked_until','pin_failed','pin_hash','can_pay','role'):
        op.drop_column('pos_memberships', column)
