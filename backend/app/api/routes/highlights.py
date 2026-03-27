import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.highlight import Highlight
from app.models.job import ProcessingJob
from app.schemas.highlight import HighlightResponse

router = APIRouter()


@router.get("/job/{job_id}", response_model=list[HighlightResponse])
async def list_highlights_by_job(
    job_id: uuid.UUID,
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Highlight).where(Highlight.job_id == job_id)
    if event_type:
        query = query.where(Highlight.event_type == event_type)
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
