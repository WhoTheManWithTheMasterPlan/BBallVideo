import uuid
from datetime import datetime

from pydantic import BaseModel


class TeamPhotoResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    file_key: str
    is_primary: bool
    has_embedding: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    name: str
    jersey_number: int | None = None
    color_primary: str | None = None
    color_secondary: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    jersey_number: int | None = None
    color_primary: str | None = None
    color_secondary: str | None = None


class TeamResponse(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    jersey_number: int | None
    color_primary: str | None
    color_secondary: str | None
    photos: list[TeamPhotoResponse]
    created_at: datetime

    model_config = {"from_attributes": True}
