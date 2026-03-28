import uuid
from datetime import datetime

from pydantic import BaseModel


class JobCreate(BaseModel):
    video_id: uuid.UUID
    profile_id: uuid.UUID
    team_id: uuid.UUID | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    profile_id: uuid.UUID
    team_id: uuid.UUID | None
    status: str
    celery_task_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    events_count: int | None
    highlights_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
