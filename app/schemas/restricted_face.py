import datetime
import uuid
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RestrictedFaceRead(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    name: Optional[str] = None
    reason: Optional[str] = None
    thumbnail_url: Optional[str] = None
    detection_confidence: Optional[float] = None
    created_at: datetime.datetime
    created_by: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


class RestrictedFaceListResponse(BaseModel):
    items: List[RestrictedFaceRead]
    total: int

