import uuid
from datetime import datetime

from pydantic import BaseModel


class StatEventResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    event_type: str
    timestamp: float
    player_id: uuid.UUID | None
    team: str | None
    court_x: float | None
    court_y: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
