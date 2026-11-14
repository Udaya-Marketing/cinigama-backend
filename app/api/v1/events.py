import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, get_current_user, get_optional_user, require_organiser
from app.models.user import User
from app.schemas.event import EventCreate, EventRead, EventStats, EventUpdate
from app.schemas.response import APIResponse, PaginatedResponse
from app.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    response_model=APIResponse[EventRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new photography event",
)
async def create_event(
    event_in: EventCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    event = await EventService.create_event(db, event_in, current_user)
    return APIResponse(
        success=True,
        message="Event created successfully",
        data=EventRead.model_validate(event),
    )


@router.get(
    "",
    response_model=PaginatedResponse[EventRead],
    summary="List events (organisers see their events, public sees active public events)",
)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    items, total = await EventService.list_events(db, current_user, page, page_size)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginatedResponse(
        success=True,
        items=[EventRead.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/{event_id}",
    response_model=APIResponse[EventRead],
    summary="Get event details by ID or slug",
)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    event = await EventService.get_event_by_id(db, event_id)
    return APIResponse(
        success=True,
        message="Event details retrieved",
        data=EventRead.model_validate(event),
    )


@router.patch(
    "/{event_id}",
    response_model=APIResponse[EventRead],
    summary="Update event configuration",
)
async def update_event(
    event_id: str,
    event_in: EventUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    updated = await EventService.update_event(db, event_id, event_in, current_user)
    return APIResponse(
        success=True,
        message="Event updated successfully",
        data=EventRead.model_validate(updated),
    )


@router.delete(
    "/{event_id}",
    response_model=APIResponse[None],
    summary="Delete event and all associated photos and biometric indexes",
)
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    await EventService.delete_event(db, event_id, current_user)
    return APIResponse(
        success=True,
        message="Event and all associated media deleted successfully",
        data=None,
    )


@router.get(
    "/{event_id}/stats",
    response_model=APIResponse[EventStats],
    summary="Get event photo and face processing statistics",
)
async def get_event_stats(
    event_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_organiser),
):
    stats = await EventService.get_event_stats(db, event_id, current_user)
    return APIResponse(
        success=True,
        message="Event statistics retrieved",
        data=stats,
    )

