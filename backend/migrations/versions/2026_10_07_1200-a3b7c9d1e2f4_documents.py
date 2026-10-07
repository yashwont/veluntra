"""documents and document chunks

Revision ID: a3b7c9d1e2f4
Revises: d6fa67f41f80
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'a3b7c9d1e2f4'
down_revision: Union[str, Sequence[str], None] = 'd6fa67f41f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Needs the pgvector build of Postgres (see docker-compose.yml)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('documents',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('uploaded_by_id', sa.Uuid(), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=150), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('status', sa.Enum('pending', 'processing', 'ready', 'failed', name='documentstatus', native_enum=False, length=20), server_default='pending', nullable=False),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name=op.f('fk_documents_uploaded_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_documents_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    op.create_index('ix_documents_workspace_id_created_at', 'documents', ['workspace_id', 'created_at'], unique=False)
    op.create_index('ix_documents_workspace_id_status', 'documents', ['workspace_id', 'status'], unique=False)

    op.create_table('document_chunks',
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', Vector(384), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_document_chunks_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks'))
    )
    op.create_index('ix_document_chunks_document_id_chunk_index', 'document_chunks', ['document_id', 'chunk_index'], unique=False)
    op.create_index('ix_document_chunks_workspace_id', 'document_chunks', ['workspace_id'], unique=False)
    op.create_index('ix_document_chunks_embedding', 'document_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_document_chunks_embedding', table_name='document_chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index('ix_document_chunks_workspace_id', table_name='document_chunks')
    op.drop_index('ix_document_chunks_document_id_chunk_index', table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_index('ix_documents_workspace_id_status', table_name='documents')
    op.drop_index('ix_documents_workspace_id_created_at', table_name='documents')
    op.drop_table('documents')
    # The vector extension is left installed: other objects may depend on it
