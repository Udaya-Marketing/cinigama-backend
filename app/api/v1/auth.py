from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_async_db, get_current_user
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.token import TokenRefreshRequest, TokenResponse
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=APIResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_async_db),
):
    user = await AuthService.register(db, user_in)
    return APIResponse(
        success=True,
        message="User registered successfully",
        data=UserRead.model_validate(user),
    )


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    summary="Authenticate and obtain JWT access and refresh tokens",
)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_async_db),
):
    token_resp = await AuthService.authenticate(db, credentials.email, credentials.password)
    return APIResponse(
        success=True,
        message="Authentication successful",
        data=token_resp,
    )


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
    summary="Rotate refresh token and obtain new access token",
)
async def refresh_token(
    refresh_req: TokenRefreshRequest,
    db: AsyncSession = Depends(get_async_db),
):
    token_resp = await AuthService.refresh(db, refresh_req.refresh_token)
    return APIResponse(
        success=True,
        message="Token refreshed successfully",
        data=token_resp,
    )


@router.get(
    "/me",
    response_model=APIResponse[UserRead],
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return APIResponse(
        success=True,
        message="User profile retrieved",
        data=UserRead.model_validate(current_user),
    )


@router.post(
    "/logout",
    response_model=APIResponse[None],
    summary="Log out and invalidate client-side session",
)
async def logout(
    current_user: User = Depends(get_current_user),
):
    # JWT tokens are stateless; client discards token.
    return APIResponse(
        success=True,
        message="Logged out successfully",
        data=None,
    )

