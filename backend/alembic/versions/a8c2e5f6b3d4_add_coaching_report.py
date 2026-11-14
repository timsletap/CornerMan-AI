"""add coaching_report to analysis_sessions (AGT-05)

Revision ID: a8c2e5f6b3d4
Revises: f7b1d4e5a2c3
Create Date: 2026-11-13 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a8c2e5f6b3d4'
down_revision: Union[str, None] = 'f7b1d4e5a2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'analysis_sessions',
        sa.Column('coaching_report', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('analysis_sessions', 'coaching_report')
