import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.stat import StatEvent
from app.schemas.stat import StatEventResponse

router = APIRouter()


@router.get("/game/{game_id}", response_model=list[StatEventResponse])
async def get_game_stats(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StatEvent).where(StatEvent.game_id == game_id).order_by(StatEvent.timestamp)
    )
    return result.scalars().all()


@router.get("/game/{game_id}/summary")
async def get_game_summary(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for a game — points, turnovers, etc. by team."""
    result = await db.execute(
        select(StatEvent).where(StatEvent.game_id == game_id)
    )
    events = result.scalars().all()

    summary: dict = {}
    for event in events:
        team = event.team or "unknown"
        if team not in summary:
            summary[team] = {"points": 0, "turnovers": 0, "made_shots": 0, "missed_shots": 0}

        if event.event_type == "made_2pt":
            summary[team]["points"] += 2
            summary[team]["made_shots"] += 1
        elif event.event_type == "made_3pt":
            summary[team]["points"] += 3
            summary[team]["made_shots"] += 1
        elif event.event_type == "miss":
            summary[team]["missed_shots"] += 1
        elif event.event_type == "turnover":
            summary[team]["turnovers"] += 1

    return {"game_id": str(game_id), "teams": summary}
