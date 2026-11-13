import datetime
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import ForeignKey, Index, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, TimestampMixin

if TYPE_CHECKING:
    from app.models.photo import Photo


class PhotoProcessingJob(Base, TimestampMixin):
    __tablename__ = "photo_processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    photo_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("photos.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # 'pending', 'processing', 'completed', 'failed'
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    photo: Mapped["Photo"] = relationship("Photo", back_populates="processing_job")


Index("idx_processing_jobs_status_attempts", PhotoProcessingJob.status, PhotoProcessingJob.attempts)

