# Cinigama Event Photography & AI Facial Recognition — API Documentation

Comprehensive API documentation for the **Cinigama Event Photography & AI Facial Recognition Platform**.

---

## 1. Overview & System Information

- **Base URL (Production)**: `https://api.cinigama.in`
- **API Prefix**: `/api/v1` (also aliased at `/v1`)
- **Interactive Swagger UI**: `https://api.cinigama.in/docs`
- **ReDoc Documentation**: `https://api.cinigama.in/redoc`
- **Supported Formats**: JSON (`application/json`), Multipart Form Data (`multipart/form-data`)

---

## 2. Authentication & Authorization

Protected endpoints require a Bearer token in the `Authorization` header:

```http
Authorization: Bearer <YOUR_JWT_ACCESS_TOKEN>
```

### Roles:
- **`organiser`**: Full control over events created by the user, photo uploads, batch jobs, and restricted faces.
- **`admin`**: System-wide access across all events and users.
- **`attendee`**: Public read access or face search via temporary biometric consent sessions.

---

## 3. Standard Response Envelopes

### 3.1 Standard Success Envelope
```json
{
  "success": true,
  "message": "Operation successful",
  "data": { ... }
}
```

### 3.2 Paginated Success Envelope
```json
{
  "success": true,
  "items": [ ... ],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "has_next": true,
  "has_prev": false
}
```

### 3.3 Error Envelope
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Description of error",
    "details": null
  }
}
```

---

## 4. API Endpoints Reference

---

### Module 1: System & Health

#### `GET /api/v1/health` (also `GET /health` and `GET /`)
Check application status, OpenCV AI model verification, and disk space.

- **Auth**: None (Public)
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "models_ready": true,
  "disk_storage": {
    "total_bytes": 104857600000,
    "free_bytes": 85899345920,
    "percent_free": 81.9
  }
}
```

---

### Module 2: Authentication (`/api/v1/auth`)

#### 1. Register User
`POST /api/v1/auth/register`
- **Auth**: None
- **Body (`application/json`)**:
```json
{
  "email": "organiser@cinigama.in",
  "full_name": "Udaya Kumar",
  "password": "StrongPassword123!",
  "role": "organiser"
}
```
- **Response `201 Created`**:
```json
{
  "success": true,
  "message": "User registered successfully",
  "data": {
    "id": "e4b2d308-3693-455b-bf49-5fbe602f307b",
    "email": "organiser@cinigama.in",
    "full_name": "Udaya Kumar",
    "role": "organiser",
    "is_active": true,
    "created_at": "2026-11-24T10:00:00Z",
    "updated_at": "2026-11-24T10:00:00Z"
  }
}
```

#### 2. User Login
`POST /api/v1/auth/login`
- **Auth**: None
- **Body (`application/json`)**:
```json
{
  "email": "organiser@cinigama.in",
  "password": "StrongPassword123!"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "message": "Authentication successful",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 1800
  }
}
```

#### 3. Refresh Access Token
`POST /api/v1/auth/refresh`
- **Auth**: None
- **Body (`application/json`)**:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```
- **Response `200 OK`**: Returns new `access_token` and rotated `refresh_token`.

#### 4. Get Current Profile
`GET /api/v1/auth/me`
- **Auth**: Bearer Token
- **Response `200 OK`**: Returns `UserRead` object.

#### 5. User Logout
`POST /api/v1/auth/logout`
- **Auth**: Bearer Token
- **Response `200 OK`**: Revokes session.

---

### Module 3: Events Management (`/api/v1/events`)

#### 1. Create Event
`POST /api/v1/events`
- **Auth**: Bearer Token (`organiser` / `admin`)
- **Body (`application/json`)**:
```json
{
  "name": "Grand Wedding Reception",
  "slug": "52630",
  "description": "Evening reception photographs and moments",
  "event_date": "2026-12-25T18:00:00Z",
  "access_type": "private",
  "access_code": "5263"
}
```
*Note: `slug` can be a custom string, number (e.g. `52630`), or omitted to auto-generate.*

#### 2. List Events
`GET /api/v1/events`
- **Auth**: Optional (Organizers see all their events; public sees active public events)
- **Query Params**:
  - `page`: int (default `1`)
  - `page_size`: int (default `20`, max `100`)
- **Response `200 OK`**: Returns `PaginatedResponse[EventRead]`.

#### 3. Get Event by ID or Slug
`GET /api/v1/events/{event_id}`
- **Path Param**: `event_id` can be Event UUID, short slug, or numeric ID (e.g. `52630`).
- **Response `200 OK`**: Returns `EventRead` with photo counts.

#### 4. Get Event Details With Photos (Paginated)
`GET /api/v1/events/{event_id}/details`
- **Query Params**:
  - `page`: int (default `1`)
  - `page_size`: int (default `20`, max `100`)
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "event": {
      "id": "cde56382-59d2-42b5-88a0-8dc92f91578e",
      "name": "Grand Wedding Reception",
      "slug": "52630",
      "status": "active"
    },
    "total_photos": 450,
    "public_photos": 80,
    "photos": [ ... ],
    "page": 1,
    "page_size": 20,
    "total_pages": 4,
    "has_next": true,
    "has_prev": false
  }
}
```

#### 5. Update Event
`PATCH /api/v1/events/{event_id}`
- **Auth**: Bearer Token
- **Body (`application/json`)**:
```json
{
  "name": "Grand Wedding Reception 2026",
  "slug": "grand-reception-52630",
  "description": "Updated event notes",
  "access_type": "code_protected",
  "access_code": "Reception2026",
  "status": "active"
}
```
*All fields optional. Updating `slug` automatically verifies uniqueness.*

#### 6. Delete Event
`DELETE /api/v1/events/{event_id}`
- **Auth**: Bearer Token
- **Response `200 OK`**: Deletes event, database records, thumbnails, and files from storage.

#### 7. Event Statistics
`GET /api/v1/events/{event_id}/stats`
- **Auth**: Bearer Token
- **Response `200 OK`**: Returns `total_photos`, `pending_photos`, `processing_photos`, `completed_photos`, `failed_photos`, `public_photos`, `private_photos`, and `total_faces_indexed`.

---

### Module 4: Event Photos Management (`/api/v1/events/{event_id}/photos`)

#### 1. Upload Single Photo
`POST /api/v1/events/{event_id}/photos`
- **Auth**: Bearer Token
- **Content-Type**: `multipart/form-data`
- **Form Data**:
  - `file`: Image file (JPEG, PNG, WebP)
  - `is_public`: boolean (`true` / `false`, default `false`)
- **Note**: Applies white logo watermark in top-right corner automatically.

#### 2. Bulk Upload Photos
`POST /api/v1/events/{event_id}/photos/bulk`
- **Auth**: Bearer Token
- **Content-Type**: `multipart/form-data`
- **Form Data**:
  - `files`: Array of image files
  - `is_public`: boolean (default `false`)
- **Response `201 Created`**: Returns counts of successful and failed uploads.

#### 3. List Event Photos
`GET /api/v1/events/{event_id}/photos`
- **Query Params**:
  - `page`: int (default `1`)
  - `page_size`: int (default `20`, max `100`)
  - `status`: string (`pending`, `processing`, `completed`, `failed`)
  - `is_public`: boolean (`true` / `false`)
  - `search`: string (filename filter)
  - `sort_by`: string (`created_at`, `file_size`, `original_filename`, `processing_status`)
  - `sort_order`: string (`asc`, `desc`, default `desc`)
- **Response `200 OK`**: `PaginatedResponse[PhotoRead]`.

#### 4. Check Background Processing Status
`GET /api/v1/events/{event_id}/photos/processing-status`
- **Auth**: Bearer Token
- **Response `200 OK`**: Returns progress of facial recognition ingestion queue.

#### 5. Get Photo by ID
`GET /api/v1/events/{event_id}/photos/{photo_id}`
- **Response `200 OK`**: Returns metadata, thumbnail URL, and preview URL.

#### 6. Update Photo Visibility
`PATCH /api/v1/events/{event_id}/photos/{photo_id}`
- **Auth**: Bearer Token
- **Body**: `{"is_public": true}`

#### 7. Delete Single Photo
`DELETE /api/v1/events/{event_id}/photos/{photo_id}`
- **Auth**: Bearer Token
- **Response `200 OK`**: Deletes image file, thumbnail, and face embeddings.

#### 8. Batch Update Photos
`POST /api/v1/events/{event_id}/photos/batch-update`
- **Auth**: Bearer Token
- **Body**:
```json
{
  "photo_ids": ["uuid-1", "uuid-2"],
  "is_public": true
}
```

#### 9. Batch Delete Photos
`POST /api/v1/events/{event_id}/photos/batch-delete`
- **Auth**: Bearer Token
- **Body**:
```json
{
  "photo_ids": ["uuid-1", "uuid-2"]
}
```

---

### Module 5: Global Photos Management (`/api/v1/photos`)

Allows viewing and managing photos directly across all events without needing `/events/{event_id}` in the URL.

#### 1. View & Manage All Photos with Pagination
`GET /api/v1/photos`
- **Auth**: Bearer Token
- **Query Params**:
  - `page`: int (default `1`)
  - `page_size`: int (default `20`, max `100`)
  - `event_id`: Optional string (filter by event ID or slug)
  - `status`: Optional string (`pending`, `processing`, `completed`, `failed`)
  - `is_public`: Optional boolean
  - `search`: Optional string (search filename)
  - `sort_by`: string (`created_at`, `file_size`, `original_filename`, `processing_status`)
  - `sort_order`: string (`asc` / `desc`)
- **Response `200 OK`**: `PaginatedResponse[PhotoRead]`. Each photo includes `event_name` and URLs.

#### 2. Get Photo Metadata Direct
`GET /api/v1/photos/{photo_id}`
- **Auth**: Optional if photo is public; Bearer Token if private.

#### 3. Update Photo Visibility Direct
`PATCH /api/v1/photos/{photo_id}`
- **Auth**: Bearer Token
- **Body**: `{"is_public": true}`

#### 4. Delete Photo Direct
`DELETE /api/v1/photos/{photo_id}`
- **Auth**: Bearer Token

#### 5. Cross-Event Batch Update
`POST /api/v1/photos/batch-update`
- **Auth**: Bearer Token
- **Body**: `{"photo_ids": ["..."], "is_public": true}`

#### 6. Cross-Event Batch Delete
`POST /api/v1/photos/batch-delete`
- **Auth**: Bearer Token
- **Body**: `{"photo_ids": ["..."]}`

---

### Module 6: Facial Recognition Search (`/api/v1/events/{event_id}/search`)

Fully compliant with India's **Digital Personal Data Protection (DPDP) Act 2023**. Temporary selfie biometric data is processed in memory and instantly wiped.

#### 1. Biometric Consent & Session Creation
`POST /api/v1/events/{event_id}/search/consent`
- **Auth**: None
- **Body (`application/json`)**:
```json
{
  "consent_given": true,
  "purpose": "facial_recognition_search"
}
```
- **Response `201 Created`**:
```json
{
  "success": true,
  "message": "Consent recorded and search session initialized",
  "data": {
    "session_id": "76ec481e-9df8-433b-81d3-3532c525fcf9",
    "event_id": "cde56382-59d2-42b5-88a0-8dc92f91578e",
    "consent_timestamp": "2026-11-24T12:00:00Z",
    "consent_purpose": "facial_recognition_search",
    "status": "active",
    "expires_at": "2026-11-24T12:30:00Z"
  }
}
```

#### 2. Search Photos by Selfie
`POST /api/v1/events/{event_id}/search`
- **Auth**: Rate-limited (15 req/min per IP)
- **Content-Type**: `multipart/form-data`
- **Form Data**:
  - `selfie`: Image file (attendee's selfie with 1 clear face)
  - `session_id`: UUID (active session from consent endpoint)
  - `threshold`: Optional float (defaults to calibrated `0.50` / 50% match)
  - `include_public`: Optional boolean (default `false`)
- **Behavior**:
  - Enforces minimum $\ge 50\%$ cosine similarity matching.
  - Rejects if selfie matches any Restricted Face for the event (`403 Forbidden`).
  - Does NOT return unmatched public photos unless `include_public=true`.
- **Response `200 OK`**:
```json
{
  "success": true,
  "message": "Found 3 matching photo(s)",
  "data": {
    "session_id": "76ec481e-9df8-433b-81d3-3532c525fcf9",
    "event_id": "cde56382-59d2-42b5-88a0-8dc92f91578e",
    "faces_detected_in_selfie": 1,
    "matched_count": 3,
    "public_count": 0,
    "total_returned": 3,
    "items": [
      {
        "photo": {
          "id": "e98e4d3a-...",
          "original_filename": "DSC_0492.jpg",
          "thumbnail_url": "/api/v1/events/52630/photos/.../thumbnail",
          "url": "/api/v1/events/52630/photos/.../view"
        },
        "match_type": "face_match",
        "similarity_score": 0.8624,
        "detection_confidence": 0.9912
      }
    ]
  }
}
```

#### 3. Verify Session Status
`GET /api/v1/events/{event_id}/search/{session_id}`
- **Response `200 OK`**: Confirms session is still active.

#### 4. Revoke Biometric Consent
`DELETE /api/v1/events/{event_id}/search/{session_id}`
- **Response `200 OK`**: Revokes session immediately. Future search requests with this session will fail.

---

### Module 7: Image Delivery (`/api/v1/events/{event_id}/photos/{photo_id}`)

#### 1. Get Thumbnail
`GET /api/v1/events/{event_id}/photos/{photo_id}/thumbnail`
- **Query Params**:
  - `session_id`: Optional UUID (required if photo is private)
- **Response**: Streams optimized WebP image (or 307 Redirect to signed Cloudflare R2 URL).

#### 2. View Photo Inline
`GET /api/v1/events/{event_id}/photos/{photo_id}/view`
- **Query Params**:
  - `session_id`: Optional UUID (for private photos)
- **Response**: Streams original resolution image (`image/jpeg` or `image/png`).

#### 3. Download Photo Attachment
`GET /api/v1/events/{event_id}/photos/{photo_id}/download`
- **Response**: Sets `Content-Disposition: attachment; filename="..."` for file saving.

---

### Module 8: Restricted Faces (`/api/v1/events/{event_id}/restricted-faces`)

Restricts specific individuals from uploading their selfie to get photos, while allowing those photos to remain visible when other attendees search.

#### 1. Restrict Face by Photo Upload
`POST /api/v1/events/{event_id}/restricted-faces`
- **Auth**: Bearer Token
- **Content-Type**: `multipart/form-data`
- **Form Data**:
  - `photo`: Image file containing the face to restrict
  - `name`: Optional string (e.g. "John Doe")
  - `reason`: Optional string (e.g. "Selfie search opt-out")
- **Response `201 Created`**: Returns `RestrictedFaceRead`.

#### 2. Restrict Face by PhotoFace ID
`POST /api/v1/events/{event_id}/restricted-faces/from-face/{face_id}`
- **Auth**: Bearer Token
- **Form Data**:
  - `name`: Optional string
  - `reason`: Optional string
- **Response `201 Created`**: Restricts using an already indexed face from an event photograph.

#### 3. List Restricted Faces
`GET /api/v1/events/{event_id}/restricted-faces`
- **Auth**: Bearer Token
- **Query Params**: `skip` (default 0), `limit` (default 50)
- **Response `200 OK`**: List of restricted faces with preview thumbnails.

#### 4. Remove Face Restriction
`DELETE /api/v1/events/{event_id}/restricted-faces/{restricted_face_id}`
- **Auth**: Bearer Token
- **Response `200 OK`**: Removes restriction, allowing selfie searches again.

#### 5. Get Restricted Face Thumbnail
`GET /api/v1/events/{event_id}/restricted-faces/{restricted_face_id}/thumbnail`
- **Response**: Streams cropped face preview thumbnail.

---

## 5. Error Codes Quick Reference

| Status Code | Error Code | Description |
| :--- | :--- | :--- |
| `400 Bad Request` | `INVALID_IMAGE` | Corrupted file, invalid EXIF, or unsupported MIME type |
| `401 Unauthorized` | `AUTHENTICATION_FAILED` | Missing, invalid, or expired JWT token |
| `403 Forbidden` | `PERMISSION_DENIED` | Not authorized for this event/photo resource |
| `403 Forbidden` | `CONSENT_REQUIRED` | Attendee attempted face search without valid consent session |
| `403 Forbidden` | `FACE_SEARCH_RESTRICTED` | Face is blocked from searching via Restricted Faces list |
| `404 Not Found` | `RESOURCE_NOT_FOUND` | Event, photo, session, or face not found |
| `409 Conflict` | `RESOURCE_CONFLICT` | Slug or email already in use |
| `422 Unprocessable`| `FACE_DETECTION_ERROR` | No face or multiple faces detected in selfie upload |
| `429 Too Many Requests` | `RATE_LIMIT_EXCEEDED` | Exceeded 15 face searches per minute |
| `500 Internal Error` | `INTERNAL_SERVER_ERROR` | Server exception (logged in backend logs) |
