import asyncio
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.config import settings
from app.models.highlight import Highlight
from app.models.job import ProcessingJob
from app.models.stat import Stat
from app.schemas.highlight import (
    HighlightResponse,
    HighlightReviewUpdate,
    ManualHighlightCreate,
    ReelCreate,
    ReelResponse,
)
from app.services.video.clipper import extract_clip, extract_thumbnail, stitch_clips
from app.services.video.storage import get_file_path

logger = logging.getLogger(__name__)

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

    start_time = max(0, body.start_time)
    end_time = body.end_time
    midpoint = (start_time + end_time) / 2

    # Extract clip and thumbnail in a thread (ffmpeg is blocking)
    await asyncio.to_thread(
        extract_clip, video_path, clip_path, start_time, end_time, 0.0
    )
    await asyncio.to_thread(
        extract_thumbnail, video_path, thumb_path, midpoint
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
        timestamp=midpoint,
        metadata_={"source": "manual"},
    )
    db.add(stat)

    await db.commit()
    await db.refresh(highlight)

    # Export clip to training data folder for ML retraining
    try:
        training_dir = Path(settings.storage_base_path) / "training" / "event-classifier" / body.event_type
        training_dir.mkdir(parents=True, exist_ok=True)
        dest = training_dir / f"{highlight_id}.mp4"
        await asyncio.to_thread(shutil.copy2, clip_path, str(dest))
        logger.info(f"Exported manual clip to training: {dest}")
    except Exception as e:
        logger.warning(f"Failed to export clip to training data: {e}")

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


@router.post("/job/{job_id}/reel", response_model=ReelResponse)
async def create_reel(
    job_id: uuid.UUID,
    body: ReelCreate,
    db: AsyncSession = Depends(get_db),
):
    """Stitch selected highlight clips into a single downloadable reel MP4."""
    if len(body.highlight_ids) < 1:
        raise HTTPException(status_code=400, detail="At least one highlight is required")

    # Load all requested highlights and verify they belong to this job
    result = await db.execute(
        select(Highlight).where(
            Highlight.id.in_([str(hid) for hid in body.highlight_ids]),
            Highlight.job_id == job_id,
        )
    )
    highlights_map = {str(h.id): h for h in result.scalars().all()}

    # Check all IDs were found and belong to this job
    missing = [str(hid) for hid in body.highlight_ids if str(hid) not in highlights_map]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Highlights not found or not in this job: {missing}",
        )

    # Build ordered list of clip file paths
    clip_paths: list[str] = []
    for hid in body.highlight_ids:
        h = highlights_map[str(hid)]
        if not h.file_key:
            raise HTTPException(
                status_code=400,
                detail=f"Highlight {hid} has no clip file",
            )
        path = get_file_path(h.file_key)
        if not path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Clip file missing for highlight {hid}",
            )
        clip_paths.append(str(path))

    # Generate output path
    reel_id = uuid.uuid4()
    reel_file_key = f"reels/{job_id}/{reel_id}.mp4"
    reel_path = str(get_file_path(reel_file_key))

    # Stitch clips in a thread (ffmpeg is blocking)
    try:
        duration = await asyncio.to_thread(stitch_clips, clip_paths, reel_path)
    except Exception as e:
        logger.error(f"Reel stitching failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reel")

    return ReelResponse(
        file_key=reel_file_key,
        duration_seconds=duration,
        clip_count=len(clip_paths),
    )
