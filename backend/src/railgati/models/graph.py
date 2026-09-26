"""Railway network graph models."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from railgati.db import Base

if TYPE_CHECKING:
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station
    from railgati.models.train import Train


class RailwayGraphBuild(Base):
    """A record of a materialized graph derived from a timetable snapshot."""

    __tablename__ = "railway_graph_builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timetable_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), nullable=False, unique=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False
    )  # PENDING, ACTIVE, FAILED

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    timetable_snapshot: Mapped["DatasetSnapshot"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<RailwayGraphBuild(id={self.id}, "
            f"snapshot_id={self.timetable_snapshot_id}, status={self.status})>"
        )


class RailwayServiceEdge(Base):
    """A specific train segment between two consecutive stops."""

    __tablename__ = "railway_service_edges"
    __table_args__ = (
        Index("ix_service_edges_from_station", "timetable_snapshot_id", "from_station_id"),
        Index("ix_service_edges_to_station", "timetable_snapshot_id", "to_station_id"),
    )

    timetable_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), primary_key=True
    )
    train_id: Mapped[int] = mapped_column(Integer, ForeignKey("trains.id"), primary_key=True)
    from_stop_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)

    from_station_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id"), nullable=False)
    to_station_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id"), nullable=False)
    to_stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    departure_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    arrival_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_day_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    timetable_snapshot: Mapped["DatasetSnapshot"] = relationship()
    train: Mapped["Train"] = relationship()
    from_station: Mapped["Station"] = relationship(foreign_keys=[from_station_id])
    to_station: Mapped["Station"] = relationship(foreign_keys=[to_station_id])

    def __repr__(self) -> str:
        return (
            f"<RailwayServiceEdge(train_id={self.train_id}, "
            f"seq={self.from_stop_sequence}->{self.to_stop_sequence})>"
        )


class RailwayNetworkEdge(Base):
    """An aggregated physical network connectivity edge."""

    __tablename__ = "railway_network_edges"
    __table_args__ = (
        Index("ix_network_edges_from_station", "timetable_snapshot_id", "from_station_id"),
        Index("ix_network_edges_to_station", "timetable_snapshot_id", "to_station_id"),
    )

    timetable_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), primary_key=True
    )
    from_station_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stations.id"), primary_key=True
    )
    to_station_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id"), primary_key=True)

    train_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    timetable_snapshot: Mapped["DatasetSnapshot"] = relationship()
    from_station: Mapped["Station"] = relationship(foreign_keys=[from_station_id])
    to_station: Mapped["Station"] = relationship(foreign_keys=[to_station_id])

    def __repr__(self) -> str:
        return (
            f"<RailwayNetworkEdge(snapshot_id={self.timetable_snapshot_id}, "
            f"{self.from_station_id}->{self.to_station_id})>"
        )
