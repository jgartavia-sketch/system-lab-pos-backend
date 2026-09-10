"""Financial ledger, pricing by fulfillment and private SL Connect binding."""
from alembic import op
import sqlalchemy as sa
revision='e260909pos03'
down_revision='e260907pos02'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('pos_businesses',sa.Column('service_rate',sa.Numeric(5,2),nullable=False,server_default='0'))
    op.add_column('pos_products',sa.Column('packaging_fee',sa.Numeric(14,2),nullable=False,server_default='0'))
    op.add_column('pos_products',sa.Column('cost_known',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column('pos_orders',sa.Column('source_channel',sa.String(20),nullable=False,server_default='pos'))
    op.add_column('pos_orders',sa.Column('fulfillment',sa.String(20),nullable=False,server_default='dine_in'))
    op.add_column('pos_orders',sa.Column('external_id',sa.String(80)))
    op.add_column('pos_orders',sa.Column('packaging_total',sa.Numeric(14,2),nullable=False,server_default='0'))
    op.add_column('pos_orders',sa.Column('service_total',sa.Numeric(14,2),nullable=False,server_default='0'))
    op.create_index('uq_pos_order_external','pos_orders',['business_id','external_id'],unique=True)
    op.create_table('pos_financial_entries',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('pos_businesses.id'),nullable=False),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('pos_accounts.id'),nullable=False),
        sa.Column('request_key',sa.String(36),nullable=False),sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('kind',sa.String(30),nullable=False),sa.Column('amount',sa.Numeric(14,2),nullable=False),
        sa.Column('category',sa.String(80),nullable=False),sa.Column('method',sa.String(20),nullable=False),
        sa.Column('reason',sa.String(500),nullable=False),sa.Column('supplier',sa.String(160),nullable=False,server_default=''),
        sa.Column('reference',sa.String(100),nullable=False,server_default=''),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('cash_movement_id',sa.Integer(),sa.ForeignKey('pos_movements.id'),unique=True),
        sa.Column('void_movement_id',sa.Integer(),sa.ForeignKey('pos_movements.id'),unique=True),
        sa.Column('voided_at',sa.DateTime(timezone=True)),sa.Column('void_reason',sa.String(500)),
        sa.UniqueConstraint('business_id','request_key',name='uq_pos_financial_request'))
    op.create_index('ix_pos_financial_entries_business_id','pos_financial_entries',['business_id'])
    op.create_table('pos_connect_links',
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('pos_businesses.id'),primary_key=True),
        sa.Column('provider',sa.String(30),unique=True,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    op.drop_table('pos_connect_links'); op.drop_table('pos_financial_entries')
    op.drop_index('uq_pos_order_external',table_name='pos_orders')
    for name in ('service_total','packaging_total','external_id','fulfillment','source_channel'): op.drop_column('pos_orders',name)
    op.drop_column('pos_products','cost_known'); op.drop_column('pos_products','packaging_fee'); op.drop_column('pos_businesses','service_rate')
