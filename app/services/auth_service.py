import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.token import TokenResponse
from app.schemas.user import UserCreate
from app.config import settings


class AuthService:
    @staticmethod
    async def register(db: AsyncSession, user_in: UserCreate) -> User:
        """Register a new user account with hashed password."""
        existing = await db.execute(select(User).where(User.email == user_in.email.lower()))
        if existing.scalar_one_or_none():
            raise ConflictError("A user with this email address already exists")

        user = User(
            id=uuid.uuid4(),
            email=user_in.email.lower(),
            full_name=user_in.full_name.strip(),
            password_hash=hash_password(user_in.password),
            role=user_in.role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> TokenResponse:
        """Verify user credentials and return new access & refresh tokens."""
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("User account is disabled")

        access_token = create_access_token(subject=str(user.id), role=user.role)
        refresh_token = create_refresh_token(subject=str(user.id))

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token_str: str) -> TokenResponse:
        """Rotate refresh token and issue new token pair."""
        try:
            payload = decode_token(refresh_token_str)
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid refresh token")
            user_id = uuid.UUID(payload["sub"])
        except Exception:
            raise AuthenticationError("Invalid or expired refresh token")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise AuthenticationError("User account is not valid")

        new_access = create_access_token(subject=str(user.id), role=user.role)
        new_refresh = create_refresh_token(subject=str(user.id))

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

