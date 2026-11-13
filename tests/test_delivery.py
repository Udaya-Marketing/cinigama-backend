import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.services.storage_service import storage_service


@pytest.mark.asyncio
async def test_delivery_public_photo(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
    sample_image_bytes: bytes,
):
    # Save a real file to test storage
    photo_id = uuid.uuid4()
    orig_path = storage_service.save_original_photo(
        event_id=test_event.id,
        photo_id=photo_id,
        file_bytes=sample_image_bytes,
        ext=".jpg",
    )
    thumb_path = storage_service.generate_thumbnail(
        event_id=test_event.id,
        photo_id=photo_id,
        original_path=orig_path,
    )

    photo = Photo(
        id=photo_id,
        event_id=test_event.id,
        original_filename="public_test.jpg",
        storage_path=str(orig_path),
        thumbnail_path=str(thumb_path),
        mime_type="image/jpeg",
        file_size=len(sample_image_bytes),
        is_public=True,
        processing_status="completed",
    )
    db_session.add(photo)
    await db_session.commit()

    # Public thumbnail request (no auth)
    thumb_res = await client.get(f"/api/v1/events/{test_event.id}/photos/{photo.id}/thumbnail")
    assert thumb_res.status_code == 200
    assert thumb_res.headers["content-type"] in ("image/webp", "image/jpeg")

    # Public view request (no auth)
    view_res = await client.get(f"/api/v1/events/{test_event.id}/photos/{photo.id}/view")
    assert view_res.status_code == 200

    # Public download request (no auth)
    dl_res = await client.get(f"/api/v1/events/{test_event.id}/photos/{photo.id}/download")
    assert dl_res.status_code == 200
    assert "attachment" in dl_res.headers["content-disposition"]


@pytest.mark.asyncio
async def test_delivery_private_photo_access_control(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
):
    photo_id = uuid.uuid4()
    orig_path = storage_service.save_original_photo(
        event_id=test_event.id,
        photo_id=photo_id,
        file_bytes=sample_image_bytes,
        ext=".jpg",
    )

    photo = Photo(
        id=photo_id,
        event_id=test_event.id,
        original_filename="private_test.jpg",
        storage_path=str(orig_path),
        thumbnail_path=None,
        mime_type="image/jpeg",
        file_size=len(sample_image_bytes),
        is_public=False,  # Private!
        processing_status="completed",
    )
    db_session.add(photo)
    await db_session.commit()

    # 1. Anonymous request without session fails with 403
    unauth_res = await client.get(f"/api/v1/events/{test_event.id}/photos/{photo.id}/view")
    assert unauth_res.status_code == 403

    # 2. Organiser request succeeds
    org_res = await client.get(
        f"/api/v1/events/{test_event.id}/photos/{photo.id}/view",
        headers=organiser_headers,
    )
    assert org_res.status_code == 200

    # 3. Request with valid attendee search session succeeds
    consent_res = await client.post(
        f"/api/v1/events/{test_event.id}/search/consent",
        json={"consent_given": True},
    )
    session_id = consent_res.json()["data"]["session_id"]

    session_view_res = await client.get(
        f"/api/v1/events/{test_event.id}/photos/{photo.id}/view?session_id={session_id}"
    )
    assert session_view_res.status_code == 200

