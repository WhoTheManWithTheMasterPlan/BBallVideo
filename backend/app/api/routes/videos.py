import uuid

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
from app.services.video.storage import check_storage_limit, save_upload
from app.workers.celery_app import celery_app

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
