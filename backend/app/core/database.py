from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Async engine for FastAPI routes
engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for Celery workers (converts asyncpg URL to psycopg)
sync_database_url = settings.database_url.replace("+asyncpg", "+psycopg")
sync_engine = create_engine(sync_database_url, echo=False)
sync_session = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


def get_sync_db() -> Session:
    """Sync session for use in Celery tasks."""
    session = sync_session()
    try:
        yield session
    finally:
        session.close()
