import json
import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings

# Dedicated logger that writes ONLY to the activity log file
activity_logger = logging.getLogger("activity")
activity_logger.setLevel(logging.INFO)
activity_logger.propagate = False  # Don't send to root/app logger

# Set up file handler: {STORAGE_BASE_PATH}/logs/activity.log
_log_dir = os.path.join(settings.storage_base_path, "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_path = os.path.join(_log_dir, "activity.log")

_handler = RotatingFileHandler(
    _log_path,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_handler.setLevel(logging.INFO)
# Raw formatter — we write pre-formatted JSON, so no extra formatting needed
_handler.setFormatter(logging.Formatter("%(message)s"))
activity_logger.addHandler(_handler)

# Paths to skip logging
_SKIP_PREFIXES = ("/_next", "/favicon")


class ActivityLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(_SKIP_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)

        # Build query string portion
        full_path = path
        if request.url.query:
            full_path = f"{path}?{request.url.query}"

        entry = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "method": request.method,
            "path": full_path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
        }
        activity_logger.info(json.dumps(entry))

        return response
