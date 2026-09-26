"""Service for discovering reachable destinations."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from railgati.api.v1.schemas import TimingConfidence
from railgati.models.station import Station
from railgati.models.train import TrainStopObservation
from railgati.services.journey import _parse_time_to_minutes


class DirectDestinationResult(BaseModel):
    """Result model for a discovered direct destination."""

    station_id: int
    station_code: str
    fastest_duration_minutes: int | None
    direct_trains_count: int
    timing_confidence: TimingConfidence


def find_direct_destinations(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    max_duration_minutes: int | None = None,
) -> list[DirectDestinationResult]:
    """Find canonical stations directly reachable from the given origin."""

    orig_stop = aliased(TrainStopObservation)
    dest_stop = aliased(TrainStopObservation)

    query = (
        select(orig_stop, dest_stop, Station)
        .join(
            dest_stop,
            (orig_stop.train_id == dest_stop.train_id)
            & (orig_stop.snapshot_id == dest_stop.snapshot_id),
        )
        .join(Station, Station.id == dest_stop.station_id)
        .filter(
            orig_stop.snapshot_id == timetable_snapshot_id,
            orig_stop.station_id == origin_station_id,
            orig_stop.stop_sequence < dest_stop.stop_sequence,
            dest_stop.station_id != origin_station_id,
        )
    )

    results = db.execute(query).all()

    destinations: dict[int, dict[str, Any]] = {}

    for o_stop, d_stop, station in results:
        dest_id = station.id

        orig_mins = _parse_time_to_minutes(o_stop.departure_time, o_stop.source_day)
        dest_mins = _parse_time_to_minutes(d_stop.arrival_time, d_stop.source_day)

        duration = None
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

        if max_duration_minutes is not None and (
            duration is None or duration > max_duration_minutes
        ):
            continue

        if dest_id not in destinations:
            destinations[dest_id] = {
                "station": station,
                "fastest_duration": None,
                "qualifying_trains": set(),
            }

        dest_data = destinations[dest_id]
        dest_data["qualifying_trains"].add(o_stop.train_id)

        if duration is not None and (
            dest_data["fastest_duration"] is None or duration < dest_data["fastest_duration"]
        ):
            dest_data["fastest_duration"] = duration

    results_list = []
    for _, data in destinations.items():
        fastest = data["fastest_duration"]
        confidence = TimingConfidence.HIGH if fastest is not None else TimingConfidence.MISSING_DATA

        res = DirectDestinationResult(
            station_id=data["station"].id,
            station_code=data["station"].code,
            fastest_duration_minutes=fastest,
            direct_trains_count=len(data["qualifying_trains"]),
            timing_confidence=confidence,
        )
        results_list.append(res)

    def sort_key(res: DirectDestinationResult) -> tuple[Any, ...]:
        dur_val = (
            res.fastest_duration_minutes
            if res.fastest_duration_minutes is not None
            else float("inf")
        )
        return (dur_val, res.station_code)

    results_list.sort(key=sort_key)
    return results_list
