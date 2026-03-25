import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.clip import Clip
from app.schemas.clip import ClipResponse

router = APIRouter()


@router.get("/game/{game_id}", response_model=list[ClipResponse])
async def get_game_clips(
    game_id: uuid.UUID,
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Clip).where(Clip.game_id == game_id)
    if event_type:
        query = query.where(Clip.event_type == event_type)
    query = query.order_by(Clip.start_time)

    result = await db.execute(query)
    return result.scalars().all()
