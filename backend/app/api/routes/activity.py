import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.middleware.activity_logger import activity_logger

router = APIRouter()


class ActivityEvent(BaseModel):
    action: str
    page: str | None = None
    details: dict | None = None


@router.post("/track")
async def track_activity(event: ActivityEvent, request: Request):
    """Log a client-side user interaction event."""
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "method": "CLIENT",
        "path": event.page or "",
        "status": 0,
        "duration_ms": 0,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", ""),
        "action": event.action,
        "details": event.details,
    }
    activity_logger.info(json.dumps(entry))
    return {"ok": True}
