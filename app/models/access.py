import datetime
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class EventAccess(Base):
    __tablename__ = "event_access"

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
    attendee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    access_token_hash: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="access_tokens")
    attendee: Mapped[Optional["User"]] = relationship("User")


Index("idx_event_access_event_token", EventAccess.event_id, EventAccess.access_token_hash)

