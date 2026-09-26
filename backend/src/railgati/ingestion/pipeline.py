"""Core ingestion pipeline."""

import hashlib
from collections.abc import Generator

from sqlalchemy import select
from sqlalchemy.orm import Session

from railgati.ingestion.schema import IngestionResult, ParsedStation
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation


class Pipeline:
    """Orchestrates the data ingestion process."""

    def __init__(self, db: Session, dry_run: bool = False):
        self.db = db
        self.dry_run = dry_run

    def get_or_create_source(self) -> DataSource:
        """Get or create the Datameet data source."""
        stmt = select(DataSource).where(DataSource.name == "Datameet Railways")
        source = self.db.execute(stmt).scalar_one_or_none()

        if not source:
            source = DataSource(
                name="Datameet Railways",
                publisher="Datameet Community",
                url="https://github.com/datameet/railways",
                license="CC0",
                description="Indian railway station coordinates",
            )
            self.db.add(source)
            self.db.flush()

        return source

    def calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(4096), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def validate_station(self, station: ParsedStation, result: IngestionResult) -> bool:
        """Validate a station record. Returns True if valid."""
        is_valid = True
        rejection_reason = ""

        if not station.code or not station.name:
            result.missing_required_fields += 1
            reason = f"Missing required fields. code='{station.code}', name='{station.name}'"
            result.warnings.append(reason)
            rejection_reason = reason
            is_valid = False

        if (
            station.latitude is not None
            and station.longitude is not None
            and not (6.0 <= station.latitude <= 36.0 and 68.0 <= station.longitude <= 98.0)
        ):
            result.invalid_coordinates += 1
            reason = (
                f"Coordinates out of bounds for {station.code}: "
                f"{station.latitude}, {station.longitude}"
            )
            result.warnings.append(reason)
            if not rejection_reason:
                rejection_reason = reason
            is_valid = False

        if not is_valid:
            result.rejections.append(
                {
                    "code": station.code,
                    "name": station.name,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "reason": rejection_reason,
                }
            )

        return is_valid

    def run(
        self, file_path: str, parser_gen: Generator[ParsedStation, None, None]
    ) -> IngestionResult:
        """Run the ingestion pipeline."""
        result = IngestionResult(source_name="Datameet Railways", snapshot_id=None)

        # 1. Setup provenance
        source = self.get_or_create_source()
        checksum = self.calculate_checksum(file_path)

        snapshot = DatasetSnapshot(
            source_id=source.id,
            checksum=checksum,
            status="PENDING",
        )
        self.db.add(snapshot)
        self.db.flush()

        result.snapshot_id = snapshot.id

        seen_codes = set()

        # Fast lookup for existing canonical stations
        stmt = select(Station.code, Station.id)
        existing_stations: dict[str, int] = dict(self.db.execute(stmt).all())

        try:
            for parsed in parser_gen:
                result.records_read += 1
                result.records_parsed += 1

                # 2. Validate
                if not self.validate_station(parsed, result):
                    result.records_rejected += 1
                    continue

                # 3. Handle intra-dataset duplicates
                if parsed.code in seen_codes:
                    result.duplicates += 1
                    reason = f"Duplicate code in dataset: {parsed.code}"
                    result.warnings.append(reason)
                    result.rejections.append(
                        {
                            "code": parsed.code,
                            "name": parsed.name,
                            "reason": reason,
                        }
                    )
                    result.records_rejected += 1
                    continue

                seen_codes.add(parsed.code)

                # 4. Canonical Station Identity
                station_id = existing_stations.get(parsed.code)
                if not station_id:
                    # Create new canonical identity
                    new_station = Station(code=parsed.code)
                    self.db.add(new_station)
                    self.db.flush()  # to get the ID
                    station_id = new_station.id
                    existing_stations[parsed.code] = station_id

                # 5. Station Observation (Snapshot Membership)
                obs = StationObservation(
                    snapshot_id=snapshot.id,
                    station_id=station_id,
                    name=parsed.name,
                    state=parsed.state,
                    zone=parsed.zone,
                    latitude=parsed.latitude,
                    longitude=parsed.longitude,
                )
                self.db.add(obs)
                result.records_accepted += 1

            snapshot.record_count = result.records_accepted
            snapshot.status = "ACTIVE"
            result.status = "SUCCESS"

            if self.dry_run:
                self.db.rollback()
                result.status = "DRY-RUN (Rolled back)"
            else:
                self.db.commit()

        except Exception as e:
            self.db.rollback()
            result.status = "FAILED"
            result.warnings.append(f"Fatal error: {e!s}")

            # Record the failure if not dry_run
            if not self.dry_run:
                try:
                    failed_snapshot = DatasetSnapshot(
                        source_id=source.id,
                        checksum=checksum,
                        status="FAILED",
                        error_message=str(e),
                    )
                    self.db.add(failed_snapshot)
                    self.db.commit()
                except Exception:
                    self.db.rollback()

        return result
