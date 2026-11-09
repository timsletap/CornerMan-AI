"""add target_track_id to analysis_sessions (VIS-09)

Revision ID: c4e8a1b2d9f0
Revises: b7d2f4a91c03
Create Date: 2026-11-09 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8a1b2d9f0'
down_revision: Union[str, None] = 'b7d2f4a91c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_sessions', sa.Column('target_track_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_sessions', 'target_track_id')
