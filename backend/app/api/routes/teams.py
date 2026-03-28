import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.profile import Profile
from app.models.team import Team
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse

router = APIRouter()


@router.post("/{profile_id}/teams", response_model=TeamResponse)
@router.post("/{profile_id}/teams/", response_model=TeamResponse)
async def create_team(
    profile_id: uuid.UUID,
    data: TeamCreate,
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    team = Team(
        profile_id=profile_id,
        name=data.name,
        color_primary=data.color_primary,
        color_secondary=data.color_secondary,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.get("/{profile_id}/teams", response_model=list[TeamResponse])
@router.get("/{profile_id}/teams/", response_model=list[TeamResponse])
async def list_teams(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Team).where(Team.profile_id == profile_id).order_by(Team.created_at.desc())
    )
    return result.scalars().all()


@router.put("/{profile_id}/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    profile_id: uuid.UUID,
    team_id: uuid.UUID,
    data: TeamUpdate,
    db: AsyncSession = Depends(get_db),
):
    team = await db.get(Team, team_id)
    if not team or team.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Team not found")

    if data.name is not None:
        team.name = data.name
    if data.color_primary is not None:
        team.color_primary = data.color_primary
    if data.color_secondary is not None:
        team.color_secondary = data.color_secondary

    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/{profile_id}/teams/{team_id}")
async def delete_team(
    profile_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    team = await db.get(Team, team_id)
    if not team or team.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Team not found")
    await db.delete(team)
    await db.commit()
    return {"status": "deleted"}
