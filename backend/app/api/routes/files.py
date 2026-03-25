from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.video.storage import get_file_path, file_exists

router = APIRouter()


@router.get("/{file_key:path}")
async def serve_file(file_key: str):
    """Serve a file from local storage (videos, clips, thumbnails)."""
    if not file_exists(file_key):
        raise HTTPException(status_code=404, detail="File not found")

    path = get_file_path(file_key)
    suffix = path.suffix.lower()

    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    return FileResponse(
        path=str(path),
        media_type=media_types.get(suffix, "application/octet-stream"),
    )
