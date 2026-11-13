import asyncio
import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_async_db
from app.main import app
from app.models.base import Base
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.storage_service import StorageService, storage_service

# Use temporary directory for test storage
TEST_STORAGE_DIR = Path(tempfile.mkdtemp(prefix="event_photo_test_storage_")).resolve()
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Ensure tests use isolated local storage backend by default
settings.STORAGE_BACKEND = "local"
settings.STORAGE_BASE_DIR = TEST_STORAGE_DIR

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db

    # Point storage service to test storage
    original_storage = storage_service.base_dir
    storage_service.base_dir = TEST_STORAGE_DIR
    storage_service.events_dir = TEST_STORAGE_DIR / "events"
    storage_service.temp_dir = TEST_STORAGE_DIR / "temp"
    storage_service.events_dir.mkdir(parents=True, exist_ok=True)
    storage_service.temp_dir.mkdir(parents=True, exist_ok=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
    storage_service.base_dir = original_storage
    storage_service.events_dir = original_storage / "events"
    storage_service.temp_dir = original_storage / "temp"


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_storage():
    yield
    if TEST_STORAGE_DIR.exists():
        shutil.rmtree(TEST_STORAGE_DIR, ignore_errors=True)


@pytest_asyncio.fixture
async def organiser_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="organiser@test.com",
        full_name="Test Organiser",
        password_hash=hash_password("SecurePass123!"),
        role="organiser",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def organiser_token(organiser_user: User) -> str:
    return create_access_token(subject=str(organiser_user.id), role=organiser_user.role)


@pytest.fixture
def organiser_headers(organiser_token: str) -> dict:
    return {"Authorization": f"Bearer {organiser_token}"}


@pytest_asyncio.fixture
async def attendee_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="attendee@test.com",
        full_name="Test Attendee",
        password_hash=hash_password("SecurePass123!"),
        role="attendee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def attendee_token(attendee_user: User) -> str:
    return create_access_token(subject=str(attendee_user.id), role=attendee_user.role)


@pytest.fixture
def attendee_headers(attendee_token: str) -> dict:
    return {"Authorization": f"Bearer {attendee_token}"}


@pytest_asyncio.fixture
async def test_event(db_session: AsyncSession, organiser_user: User) -> Event:
    event = Event(
        id=uuid.uuid4(),
        organiser_id=organiser_user.id,
        name="Annual Gala 2026",
        description="Official annual photography event",
        slug="annual-gala-2026",
        access_type="public",
        status="active",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Generate a clean JPEG test image."""
    img = Image.new("RGB", (320, 240), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_png_bytes() -> bytes:
    img = Image.new("RGB", (200, 200), color=(250, 120, 80))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
