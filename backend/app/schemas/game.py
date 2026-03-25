import uuid
from datetime import datetime

from pydantic import BaseModel


class GameCreate(BaseModel):
    title: str
    home_team: str
    away_team: str
    game_date: datetime
    user_id: str
    home_roster_id: uuid.UUID | None = None
    away_roster_id: uuid.UUID | None = None


class GameResponse(BaseModel):
    id: uuid.UUID
    title: str
    home_team: str
    away_team: str
    game_date: datetime
    status: str
    duration_seconds: int | None
    video_file_key: str | None
    home_roster_id: uuid.UUID | None
    away_roster_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
