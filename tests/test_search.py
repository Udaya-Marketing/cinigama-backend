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


@pytest.mark.asyncio
async def test_search_matches_only_equal_or_above_50_percent(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
):
    from unittest.mock import patch
    from app.services.face_service import DetectedFace

    # 1. Initialize consent session
    consent_res = await client.post(
        f"/api/v1/events/{test_event.id}/search/consent",
        json={"consent_given": True},
    )
    assert consent_res.status_code == 201
    session_id = consent_res.json()["data"]["session_id"]

    # 2. Base reference unit vector for the selfie
    selfie_vec = np.zeros(128, dtype=np.float32)
    selfie_vec[0] = 1.0

    def make_vector_with_similarity(s: float) -> list[float]:
        v = np.zeros(128, dtype=np.float32)
        v[0] = s
        v[1] = np.sqrt(max(0.0, 1.0 - s * s))
        v = v / np.linalg.norm(v)
        return v.tolist()

    # Photo 1: High match (similarity = 0.85, >= 0.50) -> MUST MATCH
    p1 = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="high_match.jpg",
        storage_path="/tmp/p1.jpg",
        thumbnail_path="/tmp/p1_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=False,
        processing_status="completed",
    )
    f1 = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=p1.id,
        embedding=make_vector_with_similarity(0.85),
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.98,
    )

    # Photo 2: Exactly 50% match (similarity = 0.50, >= 0.50) -> MUST MATCH (equal or above 50%)
    p2 = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="boundary_50_match.jpg",
        storage_path="/tmp/p2.jpg",
        thumbnail_path="/tmp/p2_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=False,
        processing_status="completed",
    )
    f2 = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=p2.id,
        embedding=make_vector_with_similarity(0.50),
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.95,
    )

    # Photo 3: Low match (similarity = 0.45, < 0.50) -> MUST NOT MATCH
    p3 = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="low_match_45.jpg",
        storage_path="/tmp/p3.jpg",
        thumbnail_path="/tmp/p3_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=False,
        processing_status="completed",
    )
    f3 = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=p3.id,
        embedding=make_vector_with_similarity(0.45),
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.90,
    )

    # Photo 4: Previous default threshold match (similarity = 0.38, < 0.50) -> MUST NOT MATCH
    p4 = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="old_threshold_38.jpg",
        storage_path="/tmp/p4.jpg",
        thumbnail_path="/tmp/p4_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=False,
        processing_status="completed",
    )
    f4 = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=p4.id,
        embedding=make_vector_with_similarity(0.38),
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.88,
    )

    # Photo 5: Public photo without matching face -> MUST NOT be in search results by default
    p5 = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="public_stage_unmatched.jpg",
        storage_path="/tmp/p5.jpg",
        thumbnail_path="/tmp/p5_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=True,
        processing_status="completed",
    )
    f5 = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=p5.id,
        embedding=make_vector_with_similarity(0.10),
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.90,
    )

    db_session.add_all([p1, p2, p3, p4, p5, f1, f2, f3, f4, f5])
    await db_session.commit()

    # 3. Perform search with mocked selfie returning selfie_vec
    mock_detected_face = DetectedFace(
        bounding_box={"x": 10, "y": 10, "w": 60, "h": 60},
        confidence=0.99,
        landmarks={},
        embedding=selfie_vec.tolist(),
    )

    with patch.object(FaceRecognitionEngine, "process_selfie", return_value=mock_detected_face):
        search_res = await client.post(
            f"/api/v1/events/{test_event.id}/search",
            files={"selfie": ("selfie.jpg", b"fake_bytes", "image/jpeg")},
            data={"session_id": str(session_id)},
        )

    assert search_res.status_code == 200
    data = search_res.json()["data"]
    items = data["items"]

    # Verify matched count is exactly 2 (p1 with 0.85 and p2 with 0.50)
    assert data["matched_count"] == 2
    assert data["public_count"] == 0
    assert data["total_returned"] == 2

    returned_photo_ids = [item["photo"]["id"] for item in items]
    assert str(p1.id) in returned_photo_ids
    assert str(p2.id) in returned_photo_ids
    assert str(p3.id) not in returned_photo_ids  # 45% similarity must be excluded
    assert str(p4.id) not in returned_photo_ids  # 38% similarity must be excluded
    assert str(p5.id) not in returned_photo_ids  # Unmatched public photo must be excluded

    # Verify similarity scores are >= 0.50
    for item in items:
        assert item["similarity_score"] >= 0.50
        assert item["match_type"] == "face_match"

    # 4. Perform search with include_public=True to ensure unmatched public photos are included only if requested
    with patch.object(FaceRecognitionEngine, "process_selfie", return_value=mock_detected_face):
        search_pub_res = await client.post(
            f"/api/v1/events/{test_event.id}/search",
            files={"selfie": ("selfie.jpg", b"fake_bytes", "image/jpeg")},
            data={"session_id": str(session_id), "include_public": "true"},
        )

    assert search_pub_res.status_code == 200
    pub_data = search_pub_res.json()["data"]
    assert pub_data["matched_count"] == 2
    assert pub_data["public_count"] == 1
    assert pub_data["total_returned"] == 3
    pub_ids = [item["photo"]["id"] for item in pub_data["items"]]
    assert str(p5.id) in pub_ids

