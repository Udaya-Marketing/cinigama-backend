"""Add restricted_faces table for blocking specific faces from selfie search.

Revision ID: 002_add_restricted_faces
Revises: 001_initial_schema
Create Date: 2026-11-21 23:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from app.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '002_add_restricted_faces'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'restricted_faces',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('event_id', GUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('embedding', Vector(128), nullable=False),
        sa.Column('bounding_box', sa.JSON(), nullable=True),
        sa.Column('detection_confidence', sa.Float(), nullable=True),
        sa.Column('thumbnail_path', sa.String(length=512), nullable=True),
        sa.Column('created_by', GUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_restricted_faces_event_id', 'restricted_faces', ['event_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_restricted_faces_event_id', table_name='restricted_faces')
    op.drop_table('restricted_faces')
