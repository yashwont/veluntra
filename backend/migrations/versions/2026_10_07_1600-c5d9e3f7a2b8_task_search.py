"""task full-text search

Revision ID: c5d9e3f7a2b8
Revises: b4c8d2e6f1a7
Create Date: 2026-10-07 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5d9e3f7a2b8'
down_revision: Union[str, Sequence[str], None] = 'b4c8d2e6f1a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tasks', sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('english', coalesce(title, '')), 'A') || setweight(to_tsvector('english', coalesce(description, '')), 'B')", persisted=True), nullable=False))
    op.create_index('ix_tasks_search_vector', 'tasks', ['search_vector'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tasks_search_vector', table_name='tasks', postgresql_using='gin')
    op.drop_column('tasks', 'search_vector')
