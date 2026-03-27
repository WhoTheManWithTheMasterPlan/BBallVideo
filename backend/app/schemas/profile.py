import uuid
from datetime import datetime

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str
    user_id: str


class ProfilePhotoResponse(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    file_key: str
    is_primary: bool
    has_embedding: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    photos: list[ProfilePhotoResponse]
    created_at: datetime

    model_config = {"from_attributes": True}
