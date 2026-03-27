import uuid
from datetime import datetime

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str
    user_id: str
    jersey_number: int | None = None
    team_color_primary: str | None = None
    team_color_secondary: str | None = None


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
    jersey_number: int | None
    team_color_primary: str | None
    team_color_secondary: str | None
    photos: list[ProfilePhotoResponse]
    created_at: datetime

    model_config = {"from_attributes": True}
