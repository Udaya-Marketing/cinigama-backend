import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_single_photo(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
):
    files = {"file": ("event_stage.jpg", sample_image_bytes, "image/jpeg")}
    data = {"is_public": "true"}

    response = await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files=files,
        data=data,
        headers=organiser_headers,
    )
    assert response.status_code == 201
    photo = response.json()["data"]
    assert photo["event_id"] == str(test_event.id)
    assert photo["original_filename"] == "event_stage.jpg"
    assert photo["is_public"] is True
    assert photo["processing_status"] == "pending"


@pytest.mark.asyncio
async def test_upload_invalid_image_rejected(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
):
    bad_bytes = b"This is a text file masquerading as a JPEG image"
    files = {"file": ("malicious.jpg", bad_bytes, "image/jpeg")}

    response = await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files=files,
        headers=organiser_headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IMAGE"


@pytest.mark.asyncio
async def test_bulk_upload_photos(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
    sample_png_bytes: bytes,
):
    files = [
        ("files", ("photo1.jpg", sample_image_bytes, "image/jpeg")),
        ("files", ("photo2.png", sample_png_bytes, "image/png")),
    ]
    response = await client.post(
        f"/api/v1/events/{test_event.id}/photos/bulk",
        files=files,
        data={"is_public": "false"},
        headers=organiser_headers,
    )
    assert response.status_code == 201
    result = response.json()["data"]
    assert result["total_uploaded"] == 2
    assert result["successful"] == 2
    assert result["failed"] == 0
    assert len(result["photos"]) == 2


@pytest.mark.asyncio
async def test_list_photos_and_status(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
):
    # Upload one photo
    await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("list_test.jpg", sample_image_bytes, "image/jpeg")},
        data={"is_public": "true"},
        headers=organiser_headers,
    )

    # List photos
    list_res = await client.get(
        f"/api/v1/events/{test_event.id}/photos",
        headers=organiser_headers,
    )
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # Check processing status
    status_res = await client.get(
        f"/api/v1/events/{test_event.id}/photos/processing-status",
        headers=organiser_headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["data"]["total"] >= 1


@pytest.mark.asyncio
async def test_update_and_delete_photo(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
):
    upload_res = await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("photo_to_delete.jpg", sample_image_bytes, "image/jpeg")},
        data={"is_public": "false"},
        headers=organiser_headers,
    )
    photo_id = upload_res.json()["data"]["id"]

    # Toggle to public
    patch_res = await client.patch(
        f"/api/v1/events/{test_event.id}/photos/{photo_id}",
        json={"is_public": True},
        headers=organiser_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["is_public"] is True

    # Delete photo
    del_res = await client.delete(
        f"/api/v1/events/{test_event.id}/photos/{photo_id}",
        headers=organiser_headers,
    )
    assert del_res.status_code == 200

    # Ensure deleted
    get_res = await client.get(
        f"/api/v1/events/{test_event.id}/photos/{photo_id}",
        headers=organiser_headers,
    )
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_batch_update_and_batch_delete_photos(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
    sample_png_bytes: bytes,
):
    # Upload 2 photos
    res1 = await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("batch1.jpg", sample_image_bytes, "image/jpeg")},
        data={"is_public": "false"},
        headers=organiser_headers,
    )
    p1_id = res1.json()["data"]["id"]

    res2 = await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("batch2.png", sample_png_bytes, "image/png")},
        data={"is_public": "false"},
        headers=organiser_headers,
    )
    p2_id = res2.json()["data"]["id"]

    # 1. Batch update visibility to public
    batch_up = await client.post(
        f"/api/v1/events/{test_event.id}/photos/batch-update",
        json={"photo_ids": [p1_id, p2_id], "is_public": True},
        headers=organiser_headers,
    )
    assert batch_up.status_code == 200
    assert batch_up.json()["data"]["affected"] == 2

    # Verify both are now public
    check1 = await client.get(f"/api/v1/events/{test_event.id}/photos/{p1_id}", headers=organiser_headers)
    check2 = await client.get(f"/api/v1/events/{test_event.id}/photos/{p2_id}", headers=organiser_headers)
    assert check1.json()["data"]["is_public"] is True
    assert check2.json()["data"]["is_public"] is True

    # 2. Batch delete both photos
    batch_del = await client.post(
        f"/api/v1/events/{test_event.id}/photos/batch-delete",
        json={"photo_ids": [p1_id, p2_id]},
        headers=organiser_headers,
    )
    assert batch_del.status_code == 200
    assert batch_del.json()["data"]["affected"] == 2

    # Verify both are gone
    gone1 = await client.get(f"/api/v1/events/{test_event.id}/photos/{p1_id}", headers=organiser_headers)
    assert gone1.status_code == 404


@pytest.mark.asyncio
async def test_view_and_manage_all_photos_with_pagination(
    client: AsyncClient,
    test_event,
    organiser_headers: dict,
    sample_image_bytes: bytes,
    sample_png_bytes: bytes,
):
    # Upload 3 photos with distinct names and visibilities
    await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("alpha_landscape.jpg", sample_image_bytes, "image/jpeg")},
        data={"is_public": "true"},
        headers=organiser_headers,
    )
    await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("beta_portrait.png", sample_png_bytes, "image/png")},
        data={"is_public": "false"},
        headers=organiser_headers,
    )
    await client.post(
        f"/api/v1/events/{test_event.id}/photos",
        files={"file": ("gamma_event.jpg", sample_image_bytes, "image/jpeg")},
        data={"is_public": "true"},
        headers=organiser_headers,
    )

    # 1. View all photos with pagination (page=1, page_size=2)
    res_p1 = await client.get(
        "/api/v1/photos?page=1&page_size=2",
        headers=organiser_headers,
    )
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert p1_data["page"] == 1
    assert p1_data["page_size"] == 2
    assert p1_data["total"] >= 3
    assert len(p1_data["items"]) == 2
    assert p1_data["has_next"] is True

    # 2. Page 2
    res_p2 = await client.get(
        "/api/v1/photos?page=2&page_size=2",
        headers=organiser_headers,
    )
    assert res_p2.status_code == 200
    p2_data = res_p2.json()
    assert p2_data["page"] == 2
    assert len(p2_data["items"]) >= 1

    # 3. Filter by search query (e.g. "landscape")
    res_search = await client.get(
        "/api/v1/photos?search=landscape",
        headers=organiser_headers,
    )
    assert res_search.status_code == 200
    search_items = res_search.json()["items"]
    assert len(search_items) == 1
    assert search_items[0]["original_filename"] == "alpha_landscape.jpg"

    # 4. Filter by is_public=false
    res_priv = await client.get(
        "/api/v1/photos?is_public=false",
        headers=organiser_headers,
    )
    assert res_priv.status_code == 200
    for p in res_priv.json()["items"]:
        assert p["is_public"] is False

    # 5. Direct photo management: PATCH visibility by ID
    target_photo = search_items[0]
    photo_id = target_photo["id"]
    patch_res = await client.patch(
        f"/api/v1/photos/{photo_id}",
        json={"is_public": False},
        headers=organiser_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["is_public"] is False

    # 6. Direct photo management: DELETE by ID
    del_res = await client.delete(
        f"/api/v1/photos/{photo_id}",
        headers=organiser_headers,
    )
    assert del_res.status_code == 200

    # 7. Verify photo deleted
    get_res = await client.get(f"/api/v1/photos/{photo_id}", headers=organiser_headers)
    assert get_res.status_code == 404


