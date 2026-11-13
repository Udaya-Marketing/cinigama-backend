# AI-Powered Event Photo Management & Face Recognition System

A production-ready, scalable, and self-hosted event photography backend built with **Python 3.12**, **FastAPI**, **PostgreSQL with pgvector**, and **OpenCV YuNet + SFace**.

The system enables event organisers to upload photographs (individually or in batches up to 1,000+ per event), automatically detects and indexes faces into 128-dimensional vector embeddings, and allows attendees to find all event photographs containing their matching face by simply uploading a selfie, alongside publicly viewable photos.

---

## 1. System Architecture

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             ORGANISER / PHOTOGRAPHER                             │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ Uploads bulk photos (up to 1,000+)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               FASTAPI REST API                                   │
│  - JWT Authentication & Role-Based Access Control                                │
│  - Multipart Photo Ingestion & Storage Service (Originals & Orientation)         │
│  - Enqueues Jobs into PostgreSQL (pending status)                                │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ FOR UPDATE SKIP LOCKED
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          BACKGROUND PROCESSING WORKER                            │
│  - Claims pending photo jobs safely with transactional locking                   │
│  - YuNet: Multi-face detection & 5-point landmark extraction                     │
│  - SFace: Facial alignment & 128-dimensional L2-normalized embedding extraction  │
│  - Generates optimized WebP thumbnails (metadata stripped)                       │
│  - Inserts embeddings into PostgreSQL pgvector                                   │
│  - Transitions photo status to 'completed'                                       │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         POSTGRESQL + PGVECTOR DATABASE                           │
│  - photo_faces: embedding vector(128) indexed with event_id                      │
│  - Strict event isolation: queries never leak cross-event photographs            │
└────────────────────────────────────────▲─────────────────────────────────────────┘
                                         │
                                         │ Exact Cosine Similarity Query
                                         │ (1 - cosine_distance >= threshold)
                                         │
┌────────────────────────────────────────┴─────────────────────────────────────────┐
│                                 ATTENDEE WORKFLOW                                │
│  1. Opens event gallery & provides explicit DPDP Act 2023 biometric consent      │
│  2. Uploads single selfie (strictly validated: exactly 1 clear face)            │
│  3. SFace extracts 128-d selfie embedding (temporary file wiped immediately)     │
│  4. PostgreSQL performs exact vector search scoped strictly to event_id         │
│  5. Returns deduplicated face matches + public event photographs                 │
│  6. Secure media delivery: enforces access checks on private images              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack & Licences

All models and dependencies use permissive, commercially viable open-source licences:

| Component | Technology | Licence | Purpose |
|---|---|---|---|
| **Web Framework** | Python 3.12 + FastAPI | MIT | Async REST API & validation |
| **Face Detection** | OpenCV YuNet (`face_detection_yunet_2023mar.onnx`) | **Apache 2.0** | Deep face detection & landmarks |
| **Face Recognition** | OpenCV SFace (`face_recognition_sface_2021dec.onnx`) | **Apache 2.0** | 128-d hyperspherical embeddings |
| **Vector Database** | PostgreSQL 16 + pgvector | PostgreSQL | Relational storage & exact vector search |
| **ORM & Migrations** | SQLAlchemy 2.x + Alembic | MIT | Type-safe database queries & migrations |
| **Image Processing** | Pillow + OpenCV | HPND / Apache 2.0 | EXIF orientation, WebP thumbnailing |
| **Worker System** | Independent Python Worker | MIT | `FOR UPDATE SKIP LOCKED` job processing |
| **Reverse Proxy** | Nginx Alpine | BSD 2-Clause | TLS termination & rate limiting |
| **Containerization** | Docker & Docker Compose | Apache 2.0 | Multi-container production deployment |

Detailed model provenance, upstream URLs, and verified SHA-256 checksums are documented in [models_zoo/MODEL_LICENSES.md](models_zoo/MODEL_LICENSES.md).

---

## 3. Key Architectural Features

1. **Strict Zero-Cloud AI Dependency**: Runs 100% on-premise or on a low-cost VPS with local OpenCV ONNX models; no AWS Rekognition, Google Cloud Vision, Azure Face API, or GPU hardware required.
2. **Dual-Backend Storage (Cloudflare R2 & Local Disk)**:
   - Configurable via `STORAGE_BACKEND=r2` or `STORAGE_BACKEND=local`.
   - Native integration with **Cloudflare R2** (`cinigama-storage`) with **$0 egress fees**.
   - Authenticated delivery via short-lived S3 presigned URLs with HTTP 307 Temporary Redirects.
   - Background workers stream images directly from R2 to ephemeral memory/disk and upload optimized WebP thumbnails to R2.
3. **Resource-Optimised (2 vCPU, 4GB RAM)**:
   - YuNet inference takes **~96 ms per image** on standard CPU.
   - Exact vector similarity search across 3,000 faces takes **0.036 ms** (27,000+ searches/sec).
   - Ingests **1,000 event photos in ~1.6 minutes** on a single worker (or under 50 seconds on two workers).
   - Memory footprint is only **~203 MB per worker**.
3. **Multi-Event Isolation**: Every database query and vector similarity calculation is scoped by `event_id`. An attendee searching in Event A can never match or view photos from Event B.
4. **Privacy & DPDP Act 2023 Compliance**:
   - Attendees must submit explicit, purposeful consent prior to face matching.
   - Temporary selfie image bytes are processed exclusively in-memory and wiped immediately.
   - Raw 128-dimensional biometric embeddings are never exposed through API responses.
   - Structured logs redact any biometric data automatically.
   - Search sessions expire automatically (default: 30 minutes) and can be revoked on-demand.
   - Deleting an event or photo cascades and purges all associated face vectors and files.
5. **Private Image Protection**:
   - The storage directory is never exposed statically via Nginx.
   - `/thumbnail`, `/view`, and `/download` endpoints verify ownership or matching search session authorization before streaming private files.
6. **Fault-Tolerant Background Worker**:
   - Multiple worker replicas can safely poll the database using `FOR UPDATE SKIP LOCKED`.
   - Automatically recovers stale jobs from interrupted or crashed worker processes.
   - Guaranteed idempotent processing (removes previous partial face records on retry).

---

## 4. Quick Start with Docker Compose

### Prerequisites
- Docker Engine 24+ and Docker Compose v2+
- Port 80 and 8000 available

### 1. Clone & Configure Environment
```bash
git clone <repository_url> event-photography
cd event-photography

# Copy default environment configuration
cp .env.example .env
```

### 2. Download Pretrained Models
Download and verify the official OpenCV Zoo ONNX weights:
```bash
python3 scripts/download_models.py
```
*(Alternatively, Docker Compose entrypoint will automatically download and verify models upon first boot).*

### 3. Start Production Services
```bash
docker compose up -d --build
```

The stack initializes:
- `event_photos_db`: PostgreSQL 16 with pgvector extension
- `event_photos_api`: FastAPI application on port 8000
- `event_photos_worker`: Background photo processing worker
- `event_photos_nginx`: Nginx reverse proxy on port 80

### 4. Verify System Health
```bash
curl http://localhost/api/v1/health
```
Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "models_ready": true,
  "disk_storage": {
    "backend": "cloudflare_r2",
    "bucket": "cinigama-storage",
    "total_bytes": 105087164416,
    "used_bytes": 25175420928,
    "free_bytes": 74526363648,
    "percent_free": 70.92
  }
}
```

### Storage Configuration (Cloudflare R2 or Local)
Configure your storage backend in `.env`:
```env
# Switch between Cloudflare R2 and Local Disk
STORAGE_BACKEND=r2

# Cloudflare R2 Object Storage
R2_ACCOUNT_ID=65254e62e5a251e99e43cd0e45e01a9a
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET_NAME=cinigama-storage
R2_ENDPOINT_URL=https://65254e62e5a251e99e43cd0e45e01a9a.r2.cloudflarestorage.com
R2_PRESIGNED_EXPIRY_SECONDS=900
```
When `STORAGE_BACKEND=r2`, original high-res photos and optimized WebP thumbnails are uploaded directly to Cloudflare R2. Delivery endpoints (`/thumbnail`, `/view`, `/download`) issue HTTP 307 Temporary Redirects to secure, short-lived presigned S3 URLs, enabling attendees to download directly from Cloudflare's global edge network with **zero egress fees**.

Interactive Swagger / OpenAPI documentation is available at:
- **Swagger UI**: `http://localhost/docs`
- **ReDoc**: `http://localhost/redoc`

---

## 5. Local Development Setup

### 1. Create Virtual Environment
```bash
# Using uv (recommended) or standard venv
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### 2. Run Tests
Execute the complete test suite (33 automated unit and integration tests):
```bash
PYTHONPATH=. pytest tests/ -v
```

### 3. Run Face Calibration
Calibrate the SFace cosine threshold measuring False Acceptance Rate (FAR) and False Rejection Rate (FRR):
```bash
PYTHONPATH=. python3 scripts/calibrate_threshold.py
```

### 4. Run Performance Benchmarks
Benchmark raw CPU inference speed, vector search latency, and memory consumption:
```bash
PYTHONPATH=. python3 scripts/benchmark_performance.py --inference-runs 20 --event-faces 3000
```

### 5. Start API & Worker Locally
```bash
# Terminal 1: Run API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Run Worker
python3 -m app.worker.processor
```

---

## 6. Complete API Reference & Examples

### A. Authentication

#### 1. Register an Organiser
```bash
curl -X POST http://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Priya Sharma",
    "email": "priya@studioevents.com",
    "password": "StrongPassword123!",
    "role": "organiser"
  }'
```

#### 2. Authenticate & Obtain Tokens
```bash
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "priya@studioevents.com",
    "password": "StrongPassword123!"
  }'
```
Response:
```json
{
  "success": true,
  "message": "Authentication successful",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600
  }
}
```

---

### B. Event Management

#### 1. Create an Event
```bash
curl -X POST http://localhost/api/v1/events \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Global Tech Summit 2026",
    "description": "Annual technology convention & keynote showcase",
    "access_type": "public"
  }'
```
Response:
```json
{
  "success": true,
  "message": "Event created successfully",
  "data": {
    "id": "e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3",
    "organiser_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
    "name": "Global Tech Summit 2026",
    "slug": "global-tech-summit-2026",
    "access_type": "public",
    "status": "active"
  }
}
```

---

### C. Photo Ingestion & Processing

#### 1. Bulk Upload Photographs
```bash
curl -X POST http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/bulk \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "files=@stage_speaker.jpg" \
  -F "files=@audience_hall.jpg" \
  -F "is_public=false"
```
Response:
```json
{
  "success": true,
  "message": "Uploaded 2 photos successfully (0 failed)",
  "data": {
    "total_uploaded": 2,
    "successful": 2,
    "failed": 0,
    "photos": [
      {
        "id": "f1111111-2222-3333-4444-555555555555",
        "event_id": "e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3",
        "original_filename": "stage_speaker.jpg",
        "processing_status": "pending",
        "is_public": false
      }
    ],
    "errors": []
  }
}
```

#### 2. Check Photo Processing Status
```bash
curl http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/processing-status \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```
Response:
```json
{
  "success": true,
  "data": {
    "event_id": "e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3",
    "total": 500,
    "pending": 0,
    "processing": 0,
    "completed": 500,
    "failed": 0
  }
}
```

#### 3. Update Photo Visibility (Make Public / Private)
```bash
# Make private photo public
curl -X PATCH http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/f1111111-2222-3333-4444-555555555555 \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"is_public": true}'
```

#### 4. Remove / Delete a Photo
```bash
curl -X DELETE http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/f1111111-2222-3333-4444-555555555555 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

#### 5. Batch Update Visibility for Multiple Photos
```bash
curl -X POST http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/batch-update \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "photo_ids": [
      "f1111111-2222-3333-4444-555555555555",
      "f2222222-3333-4444-5555-666666666666"
    ],
    "is_public": true
  }'
```

#### 6. Batch Delete Multiple Photos
```bash
curl -X POST http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/batch-delete \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "photo_ids": [
      "f1111111-2222-3333-4444-555555555555",
      "f2222222-3333-4444-5555-666666666666"
    ]
  }'
```

---

### D. Attendee Face Recognition Search

#### 1. Record Consent & Initialize Search Session
```bash
curl -X POST http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/search/consent \
  -H "Content-Type: application/json" \
  -d '{
    "consent_given": true,
    "purpose": "facial_recognition_search"
  }'
```
Response:
```json
{
  "success": true,
  "message": "Consent recorded and search session initialized",
  "data": {
    "session_id": "c1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
    "event_id": "e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3",
    "consent_purpose": "facial_recognition_search",
    "status": "active",
    "expires_at": "2026-11-12T20:45:00Z"
  }
}
```

#### 2. Upload Selfie & Retrieve Matching Photos
```bash
curl -X POST http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/search \
  -F "selfie=@attendee_selfie.jpg" \
  -F "session_id=c1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c"
```
Response:
```json
{
  "success": true,
  "message": "Found 4 matching photo(s) and 12 public photo(s)",
  "data": {
    "session_id": "c1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
    "event_id": "e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3",
    "faces_detected_in_selfie": 1,
    "matched_count": 4,
    "public_count": 12,
    "total_returned": 16,
    "items": [
      {
        "photo": {
          "id": "f1111111-2222-3333-4444-555555555555",
          "event_id": "e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3",
          "original_filename": "audience_hall.jpg",
          "is_public": false,
          "face_count": 3
        },
        "match_type": "face_match",
        "similarity_score": 0.6842,
        "detection_confidence": 0.9812
      },
      {
        "photo": {
          "id": "f2222222-3333-4444-5555-666666666666",
          "original_filename": "stage_keynote.jpg",
          "is_public": true,
          "face_count": 1
        },
        "match_type": "public",
        "similarity_score": null,
        "detection_confidence": null
      }
    ]
  }
}
```

---

### E. Secure Image Delivery

#### 1. View Private Photo (with Search Session)
```bash
curl http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/f1111111-2222-3333-4444-555555555555/view?session_id=c1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c \
  --output matched_photo.jpg
```

#### 2. Get Thumbnail
```bash
curl http://localhost/api/v1/events/e816a1b2-c3d4-4e5f-a6b7-c8d9e0f1a2b3/photos/f1111111-2222-3333-4444-555555555555/thumbnail?session_id=c1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c \
  --output thumb.webp
```

---

## 7. Performance Benchmarks

Measured results on standard CPU hardware:

- **YuNet Face Detection & SFace Extraction**: `96.88 ms` per image
- **Single Worker Ingestion Throughput**: `10.32 images/sec` (~620 images/min)
- **1,000 Photographs Processing Time**: **~1.6 minutes** (single worker) / **~0.8 minutes** (two workers)
- **Vector Cosine Similarity Search**: `0.036 ms` over 3,000 128-d faces (**27,800+ searches/sec**)
- **Process Memory Peak**: `202.7 MB` (easily fits in 2-vCPU / 4GB RAM VPS budget)

---

## 8. Privacy & Data Protection Compliance

Designed with legal compliance in mind (including India's **Digital Personal Data Protection Act 2023**):
- **Explicit Consent**: Attenders explicitly authorise biometric face indexing solely for personal photo retrieval.
- **Right to Withdraw**: Attendees can revoke search sessions at any time via `DELETE /events/{event_id}/search/{session_id}`.
- **Temporary Data Erasure**: Selfie image binaries are processed in-memory and wiped immediately upon generating the vector.
- **Audit Trails**: Security actions (search, consent granted/withdrawn, photo deletion) are recorded in `audit_logs` without storing biometric embeddings.
- **Data Retention Purge**: Run `python3 scripts/cleanup_expired_data.py` periodically (e.g. daily cron) to delete biometric search sessions exceeding policy retention limits.

# cinigama-backend
