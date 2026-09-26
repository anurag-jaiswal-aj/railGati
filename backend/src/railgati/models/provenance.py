"""Provenance models: DataSource and DatasetSnapshot."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from railgati.db import Base


class DataSource(Base):
    """A source of railway data."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    license: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    snapshots: Mapped[list["DatasetSnapshot"]] = relationship(
        "DatasetSnapshot", back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DataSource(name={self.name})>"


class DatasetSnapshot(Base):
    """A point-in-time snapshot of data from a DataSource."""

    __tablename__ = "dataset_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False
    )  # PENDING, ACTIVE, FAILED, SUPERSEDED
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source: Mapped[DataSource] = relationship("DataSource", back_populates="snapshots")

    def __repr__(self) -> str:
        return f"<DatasetSnapshot(id={self.id}, status={self.status})>"
