"""Multiple bills per table and durable purchase loyalty delivery."""
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = 'f261102pos04'
down_revision = 'f261027pos03'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pos_orders', sa.Column('table_session', sa.String(36)))
    op.create_index('ix_pos_orders_table_session', 'pos_orders', ['table_session'])
    op.add_column('pos_orders', sa.Column('split_parent_id', sa.Integer(), sa.ForeignKey('pos_orders.id')))
    op.add_column('pos_orders', sa.Column('preparation_order_id', sa.Integer(), sa.ForeignKey('pos_orders.id')))
    op.add_column('pos_orders', sa.Column('loyalty_code', sa.String(100)))
    op.add_column('pos_orders', sa.Column('loyalty_name', sa.String(160)))
    op.add_column('pos_orders', sa.Column('loyalty_status', sa.String(20), nullable=False, server_default='none'))
    op.add_column('pos_orders', sa.Column('loyalty_points', sa.Integer()))
    op.create_table('pos_bill_splits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('pos_businesses.id'), nullable=False, index=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('pos_orders.id'), nullable=False),
        sa.Column('request_key', sa.String(36), nullable=False),
        sa.Column('request_digest', sa.String(64), nullable=False),
        sa.Column('child_ids', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('business_id', 'request_key'))
    op.create_table('pos_loyalty_operations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('pos_businesses.id'), nullable=False, index=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('pos_orders.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(500)),
        sa.Column('result', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('business_id', 'order_id', 'kind'))
    connection = op.get_bind()
    active = connection.execute(sa.text("SELECT id,business_id,table_number FROM pos_orders WHERE table_number IS NOT NULL AND status IN ('open','queued','preparing','ready')")).mappings()
    sessions = {}
    for order in active:
        key = (order['business_id'], order['table_number'])
        session = sessions.setdefault(key, str(uuid4()))
        connection.execute(sa.text('UPDATE pos_orders SET table_session=:session WHERE id=:id'), {'session': session, 'id': order['id']})


def downgrade():
    op.drop_table('pos_loyalty_operations')
    op.drop_table('pos_bill_splits')
    for column in ('loyalty_points', 'loyalty_status', 'loyalty_name', 'loyalty_code', 'preparation_order_id', 'split_parent_id'):
        op.drop_column('pos_orders', column)
    op.drop_index('ix_pos_orders_table_session', table_name='pos_orders')
    op.drop_column('pos_orders', 'table_session')
