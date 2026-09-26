import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from railgati.api.v1.schemas import (
    JourneyLeg,
    JourneyOption,
    JourneyType,
    ProvenanceInfo,
    TimingConfidence,
)
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


def _parse_time_to_minutes(time_str: str | None, source_day: int | None) -> int | None:
    if not time_str or source_day is None:
        return None
    try:
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        return ((source_day - 1) * 1440) + (hours * 60) + minutes
    except (ValueError, IndexError):
        return None


def find_direct_journeys(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    destination_station_id: int,
) -> list[JourneyOption]:
    """Find direct historical journeys between two stations."""
    # 1. Look up stations and snapshot provenance
    origin_station = db.scalar(select(Station).filter(Station.id == origin_station_id))
    destination_station = db.scalar(select(Station).filter(Station.id == destination_station_id))

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )

    if not origin_station or not destination_station or not snapshot:
        return []

    source = db.scalar(select(DataSource).filter(DataSource.id == snapshot.source_id))
    if not source:
        return []

    provenance = ProvenanceInfo(
        snapshot_id=snapshot.id,
        source_name=source.name,
        retrieved_at=snapshot.retrieved_at,
    )

    orig_stop = aliased(TrainStopObservation)
    dest_stop = aliased(TrainStopObservation)

    # 2. Query for direct journeys
    query = (
        select(orig_stop, dest_stop, TrainObservation, Train)
        .join(
            dest_stop,
            (orig_stop.train_id == dest_stop.train_id)
            & (orig_stop.snapshot_id == dest_stop.snapshot_id),
        )
        .join(
            TrainObservation,
            (orig_stop.train_id == TrainObservation.train_id)
            & (orig_stop.snapshot_id == TrainObservation.snapshot_id),
        )
        .join(Train, Train.id == TrainObservation.train_id)
        .filter(
            orig_stop.snapshot_id == timetable_snapshot_id,
            orig_stop.station_id == origin_station_id,
            dest_stop.station_id == destination_station_id,
            orig_stop.stop_sequence < dest_stop.stop_sequence,
        )
        # Order to ensure we pick the earliest occurrence if a train visits multiple times
        .order_by(orig_stop.stop_sequence.asc(), dest_stop.stop_sequence.asc())
    )

    results = db.execute(query).all()

    # 3. Deduplicate and construct options
    seen_train_ids = set()
    options = []

    for o_stop, d_stop, t_obs, t in results:
        if t.id in seen_train_ids:
            continue
        seen_train_ids.add(t.id)

        # Time calculation
        orig_mins = _parse_time_to_minutes(o_stop.departure_time, o_stop.source_day)
        dest_mins = _parse_time_to_minutes(d_stop.arrival_time, d_stop.source_day)

        duration = None
        confidence = TimingConfidence.MISSING_DATA

        # We also need to ensure dest >= orig in source day as a baseline sanity check
        is_temporally_sane = True
        if (
            d_stop.source_day is not None
            and o_stop.source_day is not None
            and d_stop.source_day < o_stop.source_day
        ):
            is_temporally_sane = False

        if orig_mins is not None and dest_mins is not None and is_temporally_sane:
            calc_duration = dest_mins - orig_mins
            if calc_duration >= 0:
                duration = calc_duration
                confidence = TimingConfidence.HIGH

        stops_count = d_stop.stop_sequence - o_stop.stop_sequence

        # Create unique ID for the journey
        raw_id = f"{timetable_snapshot_id}_{t.number}_{o_stop.station_id}_{d_stop.station_id}"
        journey_id = hashlib.sha256(raw_id.encode()).hexdigest()[:12]

        leg = JourneyLeg(
            train_number=t.number,
            train_name=t_obs.name,
            train_type=t_obs.type,
            origin_station=origin_station.code,
            destination_station=destination_station.code,
            departure_time=o_stop.departure_time,
            arrival_time=d_stop.arrival_time,
            source_day_offset=o_stop.source_day,
            duration_minutes=duration,
        )

        option = JourneyOption(
            journey_id=journey_id,
            type=JourneyType.DIRECT,
            legs=[leg],
            total_duration_minutes=duration,
            timing_confidence=confidence,
            number_of_stops=stops_count,
            provenance=provenance,
        )
        options.append(option)

    # 4. Deterministic Ordering
    def sort_key(opt: JourneyOption) -> tuple[Any, ...]:
        # 1. departure timing when available
        dep_val = float("inf")
        if opt.legs[0].departure_time and opt.legs[0].source_day_offset is not None:
            mins = _parse_time_to_minutes(opt.legs[0].departure_time, opt.legs[0].source_day_offset)
            if mins is not None:
                dep_val = mins

        # 2. duration when available
        dur_val = float("inf")
        if opt.total_duration_minutes is not None:
            dur_val = opt.total_duration_minutes

        # 3. train number
        return (dep_val, dur_val, opt.legs[0].train_number)

    options.sort(key=sort_key)
    return options
