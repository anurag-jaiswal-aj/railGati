"""Station models."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from railgati.db import Base

if TYPE_CHECKING:
    from railgati.models.provenance import DatasetSnapshot


class Station(Base):
    """A canonical railway station identity."""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    observations: Mapped[list["StationObservation"]] = relationship(
        "StationObservation", back_populates="station", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Station(code={self.code})>"


class StationObservation(Base):
    """A record of a station as it appeared in a specific dataset snapshot."""

    __tablename__ = "station_observations"

    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), primary_key=True
    )
    station_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id"), primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    snapshot: Mapped["DatasetSnapshot"] = relationship()
    station: Mapped["Station"] = relationship(back_populates="observations")

    def __repr__(self) -> str:
        return f"<StationObservation(station_id={self.station_id}, snapshot_id={self.snapshot_id})>"
