import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user_success(client: AsyncClient):
    payload = {
        "email": "newuser@example.com",
        "full_name": "New User",
        "password": "Password123!",
        "role": "organiser",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newuser@example.com"
    assert data["data"]["role"] == "organiser"
    assert "password_hash" not in data["data"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "full_name": "First User",
        "password": "Password123!",
        "role": "attendee",
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "RESOURCE_CONFLICT"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    # Register user
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login@test.com", "full_name": "Login User", "password": "SecretPassword1!"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@test.com", "password": "SecretPassword1!"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "badpass@test.com", "full_name": "Test", "password": "SecretPassword1!"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "badpass@test.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@test.com", "full_name": "Refresh User", "password": "SecretPassword1!"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@test.com", "password": "SecretPassword1!"},
    )
    refresh_token = login.json()["data"]["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()["data"]


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, organiser_headers: dict):
    response = await client.get("/api/v1/auth/me", headers=organiser_headers)
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "organiser@test.com"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

