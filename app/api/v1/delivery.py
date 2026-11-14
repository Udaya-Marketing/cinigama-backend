import os
from pathlib import Path
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, get_optional_user
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.photo import Photo
from app.models.user import User
from app.services.event_service import EventService
from app.services.photo_service import PhotoService
from app.services.search_service import SearchService
from app.services.storage_service import storage_service

router = APIRouter(prefix="/events/{event_id}/photos/{photo_id}", tags=["Image Delivery"])


async def check_image_access(
    db: AsyncSession,
    event_id: str,
    photo_id: uuid.UUID,
    session_id: Optional[uuid.UUID] = None,
    current_user: Optional[User] = None,
) -> Photo:
    """Verify authorization before serving any photograph file."""
    event = await EventService.get_event_by_id(db, event_id)
    canonical_id = event.id
    photo = await PhotoService.get_photo_by_id(db, canonical_id, photo_id)

    # If photo is explicitly marked public and event is active/accessible
    if photo.is_public:
        return photo

    # If requester is the event organiser or admin
    if current_user and (current_user.id == event.organiser_id or current_user.role == "admin"):
        return photo

    # If attendee supplied an active search session ID, verify session validity
    if session_id:
        # Check session is valid and active
        await SearchService.get_valid_session(db, canonical_id, session_id)
        # Attendee has permission to access face-matched private photos
        return photo

    raise PermissionDeniedError(
        "Private photo: Authorisation required. Provide an active search session or organiser credentials."
    )


@router.get(
    "/thumbnail",
    summary="Get optimized WebP thumbnail for a photograph",
)
async def get_thumbnail(
    event_id: str,
    photo_id: uuid.UUID,
    session_id: Optional[uuid.UUID] = Query(None, description="Active search session ID for private photos"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    photo = await check_image_access(db, event_id, photo_id, session_id, current_user)
    target_key = photo.thumbnail_path or photo.storage_path

    # If Cloudflare R2 is enabled, redirect directly to secure presigned URL
    if storage_service.is_r2:
        presigned_url = storage_service.generate_presigned_url(target_key)
        if not presigned_url:
            raise NotFoundError("Thumbnail not found")
        return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Local filesystem delivery
    target_path = Path(target_key)
    if not target_path.exists():
        raise NotFoundError("Thumbnail not yet generated or file not found")

    media_type = "image/webp" if target_path.suffix.lower() == ".webp" else photo.mime_type
    return FileResponse(
        path=target_path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get(
    "/view",
    summary="View full-resolution photograph inline",
)
async def view_photo(
    event_id: str,
    photo_id: uuid.UUID,
    session_id: Optional[uuid.UUID] = Query(None, description="Active search session ID for private photos"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    photo = await check_image_access(db, event_id, photo_id, session_id, current_user)

    if storage_service.is_r2:
        presigned_url = storage_service.generate_presigned_url(photo.storage_path)
        if not presigned_url:
            raise NotFoundError("Photograph not found in R2 storage")
        return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    orig_path = Path(photo.storage_path)
    if not orig_path.exists():
        raise NotFoundError("Original photograph file not found in storage")

    return FileResponse(
        path=orig_path,
        media_type=photo.mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get(
    "/download",
    summary="Download full-resolution photograph as an attachment",
)
async def download_photo(
    event_id: str,
    photo_id: uuid.UUID,
    session_id: Optional[uuid.UUID] = Query(None, description="Active search session ID for private photos"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    photo = await check_image_access(db, event_id, photo_id, session_id, current_user)

    if storage_service.is_r2:
        presigned_url = storage_service.generate_presigned_url(
            photo.storage_path,
            filename=photo.original_filename,
        )
        if not presigned_url:
            raise NotFoundError("Photograph not found in R2 storage")
        return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    orig_path = Path(photo.storage_path)
    if not orig_path.exists():
        raise NotFoundError("Original photograph file not found in storage")

    return FileResponse(
        path=orig_path,
        media_type=photo.mime_type,
        filename=photo.original_filename,
        headers={"Content-Disposition": f'attachment; filename="{photo.original_filename}"'},
    )

