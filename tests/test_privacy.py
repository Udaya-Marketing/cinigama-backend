import datetime
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face import PhotoFace
from app.models.photo import Photo
from app.models.search import SearchSession
from app.services.search_service import SearchService


@pytest.mark.asyncio
async def test_biometric_data_deletion_on_event_delete(
    db_session: AsyncSession,
    test_event,
):
    # Add a photo and face record
    photo = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="cascade_test.jpg",
        storage_path="/tmp/test.jpg",
        mime_type="image/jpeg",
        file_size=100,
        processing_status="completed",
    )
    db_session.add(photo)

    face = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=photo.id,
        embedding=[0.1] * 128,
        bounding_box={"x": 0, "y": 0, "w": 50, "h": 50},
        detection_confidence=0.9,
    )
    db_session.add(face)
    await db_session.commit()

    # Delete event
    await db_session.delete(test_event)
    await db_session.commit()

    # Verify photo and face are cascaded and deleted
    photos_remain = (await db_session.execute(select(Photo).where(Photo.event_id == test_event.id))).scalars().all()
    faces_remain = (await db_session.execute(select(PhotoFace).where(PhotoFace.event_id == test_event.id))).scalars().all()

    assert len(photos_remain) == 0
    assert len(faces_remain) == 0


@pytest.mark.asyncio
async def test_search_session_expiration_validation(
    db_session: AsyncSession,
    test_event,
):
    # Create an already-expired session
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_session = SearchSession(
        id=uuid.uuid4(),
        event_id=test_event.id,
        consent_timestamp=now - datetime.timedelta(hours=2),
        consent_purpose="facial_recognition_search",
        status="active",
        expires_at=now - datetime.timedelta(hours=1),
    )
    db_session.add(expired_session)
    await db_session.commit()

    # Validating should detect expiration and raise PermissionDeniedError
    with pytest.raises(Exception) as exc_info:
        await SearchService.get_valid_session(db_session, test_event.id, expired_session.id)
    assert "expired" in str(exc_info.value).lower()

