"""memories

Revision ID: b4c8d2e6f1a7
Revises: a3b7c9d1e2f4
Create Date: 2026-10-07 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'b4c8d2e6f1a7'
down_revision: Union[str, Sequence[str], None] = 'a3b7c9d1e2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('memories',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('person', 'project', 'preference', 'commitment', 'event', 'decision', 'fact', name='memorykind', native_enum=False, length=20), server_default='fact', nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=True),
    sa.Column('source_type', sa.Enum('conversation', 'note', 'document', 'manual', name='memorysource', native_enum=False, length=20), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=True),
    sa.Column('source_label', sa.String(length=300), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('extraction', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('embedding', Vector(384), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_memories_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memories'))
    )
    op.create_index('ix_memories_embedding', 'memories', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_memories_workspace_id_kind', 'memories', ['workspace_id', 'kind'], unique=False)
    op.create_index('ix_memories_workspace_id_updated_at', 'memories', ['workspace_id', 'updated_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_memories_workspace_id_updated_at', table_name='memories')
    op.drop_index('ix_memories_workspace_id_kind', table_name='memories')
    op.drop_index('ix_memories_embedding', table_name='memories', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('memories')
