import datetime
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import JSON, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, GUID


class AuditLog(Base):
    """Audit log for privacy, consent, and security-sensitive events.
    Strict rule: Never store biometric embeddings or raw image binary data in logs!
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


Index("idx_audit_logs_event_action", AuditLog.event_id, AuditLog.action)

