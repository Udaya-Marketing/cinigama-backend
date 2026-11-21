import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_async_db,
    get_current_user,
    get_optional_user,
    require_organiser,
)
from app.models.user import User
from app.schemas.photo import (
    PhotoBatchDelete,
    PhotoBatchResult,
    PhotoBatchUpdate,
    PhotoBulkUploadResult,
    PhotoProcessingStatusResponse,
    PhotoRead,
    PhotoUpdate,
)
from app.schemas.response import APIResponse, PaginatedResponse
from app.services.photo_service import PhotoService

router = APIRouter(prefix="/events/{event_id}/photos", tags=["Photos"])


@router.post(
    "",
    response_model=APIResponse[PhotoRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single event photograph",
)
async def upload_photo(
    event_id: str,
    file: UploadFile = File(..., description="Image file (JPEG, PNG, WebP)"),
    is_public: bool = Form(default=False, description="Whether photograph is publicly visible"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    photo = await PhotoService.upload_single_photo(
        db=db,
        event_id=event_id,
        file=file,
        current_user=current_user,
        is_public=is_public,
    )
    return APIResponse(
        success=True,
        message="Photo uploaded and queued for face indexing",
        data=PhotoService.to_photo_read(photo, event_id),
    )


@router.post(
    "/bulk",
    response_model=APIResponse[PhotoBulkUploadResult],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk upload multiple event photographs",
)
async def upload_bulk_photos(
    event_id: str,
    files: List[UploadFile] = File(..., description="List of image files to upload"),
    is_public: bool = Form(default=False),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    result = await PhotoService.upload_bulk_photos(
        db=db,
        event_id=event_id,
        files=files,
        current_user=current_user,
        is_public=is_public,
    )
    return APIResponse(
        success=True,
        message=f"Uploaded {result.successful} photos successfully ({result.failed} failed)",
        data=result,
    )


@router.get(
    "",
    response_model=PaginatedResponse[PhotoRead],
    summary="List event photographs with pagination, search, and status filters",
)
async def list_photos(
    event_id: str,
    status: Optional[str] = Query(None, pattern="^(pending|processing|completed|failed)$"),
    is_public: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Search by original filename"),
    sort_by: str = Query("created_at", pattern="^(created_at|file_size|original_filename|processing_status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    items, total = await PhotoService.list_event_photos(
        db=db,
        event_id=event_id,
        current_user=current_user,
        status=status,
        is_public=is_public,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginatedResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/processing-status",
    response_model=APIResponse[PhotoProcessingStatusResponse],
    summary="Get current face processing job statuses for event",
)
async def get_processing_status(
    event_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    status_resp = await PhotoService.get_processing_status(db, event_id, current_user)
    return APIResponse(
        success=True,
        message="Processing status retrieved",
        data=status_resp,
    )


@router.get(
    "/{photo_id}",
    response_model=APIResponse[PhotoRead],
    summary="Get photo metadata by ID",
)
async def get_photo(
    event_id: str,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
):
    photo = await PhotoService.get_photo_by_id(db, event_id, photo_id)
    return APIResponse(
        success=True,
        message="Photo metadata retrieved",
        data=PhotoService.to_photo_read(photo, event_id),
    )


@router.patch(
    "/{photo_id}",
    response_model=APIResponse[PhotoRead],
    summary="Update photo visibility (public / private)",
)
async def update_photo(
    event_id: str,
    photo_id: uuid.UUID,
    photo_in: PhotoUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    updated = await PhotoService.update_photo(db, event_id, photo_id, photo_in, current_user)
    return APIResponse(
        success=True,
        message="Photo updated successfully",
        data=PhotoService.to_photo_read(updated, event_id),
    )


@router.delete(
    "/{photo_id}",
    response_model=APIResponse[None],
    summary="Delete photograph, thumbnails, and associated face embeddings",
)
async def delete_photo(
    event_id: str,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    await PhotoService.delete_photo(db, event_id, photo_id, current_user)
    return APIResponse(
        success=True,
        message="Photo and associated face records deleted successfully",
        data=None,
    )


@router.post(
    "/batch-update",
    response_model=APIResponse[PhotoBatchResult],
    summary="Batch update visibility (public/private) for multiple photos",
)
async def batch_update_photos(
    event_id: str,
    payload: PhotoBatchUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    updated_ids = await PhotoService.batch_update_photos(
        db=db,
        event_id=event_id,
        photo_ids=payload.photo_ids,
        is_public=payload.is_public,
        current_user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Successfully updated visibility for {len(updated_ids)} photo(s)",
        data=PhotoBatchResult(affected=len(updated_ids), photo_ids=updated_ids),
    )


@router.post(
    "/batch-delete",
    response_model=APIResponse[PhotoBatchResult],
    summary="Batch delete multiple photographs and their face vectors",
)
async def batch_delete_photos(
    event_id: str,
    payload: PhotoBatchDelete,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    deleted_ids = await PhotoService.batch_delete_photos(
        db=db,
        event_id=event_id,
        photo_ids=payload.photo_ids,
        current_user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Successfully deleted {len(deleted_ids)} photo(s)",
        data=PhotoBatchResult(affected=len(deleted_ids), photo_ids=deleted_ids),
    )


global_router = APIRouter(prefix="/photos", tags=["All Photos Management"])


@global_router.get(
    "",
    response_model=PaginatedResponse[PhotoRead],
    summary="View and manage all photos with pagination, filtering, and search",
)
async def list_all_photos(
    event_id: Optional[str] = Query(None, description="Optional filter by event ID or slug"),
    status: Optional[str] = Query(None, pattern="^(pending|processing|completed|failed)$", description="Filter by processing status"),
    is_public: Optional[bool] = Query(None, description="Filter by visibility"),
    search: Optional[str] = Query(None, description="Search by original filename"),
    sort_by: str = Query("created_at", pattern="^(created_at|file_size|original_filename|processing_status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await PhotoService.list_all_photos(
        db=db,
        current_user=current_user,
        event_id=event_id,
        status=status,
        is_public=is_public,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginatedResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@global_router.get(
    "/{photo_id}",
    response_model=APIResponse[PhotoRead],
    summary="Get photo metadata by ID",
)
async def get_photo_direct(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    photo = await PhotoService.get_photo_direct(db, photo_id, current_user)
    return APIResponse(
        success=True,
        message="Photo metadata retrieved",
        data=PhotoService.to_photo_read(photo, photo.event_id),
    )


@global_router.patch(
    "/{photo_id}",
    response_model=APIResponse[PhotoRead],
    summary="Update photo visibility (public / private)",
)
async def update_photo_direct(
    photo_id: uuid.UUID,
    photo_in: PhotoUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    updated = await PhotoService.update_photo_direct(db, photo_id, photo_in, current_user)
    return APIResponse(
        success=True,
        message="Photo updated successfully",
        data=PhotoService.to_photo_read(updated, updated.event_id),
    )


@global_router.delete(
    "/{photo_id}",
    response_model=APIResponse[dict],
    summary="Delete photograph, thumbnails, and associated face embeddings",
)
async def delete_photo_direct(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    await PhotoService.delete_photo_direct(db, photo_id, current_user)
    return APIResponse(
        success=True,
        message="Photo and associated face records deleted successfully",
        data={"photo_id": str(photo_id)},
    )


@global_router.post(
    "/batch-update",
    response_model=APIResponse[PhotoBatchResult],
    summary="Batch update visibility (public/private) for multiple photos",
)
async def batch_update_photos_direct(
    payload: PhotoBatchUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    updated_ids = await PhotoService.batch_update_photos_direct(
        db=db,
        photo_ids=payload.photo_ids,
        is_public=payload.is_public,
        current_user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Successfully updated visibility for {len(updated_ids)} photo(s)",
        data=PhotoBatchResult(affected=len(updated_ids), photo_ids=updated_ids),
    )


@global_router.post(
    "/batch-delete",
    response_model=APIResponse[PhotoBatchResult],
    summary="Batch delete multiple photographs and their face vectors",
)
async def batch_delete_photos_direct(
    payload: PhotoBatchDelete,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    deleted_ids = await PhotoService.batch_delete_photos_direct(
        db=db,
        photo_ids=payload.photo_ids,
        current_user=current_user,
    )
    return APIResponse(
        success=True,
        message=f"Successfully deleted {len(deleted_ids)} photo(s)",
        data=PhotoBatchResult(affected=len(deleted_ids), photo_ids=deleted_ids),
    )


