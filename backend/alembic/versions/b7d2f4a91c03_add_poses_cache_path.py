"""add poses_cache_path to analysis_sessions (VIS-08)

Revision ID: b7d2f4a91c03
Revises: a3c1e7f05b21
Create Date: 2026-10-21 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d2f4a91c03'
down_revision: Union[str, None] = 'a3c1e7f05b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_sessions', sa.Column('poses_cache_path', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_sessions', 'poses_cache_path')
