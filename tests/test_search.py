import uuid
import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face import PhotoFace
from app.models.photo import Photo
from app.services.face_service import FaceRecognitionEngine
from scripts.generate_test_data import create_synthetic_face_image


@pytest.mark.asyncio
async def test_search_session_consent_workflow(
    client: AsyncClient,
    test_event,
):
    # 1. Grant consent
    consent_payload = {
        "consent_given": True,
        "purpose": "facial_recognition_search",
    }
    response = await client.post(
        f"/api/v1/events/{test_event.id}/search/consent",
        json=consent_payload,
    )
    assert response.status_code == 201
    session_data = response.json()["data"]
    session_id = session_data["session_id"]
    assert session_data["status"] == "active"
    assert session_data["consent_purpose"] == "facial_recognition_search"

    # 2. Check session status
    get_res = await client.get(f"/api/v1/events/{test_event.id}/search/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["session_id"] == session_id

    # 3. Revoke consent
    rev_res = await client.delete(f"/api/v1/events/{test_event.id}/search/{session_id}")
    assert rev_res.status_code == 200

    # 4. Accessing revoked session should now fail
    get_rev = await client.get(f"/api/v1/events/{test_event.id}/search/{session_id}")
    assert get_rev.status_code == 403


@pytest.mark.asyncio
async def test_search_without_consent_fails(client: AsyncClient, test_event):
    bad_session_id = str(uuid.uuid4())
    img_bytes = create_synthetic_face_image(width=400, height=400, face_count=0)

    response = await client.post(
        f"/api/v1/events/{test_event.id}/search",
        files={"selfie": ("selfie.jpg", img_bytes, "image/jpeg")},
        data={"session_id": bad_session_id},
    )
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_search_raw_embeddings_never_exposed(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
):
    # Create an active consent session
    consent_res = await client.post(
        f"/api/v1/events/{test_event.id}/search/consent",
        json={"consent_given": True},
    )
    session_id = consent_res.json()["data"]["session_id"]

    # Insert a public completed photo in the event
    photo = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="public_stage.jpg",
        storage_path="/tmp/fake.jpg",
        thumbnail_path="/tmp/fake_thumb.webp",
        mime_type="image/jpeg",
        file_size=1024,
        is_public=True,
        processing_status="completed",
    )
    db_session.add(photo)

    # Insert a face embedding
    fake_vec = (np.random.randn(128) / np.linalg.norm(np.random.randn(128))).tolist()
    face = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=photo.id,
        embedding=fake_vec,
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.95,
    )
    db_session.add(face)
    await db_session.commit()

    # Query event photos
    photos_res = await client.get(f"/api/v1/events/{test_event.id}/photos")
    assert photos_res.status_code == 200

    # Ensure response text contains NO raw embedding array or vector
    resp_text = photos_res.text
    assert "embedding" not in resp_text.lower() or '"embedding":' not in resp_text
    assert "vector" not in resp_text.lower()

