import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("games.id"))
    event_type: Mapped[str] = mapped_column(String(50))  # made_shot, turnover, assist, etc.
    start_time: Mapped[float] = mapped_column(Float)  # seconds into video
    end_time: Mapped[float] = mapped_column(Float)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # relative path in storage
    thumbnail_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    player_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped["Game"] = relationship(back_populates="clips")
