import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.job import ProcessingJob
from app.models.profile import Profile
from app.models.video import Video
from app.schemas.job import JobResponse
from app.schemas.video import VideoCreate, VideoResponse
from app.services.video.storage import check_storage_limit, get_file_path, save_upload
from app.workers.celery_app import celery_app

# In-memory tracker for active chunked uploads
# In production, use Redis — but for single-server this is fine
_active_uploads: dict[str, dict] = {}

router = APIRouter()


@router.post("/", response_model=VideoResponse)
@router.post("", response_model=VideoResponse)
async def create_video(data: VideoCreate, db: AsyncSession = Depends(get_db)):
    # Strip timezone info — DB column is timezone-naive
    game_date = data.game_date.replace(tzinfo=None) if data.game_date else None
    video = Video(
        user_id=data.user_id,
        title=data.title,
        opponent=data.opponent,
        game_date=game_date,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video


@router.get("/", response_model=list[VideoResponse])
@router.get("", response_model=list[VideoResponse])
async def list_videos(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video).where(Video.user_id == user_id).order_by(Video.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.post("/{video_id}/upload")
async def upload_video_file(
    video_id: uuid.UUID,
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(Video, video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    ext = video.filename.rsplit(".", 1)[-1].lower() if video.filename and "." in video.filename else ""
    if f".{ext}" not in settings.supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")

    data = await video.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.max_video_size_mb:
        raise HTTPException(status_code=400, detail=f"File too large: {size_mb:.0f}MB (max {settings.max_video_size_mb}MB)")
    if not check_storage_limit(len(data)):
        raise HTTPException(status_code=507, detail="Storage limit reached")

    file_key = f"raw/{video_id}/{uuid.uuid4()}.{ext}"
    save_upload(file_key, data)

    record.file_key = file_key
    await db.commit()

    return {"file_key": file_key, "size_mb": round(size_mb, 1)}


# --- Chunked upload (for files >100MB behind Cloudflare) ---


@router.post("/{video_id}/chunked-upload/init")
async def init_chunked_upload(
    video_id: uuid.UUID,
    filename: str = Form(...),
    total_chunks: int = Form(...),
    total_size: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Initialize a chunked upload session."""
    record = await db.get(Video, video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if f".{ext}" not in settings.supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")

    size_mb = total_size / (1024 * 1024)
    if size_mb > settings.max_video_size_mb:
        raise HTTPException(status_code=400, detail=f"File too large: {size_mb:.0f}MB (max {settings.max_video_size_mb}MB)")
    if not check_storage_limit(total_size):
        raise HTTPException(status_code=507, detail="Storage limit reached")

    upload_id = str(uuid.uuid4())
    temp_dir = Path(tempfile.gettempdir()) / "bballvideo_chunks" / upload_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    _active_uploads[upload_id] = {
        "video_id": str(video_id),
        "filename": filename,
        "ext": ext,
        "total_chunks": total_chunks,
        "total_size": total_size,
        "received_chunks": set(),
        "temp_dir": str(temp_dir),
    }

    return {"upload_id": upload_id, "total_chunks": total_chunks}


@router.post("/{video_id}/chunked-upload/chunk")
async def upload_chunk(
    video_id: uuid.UUID,
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    """Upload a single chunk. Each chunk must be <100MB for Cloudflare."""
    if upload_id not in _active_uploads:
        raise HTTPException(status_code=404, detail="Upload session not found")

    session = _active_uploads[upload_id]
    if session["video_id"] != str(video_id):
        raise HTTPException(status_code=400, detail="Video ID mismatch")
    if chunk_index < 0 or chunk_index >= session["total_chunks"]:
        raise HTTPException(status_code=400, detail=f"Invalid chunk index: {chunk_index}")

    data = await chunk.read()
    chunk_path = Path(session["temp_dir"]) / f"chunk_{chunk_index:05d}"
    chunk_path.write_bytes(data)

    session["received_chunks"].add(chunk_index)

    return {
        "chunk_index": chunk_index,
        "received": len(session["received_chunks"]),
        "total": session["total_chunks"],
    }


@router.post("/{video_id}/chunked-upload/complete")
async def complete_chunked_upload(
    video_id: uuid.UUID,
    upload_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Reassemble chunks into final file."""
    if upload_id not in _active_uploads:
        raise HTTPException(status_code=404, detail="Upload session not found")

    session = _active_uploads[upload_id]
    if session["video_id"] != str(video_id):
        raise HTTPException(status_code=400, detail="Video ID mismatch")

    expected = set(range(session["total_chunks"]))
    missing = expected - session["received_chunks"]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing chunks: {sorted(missing)}")

    record = await db.get(Video, video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    # Reassemble chunks into final file
    file_key = f"raw/{video_id}/{uuid.uuid4()}.{session['ext']}"
    final_path = get_file_path(file_key)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(session["temp_dir"])
    with open(final_path, "wb") as out:
        for i in range(session["total_chunks"]):
            chunk_path = temp_dir / f"chunk_{i:05d}"
            out.write(chunk_path.read_bytes())

    # Cleanup temp dir and session
    shutil.rmtree(temp_dir, ignore_errors=True)
    del _active_uploads[upload_id]

    size_mb = final_path.stat().st_size / (1024 * 1024)
    record.file_key = file_key
    await db.commit()

    return {"file_key": file_key, "size_mb": round(size_mb, 1)}


@router.post("/{video_id}/process", response_model=JobResponse)
async def trigger_processing(
    video_id: uuid.UUID,
    profile_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.file_key:
        raise HTTPException(status_code=400, detail="No video file uploaded")

    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if not profile.photos:
        raise HTTPException(status_code=400, detail="Profile has no photos — upload at least one for ReID")

    job = ProcessingJob(video_id=video_id, profile_id=profile_id)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    task = celery_app.send_task("process_video", args=[str(job.id)])
    job.celery_task_id = task.id
    await db.commit()

    return job
