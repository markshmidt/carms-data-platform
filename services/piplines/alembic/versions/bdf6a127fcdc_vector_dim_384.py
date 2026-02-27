"""vector dim 384

Revision ID: bdf6a127fcdc
Revises: 0a179ce08a14
Create Date: 2026-02-25 16:45:58.541024

"""
from typing import Sequence, Union

from alembic import op
import sqlmodel
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'bdf6a127fcdc'
down_revision: Union[str, Sequence[str], None] = '0a179ce08a14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Change embedding column from 1536 to 384 dimensions
    op.alter_column('program', 'embedding',
               existing_type=Vector(1536),
               type_=Vector(384),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('program', 'embedding',
               existing_type=Vector(384),
               type_=Vector(1536),
               existing_nullable=True)
