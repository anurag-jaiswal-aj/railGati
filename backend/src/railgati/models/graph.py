"""Railway network graph models."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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


class RailwayNetworkEdgeResilience(Base):
    """Precomputed exact unweighted topological resilience metrics for a canonical undirected structural edge."""

    __tablename__ = "railway_network_edge_resilience"
    __table_args__ = (
        Index("ix_edge_resilience_build", "graph_build_id"),
        Index(
            "ix_edge_resilience_lookup",
            "graph_build_id",
            "station_a_id",
            "station_b_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_build_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("railway_graph_builds.id"), nullable=False
    )
    timetable_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset_snapshots.id"), nullable=False
    )

    station_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id"), nullable=False)
    station_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("stations.id"), nullable=False)

    detour_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detour_exists: Mapped[bool] = mapped_column(nullable=False)
    is_structural_bridge: Mapped[bool] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    graph_build: Mapped["RailwayGraphBuild"] = relationship()
    timetable_snapshot: Mapped["DatasetSnapshot"] = relationship()
    station_a: Mapped["Station"] = relationship(foreign_keys=[station_a_id])
    station_b: Mapped["Station"] = relationship(foreign_keys=[station_b_id])

    def __repr__(self) -> str:
        return (
            f"<RailwayNetworkEdgeResilience(build={self.graph_build_id}, "
            f"{self.station_a_id}-{self.station_b_id}, bridge={self.is_structural_bridge})>"
        )


class RailwayStationTopologicalCoreness(Base):
    __tablename__ = "railway_station_topological_coreness"

    id: Mapped[int] = mapped_column(primary_key=True)
    graph_build_id: Mapped[int] = mapped_column(ForeignKey("railway_graph_builds.id"))
    timetable_snapshot_id: Mapped[int] = mapped_column(ForeignKey("dataset_snapshots.id"))
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))

    coreness: Mapped[int] = mapped_column()
    degree: Mapped[int] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "graph_build_id",
            "station_id",
            name="uq_railway_station_topological_coreness_build_station",
        ),
        Index("ix_railway_station_coreness_build_station", "graph_build_id", "station_id"),
        Index("ix_railway_station_coreness_snapshot", "timetable_snapshot_id"),
    )

    graph_build: Mapped["RailwayGraphBuild"] = relationship()
    timetable_snapshot: Mapped["DatasetSnapshot"] = relationship()
    station: Mapped["Station"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<RailwayStationTopologicalCoreness(build={self.graph_build_id}, "
            f"station={self.station_id}, core={self.coreness})>"
        )


class RailwayNetworkEdgeTopologicalTrussness(Base):
    __tablename__ = "railway_network_edge_topological_trussness"

    id: Mapped[int] = mapped_column(primary_key=True)
    graph_build_id: Mapped[int] = mapped_column(ForeignKey("railway_graph_builds.id"))
    timetable_snapshot_id: Mapped[int] = mapped_column(ForeignKey("dataset_snapshots.id"))
    station_a_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    station_b_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))

    trussness: Mapped[int] = mapped_column()
    triangle_support: Mapped[int] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "graph_build_id",
            "station_a_id",
            "station_b_id",
            name="uq_railway_network_edge_trussness_build_stations",
        ),
        CheckConstraint("station_a_id < station_b_id", name="ck_edge_trussness_station_order"),
        Index("ix_railway_edge_trussness_build_stations", "graph_build_id", "station_a_id", "station_b_id"),
        Index("ix_railway_edge_trussness_snapshot", "timetable_snapshot_id"),
    )

    graph_build: Mapped["RailwayGraphBuild"] = relationship()
    timetable_snapshot: Mapped["DatasetSnapshot"] = relationship()
    station_a: Mapped["Station"] = relationship(foreign_keys=[station_a_id])
    station_b: Mapped["Station"] = relationship(foreign_keys=[station_b_id])

    def __repr__(self) -> str:
        return (
            f"<RailwayNetworkEdgeTopologicalTrussness(build={self.graph_build_id}, "
            f"{self.station_a_id}-{self.station_b_id}, truss={self.trussness})>"
        )
