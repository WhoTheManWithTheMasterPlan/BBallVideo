import uuid

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.game import Game
from app.services.video.storage import save_upload, check_storage_limit
from app.workers.tasks import process_video

router = APIRouter()


@router.post("/")
async def upload_video(
    game_id: str = Form(...),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a video file directly to local storage."""
    # Validate format
    ext = video.filename.rsplit(".", 1)[-1].lower() if video.filename and "." in video.filename else ""
    if f".{ext}" not in settings.supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")

    # Verify game exists
    game = await db.get(Game, uuid.UUID(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Read file data
    data = await video.read()

    # Check file size
    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.max_video_size_mb:
        raise HTTPException(status_code=400, detail=f"File too large: {size_mb:.0f}MB (max {settings.max_video_size_mb}MB)")

    # Check storage limit
    if not check_storage_limit(len(data)):
        raise HTTPException(status_code=507, detail="Storage limit reached (1TB)")

    # Save to local storage
    file_key = f"raw/{game_id}/{uuid.uuid4()}.{ext}"
    save_upload(file_key, data)

    # Link file to game record
    game.video_file_key = file_key
    game.status = "uploaded"
    await db.commit()

    return {"file_key": file_key, "size_mb": round(size_mb, 1)}


@router.post("/{game_id}/process")
async def trigger_processing(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Trigger video processing pipeline for an uploaded game."""
    # Verify game exists and has a video
    game = await db.get(Game, uuid.UUID(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not game.video_file_key:
        raise HTTPException(status_code=400, detail="No video uploaded for this game")

    game.status = "processing"
    await db.commit()

    task = process_video.delay(game_id)
    return {"task_id": task.id, "status": "queued"}
