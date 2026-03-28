import uuid
from datetime import datetime

from pydantic import BaseModel


class TeamCreate(BaseModel):
    name: str
    color_primary: str | None = None
    color_secondary: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    color_primary: str | None = None
    color_secondary: str | None = None


class TeamResponse(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    color_primary: str | None
    color_secondary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
