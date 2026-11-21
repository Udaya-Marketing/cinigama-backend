import uuid
from pathlib import Path
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_async_db,
    get_current_user,
    get_optional_user,
)
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.restricted_face import RestrictedFace
from app.models.user import User
from app.schemas.response import APIResponse
from app.schemas.restricted_face import (
    RestrictedFaceListResponse,
    RestrictedFaceRead,
)
from app.services.restricted_face_service import RestrictedFaceService
from app.services.storage_service import storage_service

router = APIRouter(prefix="/events/{event_id}/restricted-faces", tags=["Restricted Faces"])


@router.post(
    "",
    response_model=APIResponse[RestrictedFaceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Restrict a face by uploading a reference photograph",
)
async def restrict_face_by_upload(
    event_id: str,
    photo: UploadFile = File(..., description="Image containing the face to restrict from selfie search"),
    name: Optional[str] = Form(None, description="Optional name or identity tag of the person"),
    reason: Optional[str] = Form(None, description="Reason for restriction (e.g. opt-out, policy)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    rf = await RestrictedFaceService.add_restricted_face_from_upload(
        db=db,
        event_id=event_id,
        photo_file=photo,
        name=name,
        reason=reason,
        current_user=current_user,
    )
    thumb_url = None
    if rf.thumbnail_path:
        if storage_service.is_r2:
            thumb_url = storage_service.generate_presigned_url(rf.thumbnail_path)
        else:
            thumb_url = f"/api/v1/events/{rf.event_id}/restricted-faces/{rf.id}/thumbnail"

    read_item = RestrictedFaceRead(
        id=rf.id,
        event_id=rf.event_id,
        name=rf.name,
        reason=rf.reason,
        thumbnail_url=thumb_url,
        detection_confidence=rf.detection_confidence,
        created_at=rf.created_at,
        created_by=rf.created_by,
    )
    return APIResponse(
        success=True,
        message="Face successfully added to restricted list for this event",
        data=read_item,
    )


@router.post(
    "/from-face/{face_id}",
    response_model=APIResponse[RestrictedFaceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Restrict a face by referencing an existing photo face ID",
)
async def restrict_face_by_id(
    event_id: str,
    face_id: uuid.UUID,
    name: Optional[str] = Form(None, description="Optional name or identity tag"),
    reason: Optional[str] = Form(None, description="Reason for restriction"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    rf = await RestrictedFaceService.add_restricted_face_from_photo_face(
        db=db,
        event_id=event_id,
        face_id=face_id,
        name=name,
        reason=reason,
        current_user=current_user,
    )
    thumb_url = None
    if rf.thumbnail_path:
        if storage_service.is_r2:
            thumb_url = storage_service.generate_presigned_url(rf.thumbnail_path)
        else:
            thumb_url = f"/api/v1/events/{rf.event_id}/restricted-faces/{rf.id}/thumbnail"

    read_item = RestrictedFaceRead(
        id=rf.id,
        event_id=rf.event_id,
        name=rf.name,
        reason=rf.reason,
        thumbnail_url=thumb_url,
        detection_confidence=rf.detection_confidence,
        created_at=rf.created_at,
        created_by=rf.created_by,
    )
    return APIResponse(
        success=True,
        message="Face successfully restricted from selfie search",
        data=read_item,
    )


@router.get(
    "",
    response_model=APIResponse[RestrictedFaceListResponse],
    summary="List all restricted faces for an event",
)
async def list_restricted_faces(
    event_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await RestrictedFaceService.list_restricted_faces(
        db=db,
        event_id=event_id,
        skip=skip,
        limit=limit,
        current_user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Retrieved {len(items)} restricted face(s)",
        data=RestrictedFaceListResponse(items=items, total=total),
    )


@router.delete(
    "/{restricted_face_id}",
    response_model=APIResponse[dict],
    summary="Remove a face from the restricted list (allow selfie search again)",
)
async def delete_restricted_face(
    event_id: str,
    restricted_face_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    await RestrictedFaceService.delete_restricted_face(
        db=db,
        event_id=event_id,
        restricted_face_id=restricted_face_id,
        current_user=current_user,
    )
    return APIResponse(
        success=True,
        message="Restricted face removed successfully. Selfie search is now permitted.",
        data={"restricted_face_id": str(restricted_face_id)},
    )


@router.get(
    "/{restricted_face_id}/thumbnail",
    summary="Get thumbnail of a restricted face",
)
async def get_restricted_face_thumbnail(
    event_id: str,
    restricted_face_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    from sqlalchemy import select
    stmt = select(RestrictedFace).where(
        RestrictedFace.id == restricted_face_id,
    )
    rf = (await db.execute(stmt)).scalar_one_or_none()
    if not rf or not rf.thumbnail_path:
        raise NotFoundError("Thumbnail not found for restricted face")

    if storage_service.is_r2:
        return RedirectResponse(storage_service.generate_presigned_url(rf.thumbnail_path))

    path = Path(rf.thumbnail_path)
    if not path.exists():
        raise NotFoundError("Thumbnail file missing on disk")

    return FileResponse(path, media_type="image/webp")
