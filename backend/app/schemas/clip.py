import uuid
from datetime import datetime

from pydantic import BaseModel


class ClipResponse(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    event_type: str
    start_time: float
    end_time: float
    file_key: str | None
    thumbnail_file_key: str | None
    player_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
