"""vector dim 768

Revision ID: 2f31beab6b3c
Revises: bdf6a127fcdc
Create Date: 2026-02-25 23:21:42.792115

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '2f31beab6b3c'
down_revision: Union[str, Sequence[str], None] = 'bdf6a127fcdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE program SET embedding = NULL")
    op.alter_column('program', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=384),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE program SET embedding = NULL")
    op.alter_column('program', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=384),
               existing_nullable=True)
