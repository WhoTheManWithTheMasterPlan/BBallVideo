import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.game import Game
from app.schemas.game import GameCreate, GameResponse

router = APIRouter()


@router.post("/", response_model=GameResponse)
async def create_game(
    game_in: GameCreate,
    db: AsyncSession = Depends(get_db),
):
    game = Game(
        title=game_in.title,
        home_team=game_in.home_team,
        away_team=game_in.away_team,
        game_date=game_in.game_date,
        user_id=game_in.user_id,
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return game


@router.get("/", response_model=list[GameResponse])
async def list_games(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Game).where(Game.user_id == user_id).order_by(Game.game_date.desc())
    )
    return result.scalars().all()


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game
