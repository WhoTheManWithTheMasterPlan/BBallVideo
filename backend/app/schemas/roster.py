import uuid
from datetime import datetime

from pydantic import BaseModel


class RosterPlayerCreate(BaseModel):
    name: str
    jersey_number: int
    height_inches: int | None = None
    position: str | None = None


class RosterPlayerResponse(BaseModel):
    id: uuid.UUID
    roster_id: uuid.UUID
    name: str
    jersey_number: int
    height_inches: int | None
    position: str | None
    photo_file_key: str | None
    has_reid_embedding: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class RosterCreate(BaseModel):
    team_name: str
    season: str | None = None
    jersey_color_primary: str | None = None
    jersey_color_secondary: str | None = None
    user_id: str
    players: list[RosterPlayerCreate] = []


class RosterResponse(BaseModel):
    id: uuid.UUID
    team_name: str
    season: str | None
    jersey_color_primary: str | None
    jersey_color_secondary: str | None
    players: list[RosterPlayerResponse]
    created_at: datetime

    model_config = {"from_attributes": True}
