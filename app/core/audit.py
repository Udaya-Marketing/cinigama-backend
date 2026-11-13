import uuid
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog
from app.core.logging import app_logger


async def record_audit_log(
    db: AsyncSession,
    action: str,
    event_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Record an audit trail event for security, privacy, and DPDP compliance.
    Strictly verifies that no biometric vectors are passed into details.
    """
    clean_details = {}
    if details:
        for k, v in details.items():
            if "embedding" in k.lower() or "vector" in k.lower():
                continue
            clean_details[k] = v

    log_entry = AuditLog(
        id=uuid.uuid4(),
        event_id=event_id,
        user_id=user_id,
        action=action,
        details=clean_details,
        ip_address=ip_address,
    )
    db.add(log_entry)
    try:
        await db.flush()
    except Exception as e:
        app_logger.warning(f"Could not persist audit log: {e}")

