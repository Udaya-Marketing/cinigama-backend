import uuid
from typing import TYPE_CHECKING, List
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.photo import Photo


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50),
        default="organiser",
        nullable=False,
    )  # 'admin', 'organiser', 'attendee'
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    events: Mapped[List["Event"]] = relationship(
        "Event",
        back_populates="organiser",
        cascade="all, delete-orphan",
    )
    uploaded_photos: Mapped[List["Photo"]] = relationship(
        "Photo",
        back_populates="uploader",
    )

