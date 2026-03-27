import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.profile import Profile, ProfilePhoto
from app.schemas.profile import ProfileCreate, ProfileResponse, ProfilePhotoResponse
from app.services.video.storage import save_upload

router = APIRouter()


@router.post("/", response_model=ProfileResponse)
async def create_profile(data: ProfileCreate, db: AsyncSession = Depends(get_db)):
    profile = Profile(user_id=data.user_id, name=data.name)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/", response_model=list[ProfileResponse])
async def list_profiles(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Profile).where(Profile.user_id == user_id).order_by(Profile.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/{profile_id}/photos", response_model=ProfilePhotoResponse)
async def upload_photo(
    profile_id: uuid.UUID,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    data = await photo.read()
    photo_id = uuid.uuid4()
    file_key = f"photos/{profile_id}/{photo_id}.jpg"
    save_upload(file_key, data)

    # Extract ReID embedding (lazy import — only available on GPU worker or if ML libs installed)
    reid_embedding = None
    try:
        from app.services.inference.reid import ReIDExtractor
        extractor = ReIDExtractor()
        reid_embedding = extractor.extract_from_bytes(data)
    except Exception:
        pass  # ML libs not available on API server — embedding generated during processing

    is_first = len(profile.photos) == 0
    photo_record = ProfilePhoto(
        id=photo_id,
        profile_id=profile_id,
        file_key=file_key,
        reid_embedding=reid_embedding,
        is_primary=is_first,
    )
    db.add(photo_record)
    await db.commit()
    await db.refresh(photo_record)
    return photo_record


@router.delete("/{profile_id}/photos/{photo_id}")
async def delete_photo(
    profile_id: uuid.UUID, photo_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    photo = await db.get(ProfilePhoto, photo_id)
    if not photo or photo.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    await db.delete(photo)
    await db.commit()
    return {"status": "deleted"}
