import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.roster import Roster, RosterPlayer
from app.schemas.roster import RosterCreate, RosterResponse, RosterPlayerResponse
from app.services.video.storage import save_upload, check_storage_limit

router = APIRouter()

# Lazy-loaded ReID model (expensive to initialize, needs ML libs)
_reid = None


def get_reid():
    global _reid
    if _reid is None:
        from app.services.inference.reid import ReIDExtractor
        _reid = ReIDExtractor()
    return _reid


@router.post("/", response_model=RosterResponse)
async def create_roster(
    roster_in: RosterCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new roster with players."""
    roster = Roster(
        team_name=roster_in.team_name,
        season=roster_in.season,
        jersey_color_primary=roster_in.jersey_color_primary,
        jersey_color_secondary=roster_in.jersey_color_secondary,
        user_id=roster_in.user_id,
    )
    db.add(roster)
    await db.flush()

    for p in roster_in.players:
        player = RosterPlayer(
            roster_id=roster.id,
            name=p.name,
            jersey_number=p.jersey_number,
            height_inches=p.height_inches,
            position=p.position,
        )
        db.add(player)

    await db.commit()
    await db.refresh(roster)
    return roster


@router.get("/", response_model=list[RosterResponse])
async def list_rosters(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Roster).where(Roster.user_id == user_id).order_by(Roster.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{roster_id}", response_model=RosterResponse)
async def get_roster(
    roster_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    roster = await db.get(Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404, detail="Roster not found")
    return roster


@router.post("/{roster_id}/players", response_model=RosterPlayerResponse)
async def add_player(
    roster_id: uuid.UUID,
    name: str,
    jersey_number: int,
    height_inches: int | None = None,
    position: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Add a player to an existing roster."""
    roster = await db.get(Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404, detail="Roster not found")

    player = RosterPlayer(
        roster_id=roster_id,
        name=name,
        jersey_number=jersey_number,
        height_inches=height_inches,
        position=position,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@router.post("/players/{player_id}/photo", response_model=RosterPlayerResponse)
async def upload_player_photo(
    player_id: uuid.UUID,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a player photo and generate ReID embedding."""
    player = await db.get(RosterPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Validate image
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    data = await photo.read()

    if not check_storage_limit(len(data)):
        raise HTTPException(status_code=507, detail="Storage limit reached")

    # Save photo
    ext = photo.filename.rsplit(".", 1)[-1].lower() if photo.filename and "." in photo.filename else "jpg"
    file_key = f"photos/{player.roster_id}/{player_id}.{ext}"
    save_upload(file_key, data)
    player.photo_file_key = file_key

    # Generate ReID embedding from photo
    reid = get_reid()
    embedding_bytes = reid.extract_from_bytes(data)
    if embedding_bytes is not None:
        player.reid_embedding = embedding_bytes

    await db.commit()
    await db.refresh(player)
    return player


@router.post("/{roster_id}/team-photo")
async def upload_team_photo(
    roster_id: uuid.UUID,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a team photo. Detects all players, extracts ReID embeddings,
    and attempts to match them to roster entries via jersey OCR.
    """
    roster = await db.get(Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404, detail="Roster not found")

    data = await photo.read()

    # Save team photo
    file_key = f"photos/{roster_id}/team_photo.jpg"
    save_upload(file_key, data)

    # Detect players and extract embeddings
    reid = get_reid()
    player_extractions = reid.extract_from_team_photo(data)

    matched = 0
    for extraction in player_extractions:
        # Try to match jersey number to roster player
        if extraction["jersey_number"] is not None:
            result = await db.execute(
                select(RosterPlayer).where(
                    RosterPlayer.roster_id == roster_id,
                    RosterPlayer.jersey_number == extraction["jersey_number"],
                )
            )
            player = result.scalar_one_or_none()
            if player:
                player.reid_embedding = extraction["embedding"]
                if not player.photo_file_key:
                    # Save individual crop
                    crop_key = f"photos/{roster_id}/{player.id}_crop.jpg"
                    save_upload(crop_key, extraction["crop_bytes"])
                    player.photo_file_key = crop_key
                matched += 1

    await db.commit()

    return {
        "players_detected": len(player_extractions),
        "players_matched": matched,
        "unmatched": len(player_extractions) - matched,
    }
