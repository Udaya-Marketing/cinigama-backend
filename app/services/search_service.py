import datetime
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.audit import record_audit_log
from app.core.exceptions import (
    AuthenticationError,
    ConsentRequiredError,
    FaceDetectionError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.logging import app_logger
from app.models.event import Event
from app.models.face import PhotoFace
from app.models.photo import Photo
from app.models.search import SearchSession
from app.models.user import User
from app.schemas.photo import PhotoRead
from app.schemas.search import (
    ConsentCreate,
    FaceSearchResponse,
    MatchedPhotoItem,
    SearchSessionRead,
)
from app.services.event_service import EventService
from app.services.face_service import FaceRecognitionEngine
from app.services.photo_service import PhotoService


def to_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


class SearchService:
    @staticmethod
    async def create_session_with_consent(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        consent_in: ConsentCreate,
        current_user: Optional[User] = None,
        ip_address: Optional[str] = None,
    ) -> SearchSession:
        """Create an attendee search session with explicit DPDP Act 2023 compliant consent."""
        if not consent_in.consent_given:
            raise ConsentRequiredError("Explicit attendee consent is required to perform facial search")

        event = await EventService.get_event_by_id(db, event_id)
        if event.status != "active":
            raise PermissionDeniedError("Event is not currently active")

        canonical_id = event.id
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(minutes=settings.SEARCH_SESSION_EXPIRE_MINUTES)

        session = SearchSession(
            id=uuid.uuid4(),
            event_id=canonical_id,
            attendee_id=current_user.id if current_user else None,
            consent_timestamp=now,
            consent_purpose=consent_in.purpose,
            status="active",
            expires_at=expires_at,
        )
        db.add(session)
        await db.flush()

        await record_audit_log(
            db=db,
            action="CONSENT_GRANTED",
            event_id=canonical_id,
            user_id=current_user.id if current_user else None,
            details={"purpose": consent_in.purpose, "session_id": str(session.id)},
            ip_address=ip_address,
        )

        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def get_valid_session(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        session_id: uuid.UUID,
    ) -> SearchSession:
        """Validate that a search session exists, belongs to the event, and is active/unexpired."""
        event = await EventService.get_event_by_id(db, event_id)
        canonical_id = event.id

        stmt = select(SearchSession).where(
            SearchSession.id == session_id,
            SearchSession.event_id == canonical_id,
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            raise NotFoundError("Search session not found for this event")
        if session.status != "active":
            raise PermissionDeniedError(f"Search session is {session.status}")

        now = datetime.datetime.now(datetime.timezone.utc)
        if to_utc(session.expires_at) < now:
            session.status = "expired"
            await db.commit()
            raise PermissionDeniedError("Search session has expired. Please provide consent again.")

        return session

    @staticmethod
    async def revoke_session(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        session_id: uuid.UUID,
        current_user: Optional[User] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Revoke consent and expire search session immediately (DPDP Right to Withdraw Consent)."""
        session = await SearchService.get_valid_session(db, event_id, session_id)
        session.status = "revoked"

        await record_audit_log(
            db=db,
            action="CONSENT_REVOKED",
            event_id=session.event_id,
            user_id=current_user.id if current_user else None,
            details={"session_id": str(session_id)},
            ip_address=ip_address,
        )
        await db.commit()

    @staticmethod
    async def search_faces_for_attendee(
        db: AsyncSession,
        event_id: uuid.UUID | str,
        session_id: uuid.UUID,
        selfie_file: UploadFile,
        threshold: Optional[float] = None,
        current_user: Optional[User] = None,
        ip_address: Optional[str] = None,
    ) -> FaceSearchResponse:
        """Execute face recognition search:
        1. Validate active consent session.
        2. Detect exactly one face in selfie.
        3. Extract 128-d normalized embedding.
        4. Query event's indexed faces with strict event isolation.
        5. Filter by calibrated cosine threshold.
        6. Combine deduplicated face matches with public photos.
        7. Ensure temporary selfie data is wiped immediately.
        """
        session = await SearchService.get_valid_session(db, event_id, session_id)
        canonical_id = session.event_id

        # Operating threshold
        cos_threshold = threshold if threshold is not None else settings.SFACE_COSINE_THRESHOLD

        # Read and validate selfie in memory
        content = await selfie_file.read()
        engine = FaceRecognitionEngine.get_instance()

        try:
            detected_face = engine.process_selfie(content)
        finally:
            # Wipe memory buffer to ensure no temporary selfie data persists
            del content

        selfie_vec = detected_face.embedding

        # Exact Vector Similarity Search scoped strictly to event_id
        # In PostgreSQL with pgvector, cosine_distance operator is <=>
        # cosine_similarity = 1 - cosine_distance
        # For compatibility with SQLite unit tests, we test dialect
        dialect_name = db.bind.dialect.name if db.bind else "postgresql"

        matched_photos_map: Dict[uuid.UUID, Tuple[float, float]] = {}  # photo_id -> (similarity, confidence)

        if dialect_name == "postgresql":
            # Native pgvector exact cosine search
            # Cosine distance: PhotoFace.embedding.cosine_distance(selfie_vec)
            # Cosine distance = 1 - similarity => similarity = 1 - distance >= cos_threshold
            # => distance <= 1 - cos_threshold
            max_dist = 1.0 - cos_threshold
            stmt = (
                select(
                    PhotoFace.photo_id,
                    func.min(PhotoFace.embedding.cosine_distance(selfie_vec)).label("min_dist"),
                    func.max(PhotoFace.detection_confidence).label("confidence"),
                )
                .where(PhotoFace.event_id == canonical_id)
                .group_by(PhotoFace.photo_id)
                .having(func.min(PhotoFace.embedding.cosine_distance(selfie_vec)) <= max_dist)
            )
            rows = (await db.execute(stmt)).all()
            for r in rows:
                sim = 1.0 - float(r.min_dist)
                matched_photos_map[r.photo_id] = (sim, float(r.confidence))
        else:
            # Python-based exact cosine search fallback for SQLite in tests
            stmt = select(PhotoFace).where(PhotoFace.event_id == canonical_id)
            faces = (await db.execute(stmt)).scalars().all()
            for f in faces:
                sim = engine.compute_cosine_similarity(selfie_vec, f.embedding)
                if sim >= cos_threshold:
                    if f.photo_id not in matched_photos_map or sim > matched_photos_map[f.photo_id][0]:
                        matched_photos_map[f.photo_id] = (sim, f.detection_confidence)

        # Retrieve matched photo records
        matched_photo_ids = list(matched_photos_map.keys())
        matched_photos: List[Photo] = []
        if matched_photo_ids:
            p_stmt = (
                select(Photo)
                .where(
                    Photo.id.in_(matched_photo_ids),
                    Photo.event_id == canonical_id,
                    Photo.processing_status == "completed",
                )
                .options(selectinload(Photo.faces))
            )
            matched_photos = list((await db.execute(p_stmt)).scalars().all())

        # Retrieve public completed photos for this event
        pub_stmt = (
            select(Photo)
            .where(
                Photo.event_id == canonical_id,
                Photo.is_public == True,  # noqa: E712
                Photo.processing_status == "completed",
            )
            .options(selectinload(Photo.faces))
        )
        public_photos = list((await db.execute(pub_stmt)).scalars().all())

        # Combine and deduplicate
        seen_photo_ids: Set[uuid.UUID] = set()
        items: List[MatchedPhotoItem] = []

        # 1. Add face matches (sorted by similarity desc)
        matched_photos_sorted = sorted(
            matched_photos,
            key=lambda p: matched_photos_map[p.id][0],
            reverse=True,
        )

        for p in matched_photos_sorted:
            seen_photo_ids.add(p.id)
            sim, conf = matched_photos_map[p.id]
            pread = PhotoService.to_photo_read(p, canonical_id)
            items.append(
                MatchedPhotoItem(
                    photo=pread,
                    match_type="face_match",
                    similarity_score=round(sim, 4),
                    detection_confidence=round(conf, 4),
                )
            )

        # 2. Add public photos that weren't already matched
        pub_count = 0
        for p in public_photos:
            if p.id not in seen_photo_ids:
                seen_photo_ids.add(p.id)
                pread = PhotoService.to_photo_read(p, canonical_id)
                items.append(
                    MatchedPhotoItem(
                        photo=pread,
                        match_type="public",
                        similarity_score=None,
                        detection_confidence=None,
                    )
                )
                pub_count += 1

        # Audit log search operation (without biometric embeddings!)
        await record_audit_log(
            db=db,
            action="SELFIE_SEARCH",
            event_id=event_id,
            user_id=current_user.id if current_user else None,
            details={
                "session_id": str(session_id),
                "matched_count": len(matched_photos),
                "public_count": pub_count,
                "threshold_applied": cos_threshold,
            },
            ip_address=ip_address,
        )
        await db.commit()

        return FaceSearchResponse(
            session_id=session_id,
            event_id=canonical_id,
            faces_detected_in_selfie=1,
            matched_count=len(matched_photos),
            public_count=pub_count,
            total_returned=len(items),
            items=items,
        )
