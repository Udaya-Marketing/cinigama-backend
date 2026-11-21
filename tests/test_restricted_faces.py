import uuid
from unittest.mock import patch
import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face import PhotoFace
from app.models.photo import Photo
from app.models.restricted_face import RestrictedFace
from app.services.face_service import DetectedFace, FaceRecognitionEngine


def make_unit_vector(dimension: int = 128, non_zero_idx: int = 0) -> list[float]:
    v = np.zeros(dimension, dtype=np.float32)
    v[non_zero_idx] = 1.0
    return v.tolist()


def make_vector_with_similarity(base_vec: list[float], s: float) -> list[float]:
    """Return a unit vector with exact cosine similarity s with base_vec (assumed unit along index 0)."""
    v = np.zeros(len(base_vec), dtype=np.float32)
    v[0] = s
    v[1] = np.sqrt(max(0.0, 1.0 - s * s))
    v = v / np.linalg.norm(v)
    return v.tolist()


@pytest.mark.asyncio
async def test_restricted_faces_crud_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
    organiser_headers,
):
    # 1. Mock face detection for upload
    fake_face = DetectedFace(
        bounding_box={"x": 20, "y": 20, "w": 80, "h": 80},
        confidence=0.98,
        landmarks={},
        embedding=make_unit_vector(128, 0),
    )

    with patch.object(FaceRecognitionEngine, "process_selfie", return_value=fake_face):
        res = await client.post(
            f"/api/v1/events/{test_event.id}/restricted-faces",
            headers=organiser_headers,
            files={"photo": ("person_a.jpg", b"fake_image_bytes", "image/jpeg")},
            data={"name": "Restricted Person A", "reason": "Selfie search opted out"},
        )

    assert res.status_code == 201
    data = res.json()["data"]
    rf_id = data["id"]
    assert data["name"] == "Restricted Person A"
    assert data["reason"] == "Selfie search opted out"
    assert data["event_id"] == str(test_event.id)

    # 2. List restricted faces
    list_res = await client.get(
        f"/api/v1/events/{test_event.id}/restricted-faces",
        headers=organiser_headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == rf_id

    # 3. Delete restricted face
    del_res = await client.delete(
        f"/api/v1/events/{test_event.id}/restricted-faces/{rf_id}",
        headers=organiser_headers,
    )
    assert del_res.status_code == 200

    # 4. Verify list is empty
    list_res2 = await client.get(
        f"/api/v1/events/{test_event.id}/restricted-faces",
        headers=organiser_headers,
    )
    assert list_res2.status_code == 200
    assert list_res2.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_restrict_from_existing_photoface(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
    organiser_headers,
):
    # Create photo and PhotoFace in db
    photo = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="stage.jpg",
        storage_path="/tmp/fake.jpg",
        thumbnail_path="/tmp/fake_thumb.webp",
        mime_type="image/jpeg",
        file_size=1024,
        is_public=False,
        processing_status="completed",
    )
    db_session.add(photo)

    face = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=photo.id,
        embedding=make_unit_vector(128, 5),
        bounding_box={"x": 15, "y": 15, "w": 60, "h": 60},
        detection_confidence=0.96,
    )
    db_session.add(face)
    await db_session.commit()

    # Restrict by face ID
    res = await client.post(
        f"/api/v1/events/{test_event.id}/restricted-faces/from-face/{face.id}",
        headers=organiser_headers,
        data={"name": "VIP Guest", "reason": "Privacy policy request"},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["name"] == "VIP Guest"
    assert data["reason"] == "Privacy policy request"


@pytest.mark.asyncio
async def test_restricted_face_cannot_selfie_search_but_can_be_shown_in_others_photos(
    client: AsyncClient,
    db_session: AsyncSession,
    test_event,
):
    """Core Test:
    - Person A is restricted.
    - Person A uploads selfie -> BLOCKED (403 FACE_SEARCH_RESTRICTED).
    - Person B is NOT restricted.
    - Person B uploads selfie -> SUCCEEDS and receives Photo 1 (which includes Person A and Person B)!
    """
    # Vector for Person A (restricted): along dimension 0
    vec_person_a = make_unit_vector(128, 0)
    # Vector for Person B (other attendee): along dimension 1
    vec_person_b = make_unit_vector(128, 1)

    # 1. Add Person A to restricted_faces for this event
    restricted_a = RestrictedFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        name="Person A (Restricted)",
        reason="Blocked from selfie retrieval",
        embedding=vec_person_a,
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        detection_confidence=0.99,
    )
    db_session.add(restricted_a)

    # 2. Add Photo 1 containing BOTH Person A and Person B (e.g. group/duo photo)
    photo_shared = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="group_photo_a_and_b.jpg",
        storage_path="/tmp/shared.jpg",
        thumbnail_path="/tmp/shared_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=False,
        processing_status="completed",
    )
    face_a_in_shared = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=photo_shared.id,
        embedding=vec_person_a,
        bounding_box={"x": 10, "y": 10, "w": 40, "h": 40},
        detection_confidence=0.95,
    )
    face_b_in_shared = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=photo_shared.id,
        embedding=vec_person_b,
        bounding_box={"x": 80, "y": 10, "w": 40, "h": 40},
        detection_confidence=0.95,
    )

    # 3. Add Photo 2 containing Person B alone
    photo_b_only = Photo(
        id=uuid.uuid4(),
        event_id=test_event.id,
        original_filename="solo_b.jpg",
        storage_path="/tmp/b.jpg",
        thumbnail_path="/tmp/b_thumb.webp",
        mime_type="image/jpeg",
        file_size=2048,
        is_public=False,
        processing_status="completed",
    )
    face_b_solo = PhotoFace(
        id=uuid.uuid4(),
        event_id=test_event.id,
        photo_id=photo_b_only.id,
        embedding=vec_person_b,
        bounding_box={"x": 30, "y": 30, "w": 50, "h": 50},
        detection_confidence=0.97,
    )

    db_session.add_all([photo_shared, face_a_in_shared, face_b_in_shared, photo_b_only, face_b_solo])
    await db_session.commit()

    # 4. Initialize consent session for attendee search
    consent_res = await client.post(
        f"/api/v1/events/{test_event.id}/search/consent",
        json={"consent_given": True},
    )
    assert consent_res.status_code == 201
    session_id = consent_res.json()["data"]["session_id"]

    # 5. ATTEMPT 1: Person A (restricted) uploads their selfie to get photos
    selfie_a = DetectedFace(
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        confidence=0.99,
        landmarks={},
        embedding=vec_person_a,
    )
    with patch.object(FaceRecognitionEngine, "process_selfie", return_value=selfie_a):
        res_a = await client.post(
            f"/api/v1/events/{test_event.id}/search",
            files={"selfie": ("selfie_a.jpg", b"fake_bytes_a", "image/jpeg")},
            data={"session_id": session_id},
        )

    # MUST BE FORBIDDEN (403) with FACE_SEARCH_RESTRICTED code
    assert res_a.status_code == 403
    err_json = res_a.json()
    assert "FACE_SEARCH_RESTRICTED" in str(err_json)
    assert "restricted" in str(err_json).lower()

    # 6. ATTEMPT 2: Person B (NOT restricted) uploads their selfie to get photos
    # Initialize a fresh consent session for Person B
    consent_res_b = await client.post(
        f"/api/v1/events/{test_event.id}/search/consent",
        json={"consent_given": True},
    )
    session_id_b = consent_res_b.json()["data"]["session_id"]

    selfie_b = DetectedFace(
        bounding_box={"x": 10, "y": 10, "w": 50, "h": 50},
        confidence=0.99,
        landmarks={},
        embedding=vec_person_b,
    )
    with patch.object(FaceRecognitionEngine, "process_selfie", return_value=selfie_b):
        res_b = await client.post(
            f"/api/v1/events/{test_event.id}/search",
            files={"selfie": ("selfie_b.jpg", b"fake_bytes_b", "image/jpeg")},
            data={"session_id": session_id_b},
        )

    # Person B MUST SUCCEED (200 OK)
    assert res_b.status_code == 200
    data_b = res_b.json()["data"]
    assert data_b["matched_count"] == 2  # Both photo_shared and photo_b_only
    returned_ids = [item["photo"]["id"] for item in data_b["items"]]

    # CRUCIAL CHECK: Photo 1 (which includes Person A!) IS RETURNED to Person B!
    assert str(photo_shared.id) in returned_ids
    assert str(photo_b_only.id) in returned_ids
