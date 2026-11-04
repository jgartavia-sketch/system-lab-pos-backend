"""Idempotent credit checkout with an optional first payment."""
from alembic import op
import sqlalchemy as sa

revision = 'f261103pos05'
down_revision = 'f261102pos04'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pos_receivables') as batch:
        batch.add_column(sa.Column('checkout_key', sa.String(36), nullable=True))
        batch.add_column(sa.Column('checkout_digest', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_pos_receivable_checkout', ['business_id', 'checkout_key'])


def downgrade():
    with op.batch_alter_table('pos_receivables') as batch:
        batch.drop_constraint('uq_pos_receivable_checkout', type_='unique')
        batch.drop_column('checkout_digest')
        batch.drop_column('checkout_key')
