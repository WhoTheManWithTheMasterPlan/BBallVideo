import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.highlight import Highlight
from app.models.job import ProcessingJob
from app.models.stat import Stat
from app.schemas.highlight import (
    HighlightResponse,
    HighlightReviewUpdate,
    ManualHighlightCreate,
)
from app.services.video.clipper import extract_clip, extract_thumbnail
from app.services.video.storage import get_file_path

router = APIRouter()


@router.get("/job/{job_id}", response_model=list[HighlightResponse])
async def list_highlights_by_job(
    job_id: uuid.UUID,
    event_type: str | None = None,
    review_status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Highlight).where(Highlight.job_id == job_id)
    if event_type:
        query = query.where(Highlight.event_type == event_type)
    if review_status:
        query = query.where(Highlight.review_status == review_status)
    query = query.order_by(Highlight.start_time)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/profile/{profile_id}", response_model=list[HighlightResponse])
async def list_highlights_by_profile(
    profile_id: uuid.UUID,
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Highlight)
        .join(ProcessingJob)
        .where(ProcessingJob.profile_id == profile_id)
    )
    if event_type:
        query = query.where(Highlight.event_type == event_type)
    query = query.order_by(Highlight.start_time)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{highlight_id}/review", response_model=HighlightResponse)
async def review_highlight(
    highlight_id: uuid.UUID,
    body: HighlightReviewUpdate,
    db: AsyncSession = Depends(get_db),
):
    highlight = await db.get(Highlight, highlight_id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")

    highlight.review_status = body.review_status
    highlight.corrected_event_type = body.corrected_event_type
    highlight.reject_reason = body.reject_reason
    highlight.reviewed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(highlight)
    return highlight


@router.post("/job/{job_id}/manual", response_model=HighlightResponse)
async def create_manual_highlight(
    job_id: uuid.UUID,
    body: ManualHighlightCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a manual highlight clip when the pipeline missed an event."""
    # Load job with its video relationship
    result = await db.execute(
        select(ProcessingJob)
        .options(selectinload(ProcessingJob.video))
        .where(ProcessingJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed")

    video = job.video
    if not video or not video.file_key:
        raise HTTPException(status_code=400, detail="Video file not found")

    video_path = str(get_file_path(video.file_key))
    highlight_id = uuid.uuid4()
    clip_file_key = f"highlights/{job_id}/{highlight_id}.mp4"
    thumb_file_key = f"highlights/{job_id}/{highlight_id}.jpg"
    clip_path = str(get_file_path(clip_file_key))
    thumb_path = str(get_file_path(thumb_file_key))

    start_time = max(0, body.timestamp - body.padding)
    end_time = body.timestamp + body.padding

    # Extract clip and thumbnail in a thread (ffmpeg is blocking)
    await asyncio.to_thread(
        extract_clip, video_path, clip_path, body.timestamp, body.timestamp, body.padding
    )
    await asyncio.to_thread(
        extract_thumbnail, video_path, thumb_path, body.timestamp
    )

    # Create Highlight record
    highlight = Highlight(
        id=highlight_id,
        job_id=job_id,
        event_type=body.event_type,
        start_time=start_time,
        end_time=end_time,
        file_key=clip_file_key,
        thumbnail_file_key=thumb_file_key,
        confidence=1.0,
        review_status="confirmed",
        metadata_={"source": "manual"},
    )
    db.add(highlight)

    # Create Stat record
    stat = Stat(
        job_id=job_id,
        event_type=body.event_type,
        timestamp=body.timestamp,
        metadata_={"source": "manual"},
    )
    db.add(stat)

    await db.commit()
    await db.refresh(highlight)
    return highlight


@router.patch("/job/{job_id}/review-all", response_model=dict)
async def review_all_highlights(
    job_id: uuid.UUID,
    body: HighlightReviewUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        update(Highlight)
        .where(Highlight.job_id == job_id, Highlight.review_status == "pending")
        .values(
            review_status=body.review_status,
            reviewed_at=datetime.utcnow(),
        )
    )
    await db.commit()
    return {"updated": result.rowcount}
