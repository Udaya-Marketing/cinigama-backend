import datetime
import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.photo import Photo
    from app.models.face import PhotoFace
    from app.models.access import EventAccess
    from app.models.search import SearchSession


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    organiser_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    access_type: Mapped[str] = mapped_column(
        String(50),
        default="private",
        nullable=False,
    )  # 'public', 'private', 'code_protected'
    access_code_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default="active",
        nullable=False,
    )  # 'draft', 'active', 'archived'

    # Relationships
    organiser: Mapped["User"] = relationship("User", back_populates="events")
    photos: Mapped[List["Photo"]] = relationship(
        "Photo",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    faces: Mapped[List["PhotoFace"]] = relationship(
        "PhotoFace",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    access_tokens: Mapped[List["EventAccess"]] = relationship(
        "EventAccess",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    search_sessions: Mapped[List["SearchSession"]] = relationship(
        "SearchSession",
        back_populates="event",
        cascade="all, delete-orphan",
    )

