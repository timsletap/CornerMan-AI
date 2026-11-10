"""add measured_value_sw to error_flags (VIS-11)

Revision ID: d5f9b2c3e0a1
Revises: c4e8a1b2d9f0
Create Date: 2026-11-09 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5f9b2c3e0a1'
down_revision: Union[str, None] = 'c4e8a1b2d9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('error_flags', sa.Column('measured_value_sw', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('error_flags', 'measured_value_sw')
