"""integration accounts

Revision ID: d6e0f4a8b3c9
Revises: c5d9e3f7a2b8
Create Date: 2026-10-07 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd6e0f4a8b3c9'
down_revision: Union[str, Sequence[str], None] = 'c5d9e3f7a2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('integration_accounts',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.Enum('google', name='integrationprovider', native_enum=False, length=20), nullable=False),
    sa.Column('account_email', sa.String(length=320), nullable=True),
    sa.Column('scopes', postgresql.ARRAY(sa.String(length=300)), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('access_token_encrypted', sa.Text(), nullable=False),
    sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('active', 'needs_reauth', name='integrationstatus', native_enum=False, length=20), server_default='active', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_integration_accounts_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_integration_accounts_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_integration_accounts')),
    sa.UniqueConstraint('workspace_id', 'user_id', 'provider', name=op.f('uq_integration_accounts_workspace_id'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('integration_accounts')
