import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StatEvent(Base):
    __tablename__ = "stat_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("games.id"))
    event_type: Mapped[str] = mapped_column(String(50))  # made_2pt, made_3pt, miss, turnover, steal, etc.
    timestamp: Mapped[float] = mapped_column(Float)  # seconds into video
    player_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    court_x: Mapped[float | None] = mapped_column(Float, nullable=True)  # normalized court coordinates
    court_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped["Game"] = relationship(back_populates="stats")
