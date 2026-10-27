"""POS secure account activation."""
from alembic import op
import sqlalchemy as sa
revision='f261027zen01'
down_revision='f261019pwd01'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('pos_activations',sa.Column('account_id',sa.Integer(),sa.ForeignKey('pos_accounts.id'),primary_key=True),sa.Column('token_hash',sa.String(64),nullable=False,unique=True),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('used_at',sa.DateTime(timezone=True)))
    op.create_table('pos_receivables',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('pos_businesses.id'),nullable=False,index=True),
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('pos_orders.id'),nullable=False,unique=True),
        sa.Column('customer_id',sa.Integer(),sa.ForeignKey('pos_customers.id'),nullable=False),
        sa.Column('original',sa.Numeric(14,2),nullable=False),sa.Column('schedule',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('voided_at',sa.DateTime(timezone=True)),sa.Column('void_reason',sa.String(500)))
    op.create_table('pos_credit_payments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('pos_businesses.id'),nullable=False,index=True),
        sa.Column('receivable_id',sa.Integer(),sa.ForeignKey('pos_receivables.id'),nullable=False),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('pos_accounts.id'),nullable=False),
        sa.Column('register_id',sa.Integer(),sa.ForeignKey('pos_registers.id'),nullable=False),
        sa.Column('request_key',sa.String(36),nullable=False),sa.Column('request_digest',sa.String(64),nullable=False),
        sa.Column('amount',sa.Numeric(14,2),nullable=False),sa.Column('method',sa.String(20),nullable=False),
        sa.Column('reference',sa.String(100),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('voided_at',sa.DateTime(timezone=True)),sa.Column('void_reason',sa.String(500)),
        sa.Column('cash_movement_id',sa.Integer(),sa.ForeignKey('pos_movements.id'),unique=True),
        sa.Column('void_movement_id',sa.Integer(),sa.ForeignKey('pos_movements.id'),unique=True),
        sa.UniqueConstraint('business_id','request_key'))
def downgrade():
    op.drop_table('pos_credit_payments')
    op.drop_table('pos_receivables')
    op.drop_table('pos_activations')
