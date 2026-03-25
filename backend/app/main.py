from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.api.routes import games, uploads, stats, clips, files, roster
from app.core.config import settings
from app.core.database import engine, Base
import app.models  # noqa: F401 — register all models with Base.metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience — replace with Alembic for prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="BBallVideo API",
    description="Basketball video analysis platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router, prefix="/api/v1/uploads", tags=["uploads"])
app.include_router(games.router, prefix="/api/v1/games", tags=["games"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(clips.router, prefix="/api/v1/clips", tags=["clips"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(roster.router, prefix="/api/v1/rosters", tags=["rosters"])


@app.get("/health")
async def health():
    return {"status": "ok"}
