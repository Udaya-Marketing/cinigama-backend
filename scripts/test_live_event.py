"""
End-to-End Live Integration Test for 'Test Event -1'.
Exercises all API endpoints, background worker, face detection, indexing,
pgvector search, thumbnail delivery, and privacy controls against the live running stack.
"""

import os
import sys
import time
from pathlib import Path
import requests

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001/api/v1")
PHOTOS_DIR = Path("Test Event -1")


def print_step(title: str):
    print(f"\n{'='*70}\n {title}\n{'='*70}")


def run_live_test():
    session = requests.Session()

    # Step 1: Health Check
    print_step("Step 1: Checking System Health")
    health_res = session.get(f"{BASE_URL}/health")
    assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
    health_data = health_res.json()
    print("Health Status:", health_data.get("status"))
    print("Models Ready:", health_data.get("models_ready"))
    print("Disk Storage:", health_data.get("disk_storage"))
    assert health_data.get("models_ready") is True, "AI Models are not ready!"

    # Step 2: Authentication
    print_step("Step 2: Authenticating Organiser")
    auth_email = "organiser_test1@eventphotography.com"
    auth_password = "SecurePassword123!"

    # Attempt login or register
    login_res = session.post(
        f"{BASE_URL}/auth/login",
        json={"email": auth_email, "password": auth_password},
    )
    if login_res.status_code != 200:
        print("Registering new organiser account...")
        reg_res = session.post(
            f"{BASE_URL}/auth/register",
            json={
                "full_name": "Event Organiser One",
                "email": auth_email,
                "password": auth_password,
                "role": "organiser",
            },
        )
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        login_res = session.post(
            f"{BASE_URL}/auth/login",
            json={"email": auth_email, "password": auth_password},
        )

    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    tokens = login_res.json()["data"]
    access_token = tokens["access_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    print("Authenticated successfully. Access token received.")

    # Step 3: Create 'Test Event -1'
    print_step("Step 3: Creating 'Test Event -1'")
    event_payload = {
        "name": "Test Event -1",
        "description": "Live integration test event using real attendee photographs",
        "access_type": "public",
    }
    event_res = session.post(f"{BASE_URL}/events", json=event_payload, headers=auth_headers)
    assert event_res.status_code == 201, f"Failed to create event: {event_res.text}"
    event = event_res.json()["data"]
    event_id = event["id"]
    print(f"Event Created! ID: {event_id} | Name: {event['name']} | Slug: {event['slug']}")

    # Step 4: Upload all pictures from 'Test Event -1'
    print_step("Step 4: Uploading Photographs from 'Test Event -1'")
    photo_files = sorted(list(PHOTOS_DIR.glob("*.jpeg")))
    print(f"Found {len(photo_files)} photographs in {PHOTOS_DIR}")

    # 4a: Single photo upload (images (1).jpeg as public)
    first_photo = photo_files[0]
    with open(first_photo, "rb") as f:
        upload_single_res = session.post(
            f"{BASE_URL}/events/{event_id}/photos",
            files={"file": (first_photo.name, f, "image/jpeg")},
            data={"is_public": "true"},
            headers=auth_headers,
        )
    assert upload_single_res.status_code == 201, f"Single photo upload failed: {upload_single_res.text}"
    single_photo_id = upload_single_res.json()["data"]["id"]
    print(f"Uploaded single photo: {first_photo.name} -> ID: {single_photo_id} (public=True)")

    # 4b: Bulk upload remaining photos
    remaining_files = photo_files[1:]
    files_payload = []
    file_handles = []
    for p in remaining_files:
        fh = open(p, "rb")
        file_handles.append(fh)
        files_payload.append(("files", (p.name, fh, "image/jpeg")))

    try:
        bulk_res = session.post(
            f"{BASE_URL}/events/{event_id}/photos/bulk",
            files=files_payload,
            data={"is_public": "false"},  # upload remainder as private
            headers=auth_headers,
        )
        assert bulk_res.status_code == 201, f"Bulk upload failed: {bulk_res.text}"
        bulk_data = bulk_res.json()["data"]
        print(f"Bulk upload complete: {bulk_data['successful']} succeeded, {bulk_data['failed']} failed.")
    finally:
        for fh in file_handles:
            fh.close()

    # Step 5: Monitor Background Worker Processing
    print_step("Step 5: Waiting for Background Worker to Index Faces & Generate Thumbnails")
    start_time = time.time()
    max_wait_seconds = 60
    while time.time() - start_time < max_wait_seconds:
        status_res = session.get(f"{BASE_URL}/events/{event_id}/photos/processing-status", headers=auth_headers)
        assert status_res.status_code == 200, f"Status check failed: {status_res.text}"
        st = status_res.json()["data"]
        print(f"  Pending: {st['pending']} | Processing: {st['processing']} | Completed: {st['completed']} | Failed: {st['failed']}")
        if st["completed"] == len(photo_files):
            print(f"All {len(photo_files)} photos processed in {time.time() - start_time:.2f} seconds!")
            break
        time.sleep(1.0)
    else:
        raise TimeoutError("Timed out waiting for background worker to process photos!")

    # Step 6: Verify Event Statistics
    print_step("Step 6: Verifying Event Statistics")
    stats_res = session.get(f"{BASE_URL}/events/{event_id}/stats", headers=auth_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()["data"]
    print("Total Photos:", stats["total_photos"])
    print("Completed Photos:", stats["completed_photos"])
    print("Public Photos:", stats["public_photos"])
    print("Private Photos:", stats["private_photos"])
    print("Total Faces Indexed:", stats["total_faces_indexed"])
    assert stats["total_photos"] == len(photo_files), f"Expected {len(photo_files)} photos, got {stats['total_photos']}"
    assert stats["total_faces_indexed"] == 16, f"Expected 16 faces indexed, got {stats['total_faces_indexed']}"

    # Step 7: Verify Image Delivery (Thumbnail & Full View)
    print_step("Step 7: Testing Secure Image Delivery via Cloudflare R2 Presigned URLs")
    # Public photo thumbnail redirect test
    redirect_res = session.get(
        f"{BASE_URL}/events/{event_id}/photos/{single_photo_id}/thumbnail",
        allow_redirects=False,
    )
    if redirect_res.status_code == 307:
        presigned_url = redirect_res.headers.get("Location")
        print(f"Verified 307 Redirect to Cloudflare R2 Presigned URL:\n  {presigned_url[:90]}...")
        assert "r2.cloudflarestorage.com" in presigned_url or "cinigama-storage" in presigned_url

    # Public photo thumbnail content test (following redirect)
    thumb_res = session.get(f"{BASE_URL}/events/{event_id}/photos/{single_photo_id}/thumbnail")
    assert thumb_res.status_code == 200, f"Thumbnail fetch failed: {thumb_res.status_code}"
    print(f"Public thumbnail retrieved: {len(thumb_res.content)} bytes (Content-Type: {thumb_res.headers.get('content-type')})")

    # Step 8: Attendee Consent & Facial Recognition Search
    print_step("Step 8: Attendee DPDP Act Biometric Consent & Face Search")
    # 8a: Create consent session
    consent_res = session.post(
        f"{BASE_URL}/events/{event_id}/search/consent",
        json={"consent_given": True, "purpose": "facial_recognition_search"},
    )
    assert consent_res.status_code == 201, f"Consent failed: {consent_res.text}"
    session_id = consent_res.json()["data"]["session_id"]
    print(f"Biometric Consent Granted! Session ID: {session_id}")

    # 8b: Search using single-face image 'images (6).jpeg'
    selfie_path = PHOTOS_DIR / "images (6).jpeg"
    print(f"Uploading selfie: {selfie_path.name}...")
    with open(selfie_path, "rb") as f:
        search_res = session.post(
            f"{BASE_URL}/events/{event_id}/search",
            files={"selfie": (selfie_path.name, f, "image/jpeg")},
            data={"session_id": session_id},
        )
    assert search_res.status_code == 200, f"Search failed: {search_res.text}"
    search_data = search_res.json()["data"]
    print(f"Face Search Succeeded!")
    print(f"  Faces Detected in Selfie : {search_data['faces_detected_in_selfie']}")
    print(f"  Face Matches Found       : {search_data['matched_count']}")
    print(f"  Public Photos Included   : {search_data['public_count']}")
    print(f"  Total Photos Returned    : {search_data['total_returned']}")

    print("\nReturned Photograph Details:")
    for item in search_data["items"]:
        p = item["photo"]
        mtype = item["match_type"]
        score = item["similarity_score"]
        conf = item["detection_confidence"]
        print(f"  - [{mtype:<10}] {p['original_filename']} (ID: {p['id']}) | similarity: {score} | conf: {conf}")

    # Step 9: Validate Negative Edge Cases (Zero Faces and Multi-Faces)
    print_step("Step 9: Testing Facial Recognition Validation & Safeguards")
    # 9a: Zero faces rejection test ('images (2).jpeg' has 0 faces)
    zero_face_img = PHOTOS_DIR / "images (2).jpeg"
    with open(zero_face_img, "rb") as f:
        res_zero = session.post(
            f"{BASE_URL}/events/{event_id}/search",
            files={"selfie": (zero_face_img.name, f, "image/jpeg")},
            data={"session_id": session_id},
        )
    assert res_zero.status_code == 422, f"Expected 422 for 0 faces, got {res_zero.status_code}"
    print(f"Zero-face image correctly rejected: {res_zero.json()['error']['message']}")

    # 9b: Multi-face rejection test ('health.jpeg' has 4 faces)
    multi_face_img = PHOTOS_DIR / "health.jpeg"
    with open(multi_face_img, "rb") as f:
        res_multi = session.post(
            f"{BASE_URL}/events/{event_id}/search",
            files={"selfie": (multi_face_img.name, f, "image/jpeg")},
            data={"session_id": session_id},
        )
    assert res_multi.status_code == 422, f"Expected 422 for multi-face image, got {res_multi.status_code}"
    print(f"Multi-face image correctly rejected: {res_multi.json()['error']['message']}")

    # 9c: Revoke consent session (Right to withdraw)
    revoke_res = session.delete(f"{BASE_URL}/events/{event_id}/search/{session_id}")
    assert revoke_res.status_code == 200
    print("Consent revoked successfully.")

    # 9d: Re-trying search with revoked session must fail
    with open(selfie_path, "rb") as f:
        res_revoked = session.post(
            f"{BASE_URL}/events/{event_id}/search",
            files={"selfie": (selfie_path.name, f, "image/jpeg")},
            data={"session_id": session_id},
        )
    assert res_revoked.status_code == 403, f"Expected 403 on revoked session, got {res_revoked.status_code}"
    print("Revoked session access correctly rejected with 403.")

    print_step("ALL LIVE TESTS ON 'Test Event -1' PASSED WITH 100% SUCCESS!")


if __name__ == "__main__":
    try:
        run_live_test()
    except Exception as e:
        print(f"\nERROR: Test execution failed: {e}")
        sys.exit(1)

