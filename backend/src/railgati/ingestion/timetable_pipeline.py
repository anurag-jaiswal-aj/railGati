"""Timetable ingestion pipeline extensions."""

from collections.abc import Generator

from sqlalchemy import select

from railgati.ingestion.pipeline import Pipeline
from railgati.ingestion.schema import IngestionResult, ParsedSchedule, ParsedTrain
from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


class TimetablePipeline(Pipeline):
    """Orchestrates the timetable data ingestion process."""

    def validate_train(self, train: ParsedTrain, result: IngestionResult) -> bool:
        is_valid = True
        rejection_reason = ""
        if not train.number or not train.name:
            result.missing_required_fields += 1
            reason = f"Missing required fields. number='{train.number}', name='{train.name}'"
            result.warnings.append(reason)
            rejection_reason = reason
            is_valid = False

        if not is_valid:
            result.rejections.append({
                "snapshot_id": result.snapshot_id,
                "source_index": train.source_index,
                "number": train.number,
                "reason": rejection_reason,
            })
        return is_valid

    def run_timetable(
        self,
        trains_file: str,
        schedules_file: str,
        trains_gen: Generator[ParsedTrain, None, None],
        schedules_gen: Generator[ParsedSchedule, None, None],
    ) -> IngestionResult:
        """Run the timetable ingestion pipeline."""
        result = IngestionResult(source_name="Datameet Railways", snapshot_id=None)

        source = self.get_or_create_source()
        train_checksum = self.calculate_checksum(trains_file)
        sched_checksum = self.calculate_checksum(schedules_file)
        checksum = f"{train_checksum}_{sched_checksum}"

        snapshot = DatasetSnapshot(
            source_id=source.id,
            checksum=checksum,
            status="PENDING",
        )
        self.db.add(snapshot)
        self.db.flush()
        result.snapshot_id = snapshot.id

        seen_trains = set()

        # Load all canonical stations for exact matching
        stmt = select(Station.code, Station.id)
        existing_stations: dict[str, int] = dict(self.db.execute(stmt).all())

        try:
            # First, ingest trains
            train_db_ids = {}
            for parsed_train in trains_gen:
                result.records_read += 1
                result.records_parsed += 1

                if not self.validate_train(parsed_train, result):
                    result.records_rejected += 1
                    continue

                if parsed_train.number in seen_trains:
                    result.duplicates += 1
                    result.records_rejected += 1
                    continue

                seen_trains.add(parsed_train.number)

                # UPSERT Canonical Train
                stmt_train = select(Train).where(Train.number == parsed_train.number)
                train_obj = self.db.execute(stmt_train).scalar_one_or_none()
                if not train_obj:
                    train_obj = Train(number=parsed_train.number)
                    self.db.add(train_obj)
                    self.db.flush()

                train_db_ids[parsed_train.number] = train_obj.id

                # TrainObservation
                obs = TrainObservation(
                    snapshot_id=snapshot.id,
                    train_id=train_obj.id,
                    name=parsed_train.name,
                    type=parsed_train.type,
                    return_train_number=parsed_train.return_train_number,
                )
                self.db.add(obs)
                result.records_accepted += 1

            # Next, ingest schedules
            schedules_by_train: dict[str, list[ParsedSchedule]] = {}
            for parsed_schedule in schedules_gen:
                result.records_read += 1
                result.records_parsed += 1

                if parsed_schedule.train_number not in train_db_ids:
                    # Parent train didn't exist or was rejected
                    result.records_rejected += 1
                    continue

                if parsed_schedule.station_code not in existing_stations:
                    result.unknown_station_codes += 1
                    result.records_rejected += 1
                    result.rejections.append({
                        "snapshot_id": snapshot.id,
                        "source_id": parsed_schedule.source_id,
                        "train_number": parsed_schedule.train_number,
                        "station_code": parsed_schedule.station_code,
                        "reason": f"Unknown station code: {parsed_schedule.station_code}",
                    })
                    continue

                if parsed_schedule.train_number not in schedules_by_train:
                    schedules_by_train[parsed_schedule.train_number] = []
                schedules_by_train[parsed_schedule.train_number].append(parsed_schedule)

            # Insert TrainStopObservations deterministically sorted by source_id
            for train_number, schedules in schedules_by_train.items():
                schedules.sort(key=lambda s: s.source_id)
                train_id = train_db_ids[train_number]

                for seq, sched in enumerate(schedules, start=1):
                    stop_obs = TrainStopObservation(
                        snapshot_id=snapshot.id,
                        train_id=train_id,
                        stop_sequence=seq,
                        station_id=existing_stations[sched.station_code],
                        arrival_time=sched.arrival_time,
                        departure_time=sched.departure_time,
                        source_day=sched.day,
                    )
                    self.db.add(stop_obs)
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
