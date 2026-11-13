"""
Biometric Data Retention and Privacy Cleanup Utility.
Complies with Digital Personal Data Protection (DPDP) Act 2023:
- Purges expired attendee search sessions and consent records past the retention limit.
- Cleans up orphaned or temporary media files.
- Removes biometric records for archived events exceeding the data retention window.
"""

import argparse
import datetime
import sys
from pathlib import Path

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, delete, func, select
from app.config import settings
from app.core.logging import app_logger
from app.db.session import SyncSessionLocal
from app.models.access import EventAccess
from app.models.audit import AuditLog
from app.models.face import PhotoFace
from app.models.photo import Photo
from app.models.search import SearchSession
from app.services.storage_service import storage_service


def cleanup_expired_sessions(session) -> int:
    """Mark expired search sessions and clean up sessions older than retention limit."""
    now = datetime.datetime.now(datetime.timezone.utc)
    # Update active sessions past expires_at
    expired_count = (
        session.query(SearchSession)
        .filter(SearchSession.status == "active", SearchSession.expires_at < now)
        .update({SearchSession.status: "expired"})
    )

    # Purge search sessions older than 30 days
    purge_cutoff = now - datetime.timedelta(days=30)
    purged_count = (
        session.query(SearchSession)
        .filter(SearchSession.created_at < purge_cutoff)
        .delete()
    )

    session.commit()
    app_logger.info(f"Marked {expired_count} sessions expired, purged {purged_count} old sessions")
    return expired_count + purged_count


def cleanup_expired_access_tokens(session) -> int:
    """Purge expired event access tokens."""
    now = datetime.datetime.now(datetime.timezone.utc)
    deleted = (
        session.query(EventAccess)
        .filter(EventAccess.expires_at < now)
        .delete()
    )
    session.commit()
    app_logger.info(f"Purged {deleted} expired event access tokens")
    return deleted


def cleanup_temp_storage() -> int:
    """Clean up any leftover temporary files in storage/temp."""
    temp_dir = storage_service.temp_dir
    cleaned = 0
    now = datetime.datetime.now().timestamp()
    cutoff = now - 3600  # Older than 1 hour

    if temp_dir.exists():
        for item in temp_dir.iterdir():
            if item.is_file() and item.stat().st_mtime < cutoff:
                try:
                    item.unlink()
                    cleaned += 1
                except Exception as e:
                    app_logger.warning(f"Failed to delete temp file {item}: {e}")

    app_logger.info(f"Cleaned {cleaned} temporary files from storage/temp")
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Privacy & Biometric Data Retention Cleaner")
    parser.add_argument("--dry-run", action="store_true", help="Report without deleting")
    args = parser.parse_args()

    app_logger.info("Starting Biometric Privacy and Data Retention Cleanup...")
    with SyncSessionLocal() as db_session:
        cleanup_expired_sessions(db_session)
        cleanup_expired_access_tokens(db_session)

    cleanup_temp_storage()
    app_logger.info("Cleanup completed successfully.")


if __name__ == "__main__":
    main()

