import uuid
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_async_db,
    get_optional_user,
    rate_limit_search,
)
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.search import (
    ConsentCreate,
    FaceSearchResponse,
    SearchSessionRead,
)
from app.services.search_service import SearchService

router = APIRouter(prefix="/events/{event_id}/search", tags=["Face Search"])


@router.post(
    "/consent",
    response_model=APIResponse[SearchSessionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Record attendee consent and initialize face search session",
)
async def create_search_consent(
    event_id: str,
    consent_in: ConsentCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    ip_addr = request.client.host if request.client else None
    session = await SearchService.create_session_with_consent(
        db=db,
        event_id=event_id,
        consent_in=consent_in,
        current_user=current_user,
        ip_address=ip_addr,
    )
    return APIResponse(
        success=True,
        message="Consent recorded and search session initialized",
        data=SearchSessionRead(
            session_id=session.id,
            event_id=session.event_id,
            consent_timestamp=session.consent_timestamp,
            consent_purpose=session.consent_purpose,
            status=session.status,
            expires_at=session.expires_at,
        ),
    )


@router.post(
    "",
    response_model=APIResponse[FaceSearchResponse],
    summary="Upload selfie, index face, and retrieve authorized matching photographs (similarity >= 50%)",
    dependencies=[Depends(rate_limit_search)],
)
async def search_by_selfie(
    event_id: str,
    request: Request,
    selfie: UploadFile = File(..., description="Attendee selfie photo (JPEG, PNG, WebP)"),
    session_id: uuid.UUID = Form(..., description="Active search session ID from consent endpoint"),
    threshold: Optional[float] = Form(None, description="Optional override for cosine similarity threshold (default 0.50 / 50%)"),
    include_public: bool = Form(False, description="Whether to include unmatched public event photos (default False)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    ip_addr = request.client.host if request.client else None
    results = await SearchService.search_faces_for_attendee(
        db=db,
        event_id=event_id,
        session_id=session_id,
        selfie_file=selfie,
        threshold=threshold,
        include_public=include_public,
        current_user=current_user,
        ip_address=ip_addr,
    )
    if results.public_count > 0:
        msg = f"Found {results.matched_count} matching photo(s) and {results.public_count} public photo(s)"
    else:
        msg = f"Found {results.matched_count} matching photo(s)"

    return APIResponse(
        success=True,
        message=msg,
        data=results,
    )


@router.get(
    "/{session_id}",
    response_model=APIResponse[SearchSessionRead],
    summary="Get status and details of an active search session",
)
async def get_search_session(
    event_id: str,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
):
    session = await SearchService.get_valid_session(db, event_id, session_id)
    return APIResponse(
        success=True,
        message="Search session is active",
        data=SearchSessionRead(
            session_id=session.id,
            event_id=session.event_id,
            consent_timestamp=session.consent_timestamp,
            consent_purpose=session.consent_purpose,
            status=session.status,
            expires_at=session.expires_at,
        ),
    )


@router.delete(
    "/{session_id}",
    response_model=APIResponse[None],
    summary="Revoke consent and expire search session immediately",
)
async def revoke_search_session(
    event_id: str,
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    ip_addr = request.client.host if request.client else None
    await SearchService.revoke_session(db, event_id, session_id, current_user, ip_addr)
    return APIResponse(
        success=True,
        message="Search session revoked and biometric processing consent withdrawn",
        data=None,
    )

