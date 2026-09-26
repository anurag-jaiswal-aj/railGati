"""Train models."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from railgati.db import Base

if TYPE_CHECKING:
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station


class Train(Base):
    """A canonical railway train identity."""

    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    observations: Mapped[list["TrainObservation"]] = relationship(
        "TrainObservation", back_populates="train", cascade="all, delete-orphan"
    )

    stop_observations: Mapped[list["TrainStopObservation"]] = relationship(
        "TrainStopObservation", back_populates="train", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Train(number={self.number})>"


class TrainObservation(Base):
    """A record of a train as it appeared in a specific dataset snapshot."""

    __tablename__ = "train_observations"

    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), primary_key=True
    )
    train_id: Mapped[int] = mapped_column(Integer, ForeignKey("trains.id"), primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    return_train_number: Mapped[str | None] = mapped_column(String(255), nullable=True)

    snapshot: Mapped["DatasetSnapshot"] = relationship()
    train: Mapped["Train"] = relationship(back_populates="observations")

    def __repr__(self) -> str:
        return f"<TrainObservation(train_id={self.train_id}, snapshot_id={self.snapshot_id})>"


class TrainStopObservation(Base):
    """A specific stop on a train's route within a snapshot."""

    __tablename__ = "train_stop_observations"

    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), primary_key=True
    )
    train_id: Mapped[int] = mapped_column(Integer, ForeignKey("trains.id"), primary_key=True)
    stop_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)

    station_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stations.id"), nullable=False, index=True
    )

    arrival_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    departure_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    snapshot: Mapped["DatasetSnapshot"] = relationship()
    train: Mapped["Train"] = relationship(back_populates="stop_observations")
    station: Mapped["Station"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<TrainStopObservation(train_id={self.train_id}, "
            f"stop_sequence={self.stop_sequence}, station_id={self.station_id})>"
        )
