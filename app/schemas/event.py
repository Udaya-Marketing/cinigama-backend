import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(from_attributes=True)


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

