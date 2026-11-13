# Import all models for Alembic autogenerate support
from app.models.base import Base
from app.models.user import User
from app.models.event import Event
from app.models.photo import Photo
from app.models.face import PhotoFace
from app.models.access import EventAccess
from app.models.search import SearchSession
from app.models.job import PhotoProcessingJob
from app.models.audit import AuditLog

__all__ = [
    "Base",
    "User",
    "Event",
    "Photo",
    "PhotoFace",
    "EventAccess",
    "SearchSession",
    "PhotoProcessingJob",
    "AuditLog",
]

