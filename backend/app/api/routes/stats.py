import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import ProcessingJob
from app.models.stat import Stat
from app.schemas.stat import StatResponse

router = APIRouter()


@router.get("/job/{job_id}", response_model=list[StatResponse])
async def list_stats_by_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stat).where(Stat.job_id == job_id).order_by(Stat.timestamp)
    )
    return result.scalars().all()


@router.get("/profile/{profile_id}/summary")
async def profile_stats_summary(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stat.event_type, func.count(Stat.id))
        .join(ProcessingJob)
        .where(ProcessingJob.profile_id == profile_id)
        .group_by(Stat.event_type)
    )
    return {row[0]: row[1] for row in result.all()}
