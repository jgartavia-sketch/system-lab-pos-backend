"""Unified Zenit catalog and durable transaction intents."""
from alembic import op
import sqlalchemy as sa
revision='f261027zen02'
down_revision='f261027zen01'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('pos_products',sa.Column('remote_id',sa.String(80)))
    op.add_column('pos_products',sa.Column('remote_kind',sa.String(20)))
    op.add_column('pos_products',sa.Column('duration_minutes',sa.Integer()))
    op.add_column('pos_customers',sa.Column('remote_id',sa.String(80)))
    op.add_column('pos_orders',sa.Column('invoice_number',sa.String(100)))
    op.add_column('pos_connect_links',sa.Column('synced_at',sa.DateTime(timezone=True)))
    op.create_table('pos_bridge_operations',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('pos_businesses.id'),nullable=False,index=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('pos_accounts.id'),nullable=False),
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('pos_orders.id')),
        sa.Column('register_id',sa.Integer(),sa.ForeignKey('pos_registers.id')),
        sa.Column('key',sa.String(36),nullable=False,unique=True),
        sa.Column('local_path',sa.String(200),nullable=False),sa.Column('local_body',sa.JSON(),nullable=False),
        sa.Column('remote_path',sa.String(200),nullable=False),sa.Column('remote_body',sa.JSON(),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),sa.Column('result',sa.JSON()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
def downgrade():
    op.drop_table('pos_bridge_operations')
    op.drop_column('pos_connect_links','synced_at')
    op.drop_column('pos_orders','invoice_number')
    op.drop_column('pos_customers','remote_id')
    op.drop_column('pos_products','duration_minutes')
    op.drop_column('pos_products','remote_kind')
    op.drop_column('pos_products','remote_id')
