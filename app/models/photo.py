import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User
    from app.models.face import PhotoFace
    from app.models.job import PhotoProcessingJob


class Photo(Base, TimestampMixin):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    processing_status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # 'pending', 'processing', 'completed', 'failed'
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="photos")
    uploader: Mapped[Optional["User"]] = relationship("User", back_populates="uploaded_photos")
    faces: Mapped[List["PhotoFace"]] = relationship(
        "PhotoFace",
        back_populates="photo",
        cascade="all, delete-orphan",
    )
    processing_job: Mapped[Optional["PhotoProcessingJob"]] = relationship(
        "PhotoProcessingJob",
        back_populates="photo",
        uselist=False,
        cascade="all, delete-orphan",
    )


# Composite index for filtering photos by event and status/publicity
Index("idx_photos_event_status", Photo.event_id, Photo.processing_status)
Index("idx_photos_event_public", Photo.event_id, Photo.is_public)

