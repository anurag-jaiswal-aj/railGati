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


def find_one_transfer_journeys(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    destination_station_id: int,
    minimum_transfer_minutes: int = 120,
    maximum_layover_minutes: int = 1440,
) -> list[JourneyOption]:
    """Find one-transfer historical journeys between two stations."""
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

    t_a_orig = aliased(TrainStopObservation)
    t_a_trans = aliased(TrainStopObservation)
    t_b_trans = aliased(TrainStopObservation)
    t_b_dest = aliased(TrainStopObservation)
    train_a = aliased(Train)
    train_b = aliased(Train)
    t_a_obs = aliased(TrainObservation)
    t_b_obs = aliased(TrainObservation)
    transfer_station_model = aliased(Station)

    query = (
        select(
            t_a_orig,
            t_a_trans,
            t_a_obs,
            train_a,
            t_b_trans,
            t_b_dest,
            t_b_obs,
            train_b,
            transfer_station_model,
        )
        .join(
            t_a_trans,
            (t_a_orig.train_id == t_a_trans.train_id)
            & (t_a_orig.snapshot_id == t_a_trans.snapshot_id),
        )
        .join(
            t_b_trans,
            (t_a_trans.station_id == t_b_trans.station_id)
            & (t_a_trans.snapshot_id == t_b_trans.snapshot_id),
        )
        .join(
            t_b_dest,
            (t_b_trans.train_id == t_b_dest.train_id)
            & (t_b_trans.snapshot_id == t_b_dest.snapshot_id),
        )
        .join(
            t_a_obs,
            (t_a_orig.train_id == t_a_obs.train_id) & (t_a_orig.snapshot_id == t_a_obs.snapshot_id),
        )
        .join(
            t_b_obs,
            (t_b_dest.train_id == t_b_obs.train_id) & (t_b_dest.snapshot_id == t_b_obs.snapshot_id),
        )
        .join(train_a, train_a.id == t_a_orig.train_id)
        .join(train_b, train_b.id == t_b_dest.train_id)
        .join(transfer_station_model, transfer_station_model.id == t_a_trans.station_id)
        .filter(
            t_a_orig.snapshot_id == timetable_snapshot_id,
            t_a_orig.station_id == origin_station_id,
            t_b_dest.station_id == destination_station_id,
            t_a_orig.stop_sequence < t_a_trans.stop_sequence,
            t_b_trans.stop_sequence < t_b_dest.stop_sequence,
            t_a_orig.train_id != t_b_dest.train_id,
            t_a_trans.station_id != origin_station_id,
            t_a_trans.station_id != destination_station_id,
        )
        .order_by(
            t_a_orig.stop_sequence.asc(),
            t_a_trans.stop_sequence.asc(),
            t_b_trans.stop_sequence.asc(),
            t_b_dest.stop_sequence.asc(),
        )
    )

    results = db.execute(query).all()

    seen_paths = set()
    options = []

    for o_stop, a_trans, obs_a, t_a, b_trans, d_stop, obs_b, t_b, transfer_st in results:
        path_key = (t_a.id, a_trans.stop_sequence, transfer_st.id, t_b.id, b_trans.stop_sequence)
        if path_key in seen_paths:
            continue

        a_arr_mins = _parse_time_to_minutes(a_trans.arrival_time, a_trans.source_day)
        b_dep_mins = _parse_time_to_minutes(b_trans.departure_time, b_trans.source_day)

        if a_arr_mins is None or b_dep_mins is None:
            continue

        layover = b_dep_mins - a_arr_mins
        if layover < minimum_transfer_minutes or layover > maximum_layover_minutes:
            continue

        seen_paths.add(path_key)

        a_dep_mins = _parse_time_to_minutes(o_stop.departure_time, o_stop.source_day)
        b_arr_mins = _parse_time_to_minutes(d_stop.arrival_time, d_stop.source_day)

        leg1_duration = None
        if (
            a_dep_mins is not None
            and a_arr_mins is not None
            and a_trans.source_day is not None
            and o_stop.source_day is not None
            and a_trans.source_day >= o_stop.source_day
        ):
            dur = a_arr_mins - a_dep_mins
            if dur >= 0:
                leg1_duration = dur

        leg2_duration = None
        if (
            b_dep_mins is not None
            and b_arr_mins is not None
            and d_stop.source_day is not None
            and b_trans.source_day is not None
            and d_stop.source_day >= b_trans.source_day
        ):
            dur = b_arr_mins - b_dep_mins
            if dur >= 0:
                leg2_duration = dur

        total_duration = None
        confidence = TimingConfidence.MISSING_DATA
        if leg1_duration is not None and leg2_duration is not None:
            total_duration = leg1_duration + layover + leg2_duration
            confidence = TimingConfidence.HIGH

        stops_count = (a_trans.stop_sequence - o_stop.stop_sequence) + (
            d_stop.stop_sequence - b_trans.stop_sequence
        )

        leg1 = JourneyLeg(
            train_number=t_a.number,
            train_name=obs_a.name,
            train_type=obs_a.type,
            origin_station=origin_station.code,
            destination_station=transfer_st.code,
            departure_time=o_stop.departure_time,
            arrival_time=a_trans.arrival_time,
            source_day_offset=o_stop.source_day,
            duration_minutes=leg1_duration,
        )

        leg2 = JourneyLeg(
            train_number=t_b.number,
            train_name=obs_b.name,
            train_type=obs_b.type,
            origin_station=transfer_st.code,
            destination_station=destination_station.code,
            departure_time=b_trans.departure_time,
            arrival_time=d_stop.arrival_time,
            source_day_offset=b_trans.source_day,
            duration_minutes=leg2_duration,
        )

        raw_id = (
            f"{timetable_snapshot_id}_trans_{t_a.number}_{a_trans.stop_sequence}_"
            f"{transfer_st.id}_{t_b.number}_{b_trans.stop_sequence}"
        )
        journey_id = hashlib.sha256(raw_id.encode()).hexdigest()[:12]

        option = JourneyOption(
            journey_id=journey_id,
            type=JourneyType.ONE_TRANSFER,
            legs=[leg1, leg2],
            total_duration_minutes=total_duration,
            timing_confidence=confidence,
            number_of_stops=stops_count,
            transfer_station=transfer_st.code,
            layover_minutes=layover,
            provenance=provenance,
        )
        options.append(option)

    def sort_key(opt: JourneyOption) -> tuple[Any, ...]:
        dur_val = (
            opt.total_duration_minutes if opt.total_duration_minutes is not None else float("inf")
        )
        dep_val = float("inf")
        if opt.legs[0].departure_time and opt.legs[0].source_day_offset is not None:
            mins = _parse_time_to_minutes(opt.legs[0].departure_time, opt.legs[0].source_day_offset)
            if mins is not None:
                dep_val = mins
        t_a_num = opt.legs[0].train_number
        trans_code = opt.transfer_station or ""
        t_b_num = opt.legs[1].train_number
        return (dur_val, dep_val, t_a_num, trans_code, t_b_num)

    options.sort(key=sort_key)
    return options


def compare_journeys(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    destination_station_id: int,
    max_transfers: int = 0,
    minimum_transfer_minutes: int = 120,
    maximum_layover_minutes: int = 1440,
) -> list[JourneyOption]:
    """Combine direct and optionally one-transfer historical journeys."""
    if max_transfers not in (0, 1):
        raise ValueError("max_transfers must be 0 or 1")

    options: list[JourneyOption] = []

    direct_opts = find_direct_journeys(
        db, timetable_snapshot_id, origin_station_id, destination_station_id
    )
    options.extend(direct_opts)

    if max_transfers == 1:
        transfer_opts = find_one_transfer_journeys(
            db,
            timetable_snapshot_id,
            origin_station_id,
            destination_station_id,
            minimum_transfer_minutes,
            maximum_layover_minutes,
        )
        options.extend(transfer_opts)

    def combined_sort_key(opt: JourneyOption) -> tuple[Any, ...]:
        # 1. total_duration_minutes (ASC, nulls last)
        dur_val = (
            opt.total_duration_minutes if opt.total_duration_minutes is not None else float("inf")
        )

        # 2. first departure time
        dep_val = float("inf")
        if opt.legs[0].departure_time and opt.legs[0].source_day_offset is not None:
            mins = _parse_time_to_minutes(opt.legs[0].departure_time, opt.legs[0].source_day_offset)
            if mins is not None:
                dep_val = float(mins)

        # 3. type (DIRECT before ONE_TRANSFER)
        type_val = 0 if opt.type == JourneyType.DIRECT else 1

        # 4. train numbers and journey id for deterministic tie-breaker
        t_a_num = opt.legs[0].train_number
        t_b_num = opt.legs[1].train_number if len(opt.legs) > 1 else ""

        return (dur_val, dep_val, type_val, t_a_num, t_b_num, opt.journey_id)

    options.sort(key=combined_sort_key)
    return options
