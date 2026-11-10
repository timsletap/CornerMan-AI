"""add hand_role to strike_events, stance columns to analysis_sessions (VIS-12)

Revision ID: e6a0c3d4f1b2
Revises: d5f9b2c3e0a1
Create Date: 2026-11-09 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6a0c3d4f1b2'
down_revision: Union[str, None] = 'd5f9b2c3e0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

hand_role = sa.Enum('LEAD', 'REAR', name='handrole')


def upgrade() -> None:
    hand_role.create(op.get_bind(), checkfirst=True)
    op.add_column('strike_events', sa.Column('hand_role', hand_role, nullable=True))
    op.add_column('analysis_sessions', sa.Column('stance_used', sa.String(length=16), nullable=True))
    op.add_column('analysis_sessions', sa.Column('stance_source', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_sessions', 'stance_source')
    op.drop_column('analysis_sessions', 'stance_used')
    op.drop_column('strike_events', 'hand_role')
    hand_role.drop(op.get_bind(), checkfirst=True)
