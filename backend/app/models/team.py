import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id"))
    name: Mapped[str] = mapped_column(String(100))
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profile: Mapped["Profile"] = relationship(back_populates="teams")
    photos: Mapped[list["TeamPhoto"]] = relationship(back_populates="team", lazy="selectin")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="team", lazy="selectin")


class TeamPhoto(Base):
    __tablename__ = "team_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"))
    file_key: Mapped[str] = mapped_column(String(500))
    reid_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team: Mapped["Team"] = relationship(back_populates="photos")

    @property
    def has_embedding(self) -> bool:
        return self.reid_embedding is not None
