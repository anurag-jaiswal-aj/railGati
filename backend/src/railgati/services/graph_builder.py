"""Service for materializing the railway network graph."""

from datetime import UTC, datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge, RailwayServiceEdge
from railgati.models.train import TrainStopObservation
from railgati.services.journey import _parse_time_to_minutes


def build_graph_for_timetable_snapshot(
    db: Session, timetable_snapshot_id: int
) -> RailwayGraphBuild:
    """Materializes ServiceEdges and NetworkEdges for a given timetable snapshot.

    This is an idempotent, deterministic operation that deletes existing edges for the snapshot
    and rebuilds them from TrainStopObservation.
    """

    # 1. Fetch or create the build record
    build_record = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    is_new = False
    if not build_record:
        is_new = True
        build_record = RailwayGraphBuild(
            timetable_snapshot_id=timetable_snapshot_id,
            status="PENDING",
        )
        db.add(build_record)
        db.commit()
        db.refresh(build_record)

    old_status = build_record.status

    try:
        # Mark as PENDING in the transaction so it rolls back if we fail
        build_record.status = "PENDING"
        build_record.error_message = None
        build_record.completed_at = None

        # 2. Delete existing edges for idempotency
        db.execute(
            delete(RailwayNetworkEdge).where(
                RailwayNetworkEdge.timetable_snapshot_id == timetable_snapshot_id
            )
        )
        db.execute(
            delete(RailwayServiceEdge).where(
                RailwayServiceEdge.timetable_snapshot_id == timetable_snapshot_id
            )
        )
        db.flush()

        # 3. Generate ServiceEdges
        # Fetch all stops for the snapshot, ordered by train and sequence
        query = (
            select(
                TrainStopObservation.train_id,
                TrainStopObservation.stop_sequence,
                TrainStopObservation.station_id,
                TrainStopObservation.departure_time,
                TrainStopObservation.arrival_time,
                TrainStopObservation.source_day,
            )
            .filter(TrainStopObservation.snapshot_id == timetable_snapshot_id)
            .order_by(TrainStopObservation.train_id, TrainStopObservation.stop_sequence)
        )
        stops = db.execute(query).all()

        service_edges = []
        for i in range(len(stops) - 1):
            curr = stops[i]
            nxt = stops[i + 1]

            # Ensure consecutive stops of the same train
            if curr.train_id == nxt.train_id and curr.stop_sequence + 1 == nxt.stop_sequence:
                orig_mins = _parse_time_to_minutes(curr.departure_time, curr.source_day)
                dest_mins = _parse_time_to_minutes(nxt.arrival_time, nxt.source_day)

                duration = None
                if orig_mins is not None and dest_mins is not None:
                    # Guard against negative durations across days if missing source day increment
                    # (Fallback safety, though source_day should cover this)
                    calc_duration = dest_mins - orig_mins
                    if calc_duration >= 0:
                        duration = calc_duration

                service_edges.append(
                    {
                        "timetable_snapshot_id": timetable_snapshot_id,
                        "train_id": curr.train_id,
                        "from_station_id": curr.station_id,
                        "from_stop_sequence": curr.stop_sequence,
                        "to_station_id": nxt.station_id,
                        "to_stop_sequence": nxt.stop_sequence,
                        "departure_time": curr.departure_time,
                        "arrival_time": nxt.arrival_time,
                        "source_day_offset": curr.source_day,
                        "duration_minutes": duration,
                    }
                )

        # Bulk insert ServiceEdges in chunks to avoid memory spikes
        if service_edges:
            db.execute(insert(RailwayServiceEdge), service_edges)
            db.flush()

        # 4. Generate NetworkEdges
        # Aggregate from newly created ServiceEdges
        agg_query = (
            select(
                RailwayServiceEdge.from_station_id,
                RailwayServiceEdge.to_station_id,
                func.count(RailwayServiceEdge.train_id).label("train_count"),
                func.min(RailwayServiceEdge.duration_minutes).label("min_duration_minutes"),
            )
            .filter(RailwayServiceEdge.timetable_snapshot_id == timetable_snapshot_id)
            .group_by(RailwayServiceEdge.from_station_id, RailwayServiceEdge.to_station_id)
        )

        agg_results = db.execute(agg_query).all()

        network_edges = [
            {
                "timetable_snapshot_id": timetable_snapshot_id,
                "from_station_id": row.from_station_id,
                "to_station_id": row.to_station_id,
                "train_count": row.train_count,
                "min_duration_minutes": row.min_duration_minutes,
            }
            for row in agg_results
        ]

        if network_edges:
            db.execute(insert(RailwayNetworkEdge), network_edges)
            db.flush()

        # 5. Finalize
        build_record.status = "ACTIVE"
        build_record.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(build_record)
        return build_record

    except Exception as e:
        db.rollback()
        if is_new or old_status != "ACTIVE":
            build_record.status = "FAILED"
        else:
            build_record.status = "ACTIVE"

        build_record.error_message = str(e)
        db.commit()
        db.refresh(build_record)

        # Raise the exception so it is surfaced to the caller
        raise e
