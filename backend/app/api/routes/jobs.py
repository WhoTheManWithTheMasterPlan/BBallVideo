import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import ProcessingJob
from app.schemas.job import JobResponse

router = APIRouter()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/profile/{profile_id}", response_model=list[JobResponse])
async def list_jobs_by_profile(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.profile_id == profile_id)
        .order_by(ProcessingJob.created_at.desc())
    )
    return result.scalars().all()


@router.get("/video/{video_id}", response_model=list[JobResponse])
async def list_jobs_by_video(video_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.video_id == video_id)
        .order_by(ProcessingJob.created_at.desc())
    )
    return result.scalars().all()
