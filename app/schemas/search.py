import datetime
import uuid
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.photo import PhotoRead


class ConsentCreate(BaseModel):
    consent_given: bool = Field(..., description="Explicit consent from attendee to process facial biometric data solely for photograph matching")
    purpose: str = Field(
        default="facial_recognition_search",
        description="Specified purpose under privacy policies and the Digital Personal Data Protection Act 2023",
    )


class SearchSessionRead(BaseModel):
    session_id: uuid.UUID
    event_id: uuid.UUID
    consent_timestamp: datetime.datetime
    consent_purpose: str
    status: str
    expires_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class MatchedPhotoItem(BaseModel):
    photo: PhotoRead
    match_type: str  # "face_match" or "public"
    similarity_score: Optional[float] = None
    detection_confidence: Optional[float] = None


class FaceSearchResponse(BaseModel):
    session_id: uuid.UUID
    event_id: uuid.UUID
    faces_detected_in_selfie: int
    matched_count: int
    public_count: int
    total_returned: int
    items: List[MatchedPhotoItem]

