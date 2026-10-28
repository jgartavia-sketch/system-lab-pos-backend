"""Owner configures new POS businesses; preserve existing setups."""
from alembic import op
import sqlalchemy as sa
revision='f261027pos03'
down_revision='f261027zen02'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('pos_accounts',sa.Column('archived',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('pos_businesses',sa.Column('setup_complete',sa.Boolean(),nullable=False,server_default=sa.true()))
def downgrade():
    op.drop_column('pos_accounts','archived')
    op.drop_column('pos_businesses','setup_complete')
