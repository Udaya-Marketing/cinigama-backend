import re
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password, verify_password
from app.models.event import Event
from app.models.face import PhotoFace
from app.models.photo import Photo
from app.models.user import User
from app.schemas.event import EventCreate, EventStats, EventUpdate
from app.services.storage_service import storage_service


def generate_slug(name: str) -> str:
    """Generate a clean, URL-safe slug from event name."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")


class EventService:
    @staticmethod
    async def create_event(
        db: AsyncSession,
        event_in: EventCreate,
        current_user: User,
    ) -> Event:
        base_slug = event_in.slug or generate_slug(event_in.name)
        slug = base_slug

        # Ensure slug uniqueness
        counter = 1
        while True:
            existing = await db.execute(select(Event).where(Event.slug == slug))
            if not existing.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        access_code_hash = None
        if event_in.access_type == "code_protected" and event_in.access_code:
            access_code_hash = hash_password(event_in.access_code)

        event = Event(
            id=uuid.uuid4(),
            organiser_id=current_user.id,
            name=event_in.name.strip(),
            description=event_in.description,
            event_date=event_in.event_date,
            slug=slug,
            access_type=event_in.access_type,
            access_code_hash=access_code_hash,
            status="active",
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def get_event_by_id(
        db: AsyncSession,
        event_id: uuid.UUID,
    ) -> Event:
        result = await db.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        if not event:
            raise NotFoundError(f"Event with ID {event_id} not found")
        return event

    @staticmethod
    async def get_event_by_slug(
        db: AsyncSession,
        slug: str,
    ) -> Event:
        result = await db.execute(select(Event).where(Event.slug == slug))
        event = result.scalar_one_or_none()
        if not event:
            raise NotFoundError(f"Event with slug '{slug}' not found")
        return event

    @staticmethod
    async def list_events(
        db: AsyncSession,
        current_user: Optional[User] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Event], int]:
        query = select(Event)
        count_query = select(func.count(Event.id))

        # Organisers only see their events unless admin
        if current_user:
            if current_user.role == "organiser":
                query = query.where(Event.organiser_id == current_user.id)
                count_query = count_query.where(Event.organiser_id == current_user.id)
        else:
            # Public listing only shows public active events
            query = query.where(Event.access_type == "public", Event.status == "active")
            count_query = count_query.where(Event.access_type == "public", Event.status == "active")

        total = (await db.execute(count_query)).scalar_one()

        query = query.order_by(Event.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = (await db.execute(query)).scalars().all()

        return list(items), total

    @staticmethod
    async def update_event(
        db: AsyncSession,
        event_id: uuid.UUID,
        event_in: EventUpdate,
        current_user: User,
    ) -> Event:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Only the event organiser can modify this event")

        update_data = event_in.model_dump(exclude_unset=True)
        if "access_code" in update_data:
            code = update_data.pop("access_code")
            if code:
                event.access_code_hash = hash_password(code)
            else:
                event.access_code_hash = None

        for field, value in update_data.items():
            setattr(event, field, value)

        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def delete_event(
        db: AsyncSession,
        event_id: uuid.UUID,
        current_user: User,
    ) -> None:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Only the event organiser can delete this event")

        # Delete from DB (cascades to photos, faces, sessions, jobs)
        await db.delete(event)
        await db.commit()

        # Delete filesystem directory for this event
        storage_service.delete_event_directory(event_id)

    @staticmethod
    async def get_event_stats(
        db: AsyncSession,
        event_id: uuid.UUID,
        current_user: User,
    ) -> EventStats:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to view stats for this event")

        # Aggregate counts
        total_photos = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id))
        ).scalar_one()
        pending = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id, Photo.processing_status == "pending"))
        ).scalar_one()
        processing = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id, Photo.processing_status == "processing"))
        ).scalar_one()
        completed = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id, Photo.processing_status == "completed"))
        ).scalar_one()
        failed = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id, Photo.processing_status == "failed"))
        ).scalar_one()
        public_photos = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id, Photo.is_public == True))  # noqa: E712
        ).scalar_one()
        private_photos = (
            await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id, Photo.is_public == False))  # noqa: E712
        ).scalar_one()
        total_faces = (
            await db.execute(select(func.count(PhotoFace.id)).where(PhotoFace.event_id == event_id))
        ).scalar_one()

        return EventStats(
            event_id=event_id,
            total_photos=total_photos,
            pending_photos=pending,
            processing_photos=processing,
            completed_photos=completed,
            failed_photos=failed,
            public_photos=public_photos,
            private_photos=private_photos,
            total_faces_indexed=total_faces,
        )

    @staticmethod
    def verify_event_access(event: Event, access_code: Optional[str] = None) -> bool:
        """Check whether an attendee has valid access to the event."""
        if event.access_type == "public":
            return True
        if event.access_type == "code_protected":
            if not access_code or not event.access_code_hash:
                return False
            return verify_password(access_code, event.access_code_hash)
        return False

