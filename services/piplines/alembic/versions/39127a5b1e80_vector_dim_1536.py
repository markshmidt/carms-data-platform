"""vector dim 1536 (OpenAI text-embedding-3-small)

Revision ID: 39127a5b1e80
Revises: 087b8296c9db
Create Date: 2026-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '39127a5b1e80'
down_revision: Union[str, Sequence[str], None] = '087b8296c9db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE program SET embedding = NULL")
    op.alter_column('program', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=384),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE program SET embedding = NULL")
    op.alter_column('program', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=384),
               existing_nullable=True)
