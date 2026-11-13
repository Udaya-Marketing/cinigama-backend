import uuid
from typing import List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import InvalidImageError, NotFoundError, PermissionDeniedError
from app.models.event import Event
from app.models.face import PhotoFace
from app.models.job import PhotoProcessingJob
from app.models.photo import Photo
from app.models.user import User
from app.schemas.photo import (
    PhotoBulkUploadResult,
    PhotoProcessingStatusResponse,
    PhotoRead,
    PhotoUpdate,
)
from app.services.event_service import EventService
from app.services.storage_service import storage_service


class PhotoService:
    @staticmethod
    async def upload_single_photo(
        db: AsyncSession,
        event_id: uuid.UUID,
        file: UploadFile,
        current_user: User,
        is_public: bool = False,
    ) -> Photo:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to upload photos to this event")

        content = await file.read()
        filename = file.filename or "photo.jpg"

        mime_type, width, height, ext = storage_service.validate_and_inspect_image(
            content, filename
        )

        photo_id = uuid.uuid4()
        storage_path = storage_service.save_original_photo(
            event_id=event_id,
            photo_id=photo_id,
            file_bytes=content,
            ext=ext,
            mime_type=mime_type,
        )

        photo = Photo(
            id=photo_id,
            event_id=event_id,
            uploaded_by=current_user.id,
            original_filename=filename,
            storage_path=str(storage_path),
            thumbnail_path=None,  # Worker will generate
            mime_type=mime_type,
            file_size=len(content),
            width=width,
            height=height,
            is_public=is_public,
            processing_status="pending",
        )
        db.add(photo)

        # Enqueue background processing job
        job = PhotoProcessingJob(
            id=uuid.uuid4(),
            photo_id=photo_id,
            status="pending",
            attempts=0,
            max_attempts=3,
        )
        db.add(job)

        await db.commit()
        await db.refresh(photo)
        return photo

    @staticmethod
    async def upload_bulk_photos(
        db: AsyncSession,
        event_id: uuid.UUID,
        files: List[UploadFile],
        current_user: User,
        is_public: bool = False,
    ) -> PhotoBulkUploadResult:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to upload photos to this event")

        successful_photos: List[PhotoRead] = []
        errors: List[dict] = []

        for file in files:
            filename = file.filename or "unknown.jpg"
            try:
                content = await file.read()
                mime_type, width, height, ext = storage_service.validate_and_inspect_image(
                    content, filename
                )
                photo_id = uuid.uuid4()
                storage_path = storage_service.save_original_photo(
                    event_id=event_id,
                    photo_id=photo_id,
                    file_bytes=content,
                    ext=ext,
                    mime_type=mime_type,
                )

                photo = Photo(
                    id=photo_id,
                    event_id=event_id,
                    uploaded_by=current_user.id,
                    original_filename=filename,
                    storage_path=str(storage_path),
                    thumbnail_path=None,
                    mime_type=mime_type,
                    file_size=len(content),
                    width=width,
                    height=height,
                    is_public=is_public,
                    processing_status="pending",
                )
                db.add(photo)

                job = PhotoProcessingJob(
                    id=uuid.uuid4(),
                    photo_id=photo_id,
                    status="pending",
                    attempts=0,
                    max_attempts=3,
                )
                db.add(job)
                await db.flush()

                successful_photos.append(PhotoRead.model_validate(photo))

            except Exception as e:
                errors.append({"filename": filename, "error": str(e)})

        await db.commit()

        return PhotoBulkUploadResult(
            total_uploaded=len(files),
            successful=len(successful_photos),
            failed=len(errors),
            photos=successful_photos,
            errors=errors,
        )

    @staticmethod
    async def list_event_photos(
        db: AsyncSession,
        event_id: uuid.UUID,
        current_user: Optional[User] = None,
        status: Optional[str] = None,
        is_public: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[PhotoRead], int]:
        event = await EventService.get_event_by_id(db, event_id)

        # Check access permission:
        # If user is organiser or admin, can see all photos and filter by status
        is_manager = current_user and (current_user.id == event.organiser_id or current_user.role == "admin")

        query = select(Photo).where(Photo.event_id == event_id)
        count_query = select(func.count(Photo.id)).where(Photo.event_id == event_id)

        if not is_manager:
            # Attendees can only list public photos through this general endpoint
            query = query.where(Photo.is_public == True, Photo.processing_status == "completed")  # noqa: E712
            count_query = count_query.where(Photo.is_public == True, Photo.processing_status == "completed")  # noqa: E712
        else:
            if status:
                query = query.where(Photo.processing_status == status)
                count_query = count_query.where(Photo.processing_status == status)
            if is_public is not None:
                query = query.where(Photo.is_public == is_public)
                count_query = count_query.where(Photo.is_public == is_public)

        total = (await db.execute(count_query)).scalar_one()

        query = (
            query.options(selectinload(Photo.faces))
            .order_by(Photo.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        photos = (await db.execute(query)).scalars().all()

        photo_reads = []
        for p in photos:
            pread = PhotoRead.model_validate(p)
            pread.face_count = len(p.faces) if p.faces else 0
            photo_reads.append(pread)

        return photo_reads, total

    @staticmethod
    async def get_photo_by_id(
        db: AsyncSession,
        event_id: uuid.UUID,
        photo_id: uuid.UUID,
    ) -> Photo:
        query = select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id).options(selectinload(Photo.faces))
        result = await db.execute(query)
        photo = result.scalar_one_or_none()
        if not photo:
            raise NotFoundError(f"Photo {photo_id} in event {event_id} not found")
        return photo

    @staticmethod
    async def update_photo(
        db: AsyncSession,
        event_id: uuid.UUID,
        photo_id: uuid.UUID,
        photo_in: PhotoUpdate,
        current_user: User,
    ) -> Photo:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to edit photos in this event")

        photo = await PhotoService.get_photo_by_id(db, event_id, photo_id)
        if photo_in.is_public is not None:
            photo.is_public = photo_in.is_public

        await db.commit()
        await db.refresh(photo)
        return photo

    @staticmethod
    async def delete_photo(
        db: AsyncSession,
        event_id: uuid.UUID,
        photo_id: uuid.UUID,
        current_user: User,
    ) -> None:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to delete photos in this event")

        photo = await PhotoService.get_photo_by_id(db, event_id, photo_id)
        orig_path = photo.storage_path
        thumb_path = photo.thumbnail_path

        await db.delete(photo)
        await db.commit()

        storage_service.delete_photo_files(orig_path, thumb_path)

    @staticmethod
    async def batch_update_photos(
        db: AsyncSession,
        event_id: uuid.UUID,
        photo_ids: List[uuid.UUID],
        is_public: bool,
        current_user: User,
    ) -> List[uuid.UUID]:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to edit photos in this event")

        stmt = select(Photo).where(Photo.id.in_(photo_ids), Photo.event_id == event_id)
        photos = list((await db.execute(stmt)).scalars().all())

        updated_ids = []
        for p in photos:
            p.is_public = is_public
            updated_ids.append(p.id)

        await db.commit()
        return updated_ids

    @staticmethod
    async def batch_delete_photos(
        db: AsyncSession,
        event_id: uuid.UUID,
        photo_ids: List[uuid.UUID],
        current_user: User,
    ) -> List[uuid.UUID]:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to delete photos in this event")

        stmt = select(Photo).where(Photo.id.in_(photo_ids), Photo.event_id == event_id)
        photos = list((await db.execute(stmt)).scalars().all())

        deleted_ids = []
        file_paths_to_delete = []

        for p in photos:
            deleted_ids.append(p.id)
            file_paths_to_delete.append((p.storage_path, p.thumbnail_path))
            await db.delete(p)

        await db.commit()

        for orig_p, thumb_p in file_paths_to_delete:
            storage_service.delete_photo_files(orig_p, thumb_p)

        return deleted_ids

    @staticmethod
    async def get_processing_status(
        db: AsyncSession,
        event_id: uuid.UUID,
        current_user: User,
    ) -> PhotoProcessingStatusResponse:
        event = await EventService.get_event_by_id(db, event_id)
        if event.organiser_id != current_user.id and current_user.role != "admin":
            raise PermissionDeniedError("Not authorised to view processing status")

        total = (await db.execute(select(func.count(Photo.id)).where(Photo.event_id == event_id))).scalar_one()
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

        return PhotoProcessingStatusResponse(
            event_id=event_id,
            total=total,
            pending=pending,
            processing=processing,
            completed=completed,
            failed=failed,
        )

