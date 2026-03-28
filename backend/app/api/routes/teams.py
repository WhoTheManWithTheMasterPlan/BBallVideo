import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.profile import Profile
from app.models.team import Team, TeamPhoto
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse, TeamPhotoResponse
from app.services.video.storage import save_upload

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
        jersey_number=data.jersey_number,
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
    if data.jersey_number is not None:
        team.jersey_number = data.jersey_number
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


# --- Team Photos ---


@router.post("/{profile_id}/teams/{team_id}/photos", response_model=TeamPhotoResponse)
async def upload_team_photo(
    profile_id: uuid.UUID,
    team_id: uuid.UUID,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    team = await db.get(Team, team_id)
    if not team or team.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Team not found")

    data = await photo.read()
    photo_id = uuid.uuid4()
    file_key = f"photos/{profile_id}/{team_id}/{photo_id}.jpg"
    save_upload(file_key, data)

    reid_embedding = None
    try:
        from app.services.inference.reid import ReIDExtractor
        extractor = ReIDExtractor()
        reid_embedding = extractor.extract_from_bytes(data)
    except Exception:
        pass

    is_first = len(team.photos) == 0
    photo_record = TeamPhoto(
        id=photo_id,
        team_id=team_id,
        file_key=file_key,
        reid_embedding=reid_embedding,
        is_primary=is_first,
    )
    db.add(photo_record)
    await db.commit()
    await db.refresh(photo_record)
    return photo_record


@router.delete("/{profile_id}/teams/{team_id}/photos/{photo_id}")
async def delete_team_photo(
    profile_id: uuid.UUID,
    team_id: uuid.UUID,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    photo = await db.get(TeamPhoto, photo_id)
    if not photo or photo.team_id != team_id:
        raise HTTPException(status_code=404, detail="Photo not found")

    team = await db.get(Team, team_id)
    if not team or team.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Team not found")

    await db.delete(photo)
    await db.commit()
    return {"status": "deleted"}
