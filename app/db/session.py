import os
from collections.abc import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

is_serverless = bool(
    os.environ.get("VERCEL")
    or os.environ.get("VERCEL_ENV")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
)

# Async Engine and Session for FastAPI
async_db_url = settings.get_database_url()
is_sqlite_async = async_db_url.startswith("sqlite")

async_engine_kwargs = {"echo": settings.DEBUG}
if not is_sqlite_async:
    if is_serverless:
        # Optimized for serverless: smaller pool per instance, aggressive recycling
        async_engine_kwargs.update({
            "pool_size": 2,
            "max_overflow": 3,
            "pool_recycle": 300,
            "pool_pre_ping": True,
        })
    else:
        async_engine_kwargs.update({
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_pre_ping": True,
        })

async_engine = create_async_engine(async_db_url, **async_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Sync Engine and Session for migrations / sync workers / CLI scripts
sync_db_url = settings.get_sync_database_url()
is_sqlite_sync = sync_db_url.startswith("sqlite")

sync_engine_kwargs = {"echo": settings.DEBUG}
if not is_sqlite_sync:
    sync_engine_kwargs.update({
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_pre_ping": True,
    })

sync_engine = create_engine(sync_db_url, **sync_engine_kwargs)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session in FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db() -> Generator[Session, None, None]:
    """Dependency or context helper for sync database session."""
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()

