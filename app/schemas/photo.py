import datetime
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PhotoFaceRead(BaseModel):
    id: uuid.UUID
    bounding_box: Dict[str, Any]
    detection_confidence: float
    landmarks: Optional[Dict[str, Any]] = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class PhotoRead(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    uploaded_by: Optional[uuid.UUID]
    original_filename: str
    mime_type: str
    file_size: int
    width: Optional[int]
    height: Optional[int]
    is_public: bool
    processing_status: str
    processing_error: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    face_count: Optional[int] = 0
    thumbnail_url: Optional[str] = None
    url: Optional[str] = None
    event_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PhotoUpdate(BaseModel):
    is_public: Optional[bool] = None


class PhotoBatchUpdate(BaseModel):
    photo_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)
    is_public: bool


class PhotoBatchDelete(BaseModel):
    photo_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)


class PhotoBatchResult(BaseModel):
    affected: int
    photo_ids: List[uuid.UUID]


class PhotoBulkUploadResult(BaseModel):
    total_uploaded: int
    successful: int
    failed: int
    photos: List[PhotoRead]
    errors: List[Dict[str, str]]


class PhotoProcessingStatusResponse(BaseModel):
    event_id: uuid.UUID
    total: int
    pending: int
    processing: int
    completed: int
    failed: int

