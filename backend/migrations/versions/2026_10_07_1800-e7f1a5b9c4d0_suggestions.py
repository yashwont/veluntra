"""suggestions

Revision ID: e7f1a5b9c4d0
Revises: d6e0f4a8b3c9
Create Date: 2026-10-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7f1a5b9c4d0'
down_revision: Union[str, Sequence[str], None] = 'd6e0f4a8b3c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('suggestions',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('email_action', 'email_follow_up', name='suggestionkind', native_enum=False, length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('priority', sa.Enum('low', 'medium', 'high', 'urgent', name='taskpriority', native_enum=False, length=20), nullable=False),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('source_id', sa.String(length=200), nullable=False),
    sa.Column('source_label', sa.String(length=300), nullable=True),
    sa.Column('status', sa.Enum('pending', 'accepted', 'dismissed', name='suggestionstatus', native_enum=False, length=20), server_default='pending', nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_suggestions_task_id_tasks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_suggestions_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_suggestions_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suggestions')),
    sa.UniqueConstraint('workspace_id', 'user_id', 'kind', 'source_type', 'source_id', name=op.f('uq_suggestions_workspace_id'))
    )
    op.create_index('ix_suggestions_workspace_id_user_id_status', 'suggestions', ['workspace_id', 'user_id', 'status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_suggestions_workspace_id_user_id_status', table_name='suggestions')
    op.drop_table('suggestions')
