from typing import Optional
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PhotoFilterParams(PaginationParams):
    status: Optional[str] = Field(None, pattern="^(pending|processing|completed|failed)$")
    is_public: Optional[bool] = None

