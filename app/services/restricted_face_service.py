import io
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import UploadFile

from app.config import settings
from app.core.exceptions import (
    FaceDetectionError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.logging import app_logger
from app.models.event import Event
from app.models.face import PhotoFace
from app.models.photo import Photo
from app.models.restricted_face import RestrictedFace
from app.models.user import User
from app.schemas.restricted_face import RestrictedFaceRead
from app.services.event_service import EventService
from app.services.face_service import DetectedFace, FaceRecognitionEngine
from app.services.storage_service import storage_service


class RestrictedFaceService:
    @staticmethod
    def _save_thumbnail(
        event_id: uuid.UUID,
        restricted_id: uuid.UUID,
        img_bytes: bytes,
        box: Optional[Dict[str, int]] = None,
    ) -> str:
        """Crop and store face thumbnail for dashboard preview."""
        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
            pil_img = ImageOps.exif_transpose(pil_img) or pil_img

            if box:
                w_img, h_img = pil_img.size
                bx = max(0, int(box.get("x", 0)))
                by = max(0, int(box.get("y", 0)))
                bw = max(10, int(box.get("w", 50)))
                bh = max(10, int(box.get("h", 50)))
                pad_x = int(bw * 0.3)
                pad_y = int(bh * 0.3)
                x0 = max(0, bx - pad_x)
                y0 = max(0, by - pad_y)
                x1 = min(w_img, bx + bw + pad_x)
                y1 = min(h_img, by + bh + pad_y)
                pil_img = pil_img.crop((x0, y0, x1, y1))

            pil_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            pil_img.convert("RGB").save(buf, format="WEBP", quality=85)
            thumb_bytes = buf.getvalue()

            if storage_service.is_r2:
                key = f"events/{event_id}/restricted/{restricted_id}.webp"
                storage_service.get_s3_client().put_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=key,
                    Body=thumb_bytes,
                    ContentType="image/webp",
                )
                return key
            else:
                event_dir = storage_service.events_dir / str(event_id) / "restricted"
                event_dir.mkdir(parents=True, exist_ok=True)
                target = event_dir / f"{restricted_id}.webp"
                target.write_bytes(thumb_bytes)
                return str(target)
        except Exception as e:
            app_logger.warning(f"Could not generate restricted face thumbnail: {e}")
            return ""

    @staticmethod
    async def add_restricted_face_from_upload(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        photo_file: UploadFile,
        name: Optional[str] = None,
        reason: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> RestrictedFace:
        """Extract face from uploaded image and register it in the event restricted list."""
        event = await EventService.get_event_by_id(db, event_id)
        if current_user and current_user.role != "admin" and event.organiser_id != current_user.id:
            raise PermissionDeniedError("Only event organizers or admins can restrict faces.")

        content = await photo_file.read()
        engine = FaceRecognitionEngine.get_instance()

        try:
            detected_face = engine.process_selfie(content)
        except Exception:
            # Fallback to detect_faces to pick the most prominent face if process_selfie strict check fails
            faces = engine.detect_faces(content)
            if not faces:
                raise FaceDetectionError("No faces detected in the uploaded photo.")
            # Pick the face with largest area
            detected_face = max(
                faces,
                key=lambda f: f.bounding_box.get("w", 0) * f.bounding_box.get("h", 0),
            )

        restricted_id = uuid.uuid4()
        thumb_path = RestrictedFaceService._save_thumbnail(
            event_id=event.id,
            restricted_id=restricted_id,
            img_bytes=content,
            box=detected_face.bounding_box,
        )

        restricted = RestrictedFace(
            id=restricted_id,
            event_id=event.id,
            name=name.strip() if name else None,
            reason=reason.strip() if reason else None,
            embedding=detected_face.embedding,
            bounding_box=detected_face.bounding_box,
            detection_confidence=detected_face.confidence,
            thumbnail_path=thumb_path if thumb_path else None,
            created_by=current_user.id if current_user else None,
        )
        db.add(restricted)
        await db.commit()
        await db.refresh(restricted)
        return restricted

    @staticmethod
    async def add_restricted_face_from_photo_face(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        face_id: uuid.UUID,
        name: Optional[str] = None,
        reason: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> RestrictedFace:
        """Restrict a face using an existing detected face from the event's photos."""
        event = await EventService.get_event_by_id(db, event_id)
        if current_user and current_user.role != "admin" and event.organiser_id != current_user.id:
            raise PermissionDeniedError("Only event organizers or admins can restrict faces.")

        stmt = (
            select(PhotoFace)
            .where(PhotoFace.id == face_id, PhotoFace.event_id == event.id)
            .options(selectinload(PhotoFace.photo))
        )
        face_row = (await db.execute(stmt)).scalar_one_or_none()
        if not face_row:
            raise NotFoundError(f"Face {face_id} not found in event {event.id}")

        restricted_id = uuid.uuid4()
        thumb_path = ""
        try:
            if face_row.photo and face_row.photo.storage_path:
                source = face_row.photo.storage_path
                if storage_service.is_r2:
                    s3 = storage_service.get_s3_client()
                    obj = s3.get_object(Bucket=settings.R2_BUCKET_NAME, Key=source)
                    p_bytes = obj["Body"].read()
                elif Path(source).exists():
                    p_bytes = Path(source).read_bytes()
                else:
                    p_bytes = None

                if p_bytes:
                    thumb_path = RestrictedFaceService._save_thumbnail(
                        event_id=event.id,
                        restricted_id=restricted_id,
                        img_bytes=p_bytes,
                        box=face_row.bounding_box,
                    )
        except Exception as e:
            app_logger.warning(f"Could not crop thumbnail for photo face restriction: {e}")

        restricted = RestrictedFace(
            id=restricted_id,
            event_id=event.id,
            name=name.strip() if name else None,
            reason=reason.strip() if reason else None,
            embedding=face_row.embedding,
            bounding_box=face_row.bounding_box,
            detection_confidence=face_row.detection_confidence,
            thumbnail_path=thumb_path if thumb_path else None,
            created_by=current_user.id if current_user else None,
        )
        db.add(restricted)
        await db.commit()
        await db.refresh(restricted)
        return restricted

    @staticmethod
    async def list_restricted_faces(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        skip: int = 0,
        limit: int = 50,
        current_user: Optional[User] = None,
    ) -> Tuple[List[RestrictedFaceRead], int]:
        """List all restricted faces for an event."""
        event = await EventService.get_event_by_id(db, event_id)
        if current_user and current_user.role != "admin" and event.organiser_id != current_user.id:
            raise PermissionDeniedError("Only event organizers or admins can view restricted faces.")

        count_stmt = select(func.count(RestrictedFace.id)).where(RestrictedFace.event_id == event.id)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(RestrictedFace)
            .where(RestrictedFace.event_id == event.id)
            .order_by(RestrictedFace.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()

        items: List[RestrictedFaceRead] = []
        for r in rows:
            thumb_url = None
            if r.thumbnail_path:
                if storage_service.is_r2:
                    thumb_url = storage_service.generate_presigned_url(r.thumbnail_path)
                else:
                    thumb_url = f"/api/v1/events/{event.id}/restricted-faces/{r.id}/thumbnail"

            items.append(
                RestrictedFaceRead(
                    id=r.id,
                    event_id=r.event_id,
                    name=r.name,
                    reason=r.reason,
                    thumbnail_url=thumb_url,
                    detection_confidence=r.detection_confidence,
                    created_at=r.created_at,
                    created_by=r.created_by,
                )
            )

        return items, total

    @staticmethod
    async def delete_restricted_face(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        restricted_face_id: uuid.UUID,
        current_user: Optional[User] = None,
    ) -> bool:
        """Delete / unrestrict a face."""
        event = await EventService.get_event_by_id(db, event_id)
        if current_user and current_user.role != "admin" and event.organiser_id != current_user.id:
            raise PermissionDeniedError("Only event organizers or admins can remove restricted faces.")

        stmt = select(RestrictedFace).where(
            RestrictedFace.id == restricted_face_id,
            RestrictedFace.event_id == event.id,
        )
        rf = (await db.execute(stmt)).scalar_one_or_none()
        if not rf:
            raise NotFoundError(f"Restricted face {restricted_face_id} not found in event {event.id}")

        if rf.thumbnail_path and not storage_service.is_r2:
            try:
                p = Path(rf.thumbnail_path)
                if p.exists():
                    p.unlink()
            except OSError:
                pass

        await db.delete(rf)
        await db.commit()
        return True

    @staticmethod
    async def is_face_restricted(
        db: AsyncSession,
        event_id: uuid.UUID,
        selfie_vec: List[float] | np.ndarray,
        threshold: float = 0.50,
    ) -> Tuple[bool, Optional[RestrictedFace]]:
        """Check if an uploaded selfie matches any restricted face in this event with similarity >= threshold."""
        dialect_name = db.bind.dialect.name if db.bind else "postgresql"
        engine = FaceRecognitionEngine.get_instance()

        if dialect_name == "postgresql":
            # Exact cosine similarity search via pgvector: distance <= 1.0 - threshold
            max_dist = 1.0 - threshold
            stmt = (
                select(
                    RestrictedFace,
                    RestrictedFace.embedding.cosine_distance(selfie_vec).label("distance"),
                )
                .where(RestrictedFace.event_id == event_id)
                .order_by("distance")
                .limit(1)
            )
            row = (await db.execute(stmt)).first()
            if row:
                rf, dist = row
                sim = 1.0 - float(dist)
                if sim >= threshold:
                    return True, rf
            return False, None
        else:
            # SQLite fallback for unit tests
            stmt = select(RestrictedFace).where(RestrictedFace.event_id == event_id)
            rows = (await db.execute(stmt)).scalars().all()
            for rf in rows:
                sim = engine.compute_cosine_similarity(selfie_vec, rf.embedding)
                if sim >= threshold:
                    return True, rf
            return False, None
