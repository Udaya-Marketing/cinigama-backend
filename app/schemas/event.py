import datetime
import uuid
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.photo import PhotoRead


class EventBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    event_date: Optional[datetime.datetime] = None
    access_type: str = Field(default="private", pattern="^(public|private|code_protected)$")


class EventCreate(EventBase):
    slug: Optional[str] = Field(None, min_length=2, max_length=255)
    access_code: Optional[str] = Field(None, min_length=4, max_length=64)


class EventUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    slug: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    event_date: Optional[datetime.datetime] = None
    access_type: Optional[str] = Field(None, pattern="^(public|private|code_protected)$")
    access_code: Optional[str] = Field(None, min_length=4, max_length=64)
    status: Optional[str] = Field(None, pattern="^(draft|active|archived)$")


class EventRead(EventBase):
    id: uuid.UUID
    organiser_id: uuid.UUID
    slug: str
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    total_photos: Optional[int] = 0
    public_photos: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class EventDetailsWithPhotos(BaseModel):
    event: EventRead
    total_photos: int
    public_photos: int
    photos: List[PhotoRead]
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class EventStats(BaseModel):
    event_id: uuid.UUID
    total_photos: int
    pending_photos: int
    processing_photos: int
    completed_photos: int
    failed_photos: int
    public_photos: int
    private_photos: int
    total_faces_indexed: int


class EventAccessVerification(BaseModel):
    access_code: Optional[str] = None

