"""vector dim 384

Revision ID: 087b8296c9db
Revises: 2f31beab6b3c
Create Date: 2026-02-26 23:20:55.885051

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '087b8296c9db'
down_revision: Union[str, Sequence[str], None] = '2f31beab6b3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE program SET embedding = NULL")
    op.alter_column('program', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=384),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE program SET embedding = NULL")
    op.alter_column('program', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=384),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               existing_nullable=True)
