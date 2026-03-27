import uuid
from datetime import datetime

from pydantic import BaseModel


class StatResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    event_type: str
    timestamp: float
    court_x: float | None
    court_y: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
