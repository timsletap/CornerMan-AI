"""add prompt_version and llm_model to analysis_sessions (AGT-11)

Revision ID: b9d3f6a7c4e5
Revises: a8c2e5f6b3d4
Create Date: 2026-11-13 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d3f6a7c4e5'
down_revision: Union[str, None] = 'a8c2e5f6b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_sessions', sa.Column('prompt_version', sa.Text(), nullable=True))
    op.add_column('analysis_sessions', sa.Column('llm_model', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_sessions', 'llm_model')
    op.drop_column('analysis_sessions', 'prompt_version')
