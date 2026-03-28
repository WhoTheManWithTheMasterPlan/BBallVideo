from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.api.routes import profiles, teams, videos, jobs, highlights, stats, files
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
    version="0.2.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["profiles"])
app.include_router(teams.router, prefix="/api/v1/profiles", tags=["teams"])
app.include_router(videos.router, prefix="/api/v1/videos", tags=["videos"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(highlights.router, prefix="/api/v1/highlights", tags=["highlights"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])


@app.get("/health")
async def health():
    return {"status": "ok"}
