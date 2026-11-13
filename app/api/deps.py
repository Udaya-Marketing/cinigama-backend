import time
import uuid
from collections import defaultdict
from typing import AsyncGenerator, Optional
from fastapi import Depends, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError, RateLimitExceededError
from app.core.security import decode_token
from app.db.session import get_async_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


# In-memory sliding window rate limiter for face searches
class SimpleRateLimiter:
    def __init__(self, requests_per_minute: int = 15):
        self.requests_per_minute = requests_per_minute
        self.history = defaultdict(list)

    def check(self, client_ip: str) -> None:
        now = time.time()
        window_start = now - 60.0
        # Purge timestamps older than 60s
        self.history[client_ip] = [ts for ts in self.history[client_ip] if ts > window_start]
        if len(self.history[client_ip]) >= self.requests_per_minute:
            raise RateLimitExceededError()
        self.history[client_ip].append(now)


search_rate_limiter = SimpleRateLimiter(requests_per_minute=settings.RATE_LIMIT_SEARCH_PER_MINUTE)


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """Validate JWT access token and return the authenticated User."""
    if not auth or not auth.credentials:
        raise AuthenticationError("Authorization header with Bearer token is required")

    try:
        payload = decode_token(auth.credentials)
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise AuthenticationError("Subject missing in token")
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise AuthenticationError("Invalid or expired token")

    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise PermissionDeniedError("User account is inactive")

    return user


async def get_optional_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> Optional[User]:
    """Return User if valid Bearer token provided, otherwise None."""
    if not auth or not auth.credentials:
        return None
    try:
        payload = decode_token(auth.credentials)
        if payload.get("type") != "access":
            return None
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user
        return None
    except Exception:
        return None


def require_role(*roles: str):
    """Dependency factory checking user has one of the allowed roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles and current_user.role != "admin":
            raise PermissionDeniedError(f"Access restricted to roles: {', '.join(roles)}")
        return current_user
    return role_checker


require_organiser = require_role("organiser")
require_admin = require_role("admin")


def rate_limit_search(request: Request) -> None:
    """Enforce rate limits per client IP for facial search endpoints."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    search_rate_limiter.check(client_ip)

