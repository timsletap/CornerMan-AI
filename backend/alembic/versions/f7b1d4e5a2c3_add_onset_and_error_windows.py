"""add onset_ms to strike_events, window columns to error_flags (VIS-13, VIS-14)

Revision ID: f7b1d4e5a2c3
Revises: e6a0c3d4f1b2
Create Date: 2026-11-09 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7b1d4e5a2c3'
down_revision: Union[str, None] = 'e6a0c3d4f1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('strike_events', sa.Column('onset_ms', sa.Integer(), nullable=True))
    op.add_column('error_flags', sa.Column('window_start_ms', sa.Integer(), nullable=True))
    op.add_column('error_flags', sa.Column('window_end_ms', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('error_flags', 'window_end_ms')
    op.drop_column('error_flags', 'window_start_ms')
    op.drop_column('strike_events', 'onset_ms')
