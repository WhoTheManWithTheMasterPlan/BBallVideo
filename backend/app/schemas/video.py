import uuid
from datetime import datetime

from pydantic import BaseModel


class VideoCreate(BaseModel):
    title: str
    opponent: str | None = None
    game_date: datetime | None = None
    user_id: str


class VideoResponse(BaseModel):
    id: uuid.UUID
    title: str
    opponent: str | None
    game_date: datetime | None
    file_key: str | None
    duration_seconds: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
