"""Initial schema with pgvector, users, events, photos, photo_faces, access, sessions, jobs, and audit logs.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from app.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension if PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Users table
    op.create_table(
        'users',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='organiser'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 3. Events table
    op.create_table(
        'events',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('organiser_id', GUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('event_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('access_type', sa.String(length=50), nullable=False, server_default='private'),
        sa.Column('access_code_hash', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organiser_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_organiser_id', 'events', ['organiser_id'], unique=False)
    op.create_index('ix_events_slug', 'events', ['slug'], unique=True)

    # 4. Photos table
    op.create_table(
        'photos',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('event_id', GUID(), nullable=False),
        sa.Column('uploaded_by', GUID(), nullable=True),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('thumbnail_path', sa.String(length=512), nullable=True),
        sa.Column('mime_type', sa.String(length=64), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('processing_status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_photos_event_id', 'photos', ['event_id'], unique=False)
    op.create_index('ix_photos_processing_status', 'photos', ['processing_status'], unique=False)
    op.create_index('ix_photos_is_public', 'photos', ['is_public'], unique=False)
    op.create_index('idx_photos_event_status', 'photos', ['event_id', 'processing_status'])
    op.create_index('idx_photos_event_public', 'photos', ['event_id', 'is_public'])

    # 5. Photo faces table
    op.create_table(
        'photo_faces',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('event_id', GUID(), nullable=False),
        sa.Column('photo_id', GUID(), nullable=False),
        sa.Column('embedding', Vector(128), nullable=False),
        sa.Column('bounding_box', sa.JSON(), nullable=False),
        sa.Column('detection_confidence', sa.Float(), nullable=False),
        sa.Column('landmarks', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_photo_faces_event_id', 'photo_faces', ['event_id'], unique=False)
    op.create_index('ix_photo_faces_photo_id', 'photo_faces', ['photo_id'], unique=False)
    op.create_index('idx_photo_faces_event_photo', 'photo_faces', ['event_id', 'photo_id'])

    # 6. Event access table
    op.create_table(
        'event_access',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('event_id', GUID(), nullable=False),
        sa.Column('attendee_id', GUID(), nullable=True),
        sa.Column('access_token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['attendee_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_event_access_event_id', 'event_access', ['event_id'], unique=False)
    op.create_index('ix_event_access_access_token_hash', 'event_access', ['access_token_hash'], unique=False)
    op.create_index('idx_event_access_event_token', 'event_access', ['event_id', 'access_token_hash'])

    # 7. Search sessions table
    op.create_table(
        'search_sessions',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('event_id', GUID(), nullable=False),
        sa.Column('attendee_id', GUID(), nullable=True),
        sa.Column('consent_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consent_purpose', sa.String(length=255), nullable=False, server_default='facial_recognition_search'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['attendee_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_search_sessions_event_id', 'search_sessions', ['event_id'], unique=False)
    op.create_index('ix_search_sessions_status', 'search_sessions', ['status'], unique=False)
    op.create_index('idx_search_sessions_event_status', 'search_sessions', ['event_id', 'status'])

    # 8. Photo processing jobs table
    op.create_table(
        'photo_processing_jobs',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('photo_id', GUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('photo_id')
    )
    op.create_index('ix_photo_processing_jobs_photo_id', 'photo_processing_jobs', ['photo_id'], unique=True)
    op.create_index('ix_photo_processing_jobs_status', 'photo_processing_jobs', ['status'], unique=False)
    op.create_index('idx_processing_jobs_status_attempts', 'photo_processing_jobs', ['status', 'attempts'])

    # 9. Audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('event_id', GUID(), nullable=True),
        sa.Column('user_id', GUID(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_event_id', 'audit_logs', ['event_id'], unique=False)
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('idx_audit_logs_event_action', 'audit_logs', ['event_id', 'action'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('photo_processing_jobs')
    op.drop_table('search_sessions')
    op.drop_table('event_access')
    op.drop_table('photo_faces')
    op.drop_table('photos')
    op.drop_table('events')
    op.drop_table('users')

