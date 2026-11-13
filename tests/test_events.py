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
async def test_delete_event(client: AsyncClient, test_event, organiser_headers: dict):
    response = await client.delete(
        f"/api/v1/events/{test_event.id}",
        headers=organiser_headers,
    )
    assert response.status_code == 200

    # Ensure it's gone
    get_res = await client.get(f"/api/v1/events/{test_event.id}")
    assert get_res.status_code == 404

