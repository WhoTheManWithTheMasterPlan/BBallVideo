import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.highlight import Highlight
from app.models.job import ProcessingJob
from app.schemas.highlight import HighlightResponse, HighlightReviewUpdate

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
    highlight.reviewed_at = datetime.utcnow()
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
