import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_event_by_organiser(client: AsyncClient, organiser_headers: dict):
    payload = {
        "name": "Summer Tech Summit 2026",
        "description": "Annual tech convention and awards",
        "access_type": "public",
    }
    response = await client.post("/api/v1/events", json=payload, headers=organiser_headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "Summer Tech Summit 2026"
    assert data["slug"] == "summer-tech-summit-2026"
    assert data["access_type"] == "public"


@pytest.mark.asyncio
async def test_create_event_by_attendee_forbidden(client: AsyncClient, attendee_headers: dict):
    payload = {
        "name": "Unauthorized Event",
        "access_type": "public",
    }
    response = await client.post("/api/v1/events", json=payload, headers=attendee_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_events(client: AsyncClient, test_event, organiser_headers: dict):
    response = await client.get("/api/v1/events", headers=organiser_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(e["id"] == str(test_event.id) for e in data["items"])


@pytest.mark.asyncio
async def test_get_event_by_id(client: AsyncClient, test_event):
    response = await client.get(f"/api/v1/events/{test_event.id}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(test_event.id)


@pytest.mark.asyncio
async def test_update_event(client: AsyncClient, test_event, organiser_headers: dict):
    update_payload = {"name": "Updated Gala Name 2026"}
    response = await client.patch(
        f"/api/v1/events/{test_event.id}",
        json=update_payload,
        headers=organiser_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated Gala Name 2026"


@pytest.mark.asyncio
async def test_get_event_stats(client: AsyncClient, test_event, organiser_headers: dict):
    response = await client.get(
        f"/api/v1/events/{test_event.id}/stats",
        headers=organiser_headers,
    )
    assert response.status_code == 200
    stats = response.json()["data"]
    assert stats["total_photos"] == 0
    assert stats["total_faces_indexed"] == 0


@pytest.mark.asyncio
async def test_get_event_details_with_photos(client: AsyncClient, test_event):
    response = await client.get(f"/api/v1/events/{test_event.id}/details?page=1&page_size=10")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    data = res_data["data"]
    assert data["event"]["id"] == str(test_event.id)
    assert "total_photos" in data
    assert "public_photos" in data
    assert "photos" in data
    assert isinstance(data["photos"], list)
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_pages"] >= 1
    assert "has_next" in data
    assert "has_prev" in data


@pytest.mark.asyncio
async def test_delete_event(client: AsyncClient, test_event, organiser_headers: dict):
    response = await client.delete(
        f"/api/v1/events/{test_event.id}",
        headers=organiser_headers,
    )
    assert response.status_code == 200

    # Ensure it's gone
    get_res = await client.get(f"/api/v1/events/{test_event.id}")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_update_event_slug(client: AsyncClient, test_event, organiser_headers: dict):
    # 1. Update slug to a custom string
    response = await client.patch(
        f"/api/v1/events/{test_event.id}",
        json={"slug": "new-custom-slug-52630"},
        headers=organiser_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["slug"] == "new-custom-slug-52630"

    # 2. Verify event can be fetched via new slug
    get_res = await client.get("/api/v1/events/new-custom-slug-52630")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == str(test_event.id)

    # 3. Create another event and ensure updating to duplicate slug fails with 409
    create_second = await client.post(
        "/api/v1/events",
        json={"name": "Second Event", "slug": "second-unique-slug"},
        headers=organiser_headers,
    )
    assert create_second.status_code == 201

    conflict_res = await client.patch(
        f"/api/v1/events/{test_event.id}",
        json={"slug": "second-unique-slug"},
        headers=organiser_headers,
    )
    assert conflict_res.status_code == 409

