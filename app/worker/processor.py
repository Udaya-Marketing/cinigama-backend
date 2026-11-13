import datetime
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import app_logger
from app.db.session import SyncSessionLocal
from app.models.face import PhotoFace
from app.models.job import PhotoProcessingJob
from app.models.photo import Photo
from app.services.face_service import FaceRecognitionEngine
from app.services.storage_service import storage_service

running = True


def handle_shutdown(signum, frame):
    global running
    app_logger.info(f"Received signal {signum}. Shutting down worker gracefully...")
    running = False


class PhotoProcessorWorker:
    def __init__(self):
        self.face_engine = FaceRecognitionEngine.get_instance()
        self.batch_size = settings.WORKER_BATCH_SIZE
        self.poll_interval = settings.WORKER_POLL_INTERVAL_SECONDS
        self.max_attempts = settings.WORKER_MAX_ATTEMPTS
        self.lock_timeout = settings.WORKER_LOCK_TIMEOUT_SECONDS

    def recover_stale_jobs(self, session: Session) -> int:
        """Reset jobs stuck in 'processing' state due to worker crashes."""
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(seconds=self.lock_timeout)

        stale_jobs = (
            session.query(PhotoProcessingJob)
            .filter(
                PhotoProcessingJob.status == "processing",
                PhotoProcessingJob.started_at < cutoff,
            )
            .all()
        )

        recovered = 0
        for job in stale_jobs:
            if job.attempts >= self.max_attempts:
                job.status = "failed"
                job.last_error = "Job timed out and reached maximum retry attempts"
                if job.photo:
                    job.photo.processing_status = "failed"
                    job.photo.processing_error = job.last_error
            else:
                job.status = "pending"
                job.last_error = "Recovered from crashed/timed-out worker process"
            recovered += 1

        if recovered > 0:
            session.commit()
            app_logger.warning(f"Recovered {recovered} stale processing jobs")

        return recovered

    def claim_next_job(self, session: Session) -> Optional[PhotoProcessingJob]:
        """Claim a single pending job using FOR UPDATE SKIP LOCKED."""
        stmt = (
            select(PhotoProcessingJob)
            .filter(PhotoProcessingJob.status == "pending")
            .order_by(PhotoProcessingJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = session.execute(stmt).scalar_one_or_none()
        if job:
            job.status = "processing"
            job.attempts += 1
            job.started_at = datetime.datetime.now(datetime.timezone.utc)
            session.commit()
        return job

    def process_job(self, job_id: str) -> bool:
        """Process a claimed job: detect faces, store embeddings, generate thumbnail."""
        with SyncSessionLocal() as session:
            job = session.query(PhotoProcessingJob).filter_by(id=job_id).first()
            if not job:
                return False

            photo = session.query(Photo).filter_by(id=job.photo_id).first()
            if not photo:
                job.status = "failed"
                job.last_error = "Photo record not found"
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                session.commit()
                return False

            temp_local_file = None
            try:
                # 1. Update photo status to processing
                photo.processing_status = "processing"
                session.commit()

                # 2. Ensure image is available on local disk for inference
                if storage_service.is_r2 or not Path(photo.storage_path).exists():
                    temp_local_file = storage_service.download_to_temp_file(photo.storage_path)
                    inference_source = temp_local_file
                else:
                    inference_source = Path(photo.storage_path)

                # 3. Detect faces and generate embeddings
                detected_faces = self.face_engine.detect_and_extract_faces(inference_source)

                # 4. Idempotently remove any existing face records for this photo
                session.query(PhotoFace).filter_by(photo_id=photo.id).delete()

                # 5. Insert newly detected face embeddings
                for face in detected_faces:
                    photo_face = PhotoFace(
                        event_id=photo.event_id,
                        photo_id=photo.id,
                        embedding=face.embedding,
                        bounding_box=face.bounding_box,
                        detection_confidence=face.confidence,
                        landmarks=face.landmarks,
                    )
                    session.add(photo_face)

                # 6. Generate optimized WebP thumbnail (uploaded to R2 or saved locally)
                thumb_path = storage_service.generate_thumbnail(
                    event_id=photo.event_id,
                    photo_id=photo.id,
                    original_source=inference_source,
                )
                photo.thumbnail_path = str(thumb_path)

                # 7. Mark completed
                now = datetime.datetime.now(datetime.timezone.utc)
                photo.processing_status = "completed"
                photo.processing_error = None
                job.status = "completed"
                job.completed_at = now
                job.last_error = None

                session.commit()
                app_logger.info(
                    f"Successfully processed photo {photo.id}: "
                    f"{len(detected_faces)} face(s) detected and indexed"
                )
                return True

            except Exception as exc:
                session.rollback()
                app_logger.exception(f"Error processing photo {photo.id}: {exc}")

                with SyncSessionLocal() as err_session:
                    err_job = err_session.query(PhotoProcessingJob).filter_by(id=job_id).first()
                    err_photo = err_session.query(Photo).filter_by(id=photo.id).first()

                    if err_job:
                        err_job.last_error = str(exc)
                        if err_job.attempts >= self.max_attempts:
                            err_job.status = "failed"
                            err_job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                            if err_photo:
                                err_photo.processing_status = "failed"
                                err_photo.processing_error = str(exc)
                        else:
                            err_job.status = "pending"  # Re-enqueue for retry
                            if err_photo:
                                err_photo.processing_status = "pending"

                    err_session.commit()
                return False
            finally:
                if temp_local_file and temp_local_file.exists():
                    try:
                        temp_local_file.unlink()
                    except Exception as e:
                        app_logger.warning(f"Failed to delete temp file {temp_local_file}: {e}")

    def run(self) -> None:
        """Main worker execution loop."""
        app_logger.info("Starting Photo Processing Background Worker...")
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        last_recovery = 0.0

        while running:
            try:
                now = time.time()
                # Run crash recovery check every 60 seconds
                if now - last_recovery > 60.0:
                    with SyncSessionLocal() as session:
                        self.recover_stale_jobs(session)
                    last_recovery = now

                # Claim a pending job
                job_id = None
                with SyncSessionLocal() as session:
                    job = self.claim_next_job(session)
                    if job:
                        job_id = str(job.id)

                if job_id:
                    self.process_job(job_id)
                else:
                    time.sleep(self.poll_interval)

            except Exception as e:
                app_logger.error(f"Worker loop error: {e}")
                time.sleep(self.poll_interval)

        app_logger.info("Photo Processing Worker stopped cleanly.")


def main():
    worker = PhotoProcessorWorker()
    worker.run()


if __name__ == "__main__":
    main()

