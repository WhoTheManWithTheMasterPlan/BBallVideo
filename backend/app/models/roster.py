import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Roster(Base):
    """A team roster — reusable across multiple games."""
    __tablename__ = "rosters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_name: Mapped[str] = mapped_column(String(100))
    season: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. "2025-26"
    jersey_color_primary: Mapped[str | None] = mapped_column(String(30), nullable=True)  # e.g. "#FFFFFF" or "white"
    jersey_color_secondary: Mapped[str | None] = mapped_column(String(30), nullable=True)
    user_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    players: Mapped[list["RosterPlayer"]] = relationship(back_populates="roster", lazy="selectin")


class RosterPlayer(Base):
    """A player on a roster, with optional photo for ReID."""
    __tablename__ = "roster_players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    roster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rosters.id"))
    name: Mapped[str] = mapped_column(String(100))
    jersey_number: Mapped[int] = mapped_column(Integer)
    height_inches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(10), nullable=True)  # PG, SG, SF, PF, C
    photo_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reid_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # numpy array as bytes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roster: Mapped["Roster"] = relationship(back_populates="players")

    @property
    def has_reid_embedding(self) -> bool:
        return self.reid_embedding is not None
