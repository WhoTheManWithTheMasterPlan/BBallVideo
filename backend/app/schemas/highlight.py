import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HighlightResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    event_type: str
    start_time: float
    end_time: float
    file_key: str | None
    thumbnail_file_key: str | None
    confidence: float | None
    created_at: datetime
    review_status: str
    corrected_event_type: str | None
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class HighlightReviewUpdate(BaseModel):
    review_status: Literal["confirmed", "rejected"]
    corrected_event_type: str | None = None
