import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="organiser", pattern="^(admin|organiser|attendee)$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(UserBase):
    id: uuid.UUID
    role: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=128)

