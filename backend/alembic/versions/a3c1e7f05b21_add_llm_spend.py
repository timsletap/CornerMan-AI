"""add llm_spend for the rolling hourly LLM spend cap (PLT-05)

Revision ID: a3c1e7f05b21
Revises: 5fd32ea992c7
Create Date: 2026-10-21 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a3c1e7f05b21'
down_revision: Union[str, None] = '5fd32ea992c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_spend',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['analysis_sessions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_llm_spend_user_id'), 'llm_spend', ['user_id'], unique=False)
    op.create_index(op.f('ix_llm_spend_created_at'), 'llm_spend', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_llm_spend_created_at'), table_name='llm_spend')
    op.drop_index(op.f('ix_llm_spend_user_id'), table_name='llm_spend')
    op.drop_table('llm_spend')
