import datetime
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.base import Base
from app.models.event import Event
from app.models.job import PhotoProcessingJob
from app.models.photo import Photo
from app.models.user import User
from app.worker.processor import PhotoProcessorWorker


def test_worker_recover_stale_jobs():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    worker = PhotoProcessorWorker()

    with Session(engine) as session:
        user = User(
            id=uuid.uuid4(),
            email=f"worker_test_{uuid.uuid4().hex[:6]}@test.com",
            full_name="Worker User",
            password_hash="fake",
            role="organiser",
        )
        session.add(user)
        session.flush()

        event = Event(
            id=uuid.uuid4(),
            organiser_id=user.id,
            name="Worker Event",
            slug=f"worker-event-{uuid.uuid4().hex[:6]}",
        )
        session.add(event)
        session.flush()

        photo = Photo(
            id=uuid.uuid4(),
            event_id=event.id,
            original_filename="stale.jpg",
            storage_path="/tmp/stale.jpg",
            mime_type="image/jpeg",
            file_size=100,
            processing_status="processing",
        )
        session.add(photo)
        session.flush()

        # Job started 10 minutes ago (> lock timeout)
        stale_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
        job = PhotoProcessingJob(
            id=uuid.uuid4(),
            photo_id=photo.id,
            status="processing",
            attempts=1,
            started_at=stale_time,
        )
        session.add(job)
        session.commit()

        # Run recovery
        recovered = worker.recover_stale_jobs(session)
        assert recovered >= 1

        # Check job is reset to pending
        refreshed_job = session.query(PhotoProcessingJob).filter_by(id=job.id).first()
        assert refreshed_job.status == "pending"
