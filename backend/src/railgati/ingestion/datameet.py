"""Datameet GeoJSON parser."""

import json
from collections.abc import Generator
from pathlib import Path

from railgati.ingestion.schema import ParsedSchedule, ParsedStation, ParsedTrain


class DatameetParser:
    """Parses Datameet railways GeoJSON dataset."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def parse(self) -> Generator[ParsedStation, None, None]:
        """Parse the JSON file and yield normalized station records."""
        with open(self.file_path, encoding="utf-8") as f:
            data = json.load(f)

        if "features" not in data:
            raise ValueError("Invalid GeoJSON: missing 'features' array.")

        for i, feature in enumerate(data["features"]):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})

            # Normalization
            code = str(props.get("code", "")).strip().upper()
            name = str(props.get("name", "")).strip()

            state = props.get("state")
            if state is not None:
                state = str(state).strip()

            zone = props.get("zone")
            if zone is not None:
                zone = str(zone).strip()

            latitude = None
            longitude = None

            if geom and geom.get("type") == "Point":
                coords = geom.get("coordinates")
                if coords and len(coords) >= 2:
                    try:
                        # GeoJSON is [longitude, latitude]
                        longitude = float(coords[0])
                        latitude = float(coords[1])
                    except (ValueError, TypeError):
                        pass

            yield ParsedStation(
                source_index=i,
                code=code,
                name=name,
                state=state,
                zone=zone,
                latitude=latitude,
                longitude=longitude,
            )

    def parse_trains(self) -> Generator[ParsedTrain, None, None]:
        """Parse the trains JSON file and yield normalized train records."""
        with open(self.file_path, encoding="utf-8") as f:
            data = json.load(f)

        if "features" not in data:
            raise ValueError("Invalid GeoJSON: missing 'features' array.")

        for i, feature in enumerate(data["features"]):
            props = feature.get("properties", {})

            number = str(props.get("number", "")).strip()
            name = str(props.get("name", "")).strip()
            type_val = props.get("type")
            return_train = props.get("return_train")

            if type_val:
                type_val = str(type_val).strip()
            if return_train:
                return_train = str(return_train).strip()

            # Handle "None" as a string if any
            if type_val == "None":
                type_val = None
            if return_train == "None":
                return_train = None

            yield ParsedTrain(
                source_index=i,
                number=number,
                name=name,
                type=type_val,
                return_train_number=return_train,
            )

    def parse_schedules(self) -> Generator[ParsedSchedule, None, None]:
        """Parse the schedules JSON file and yield normalized schedule records."""
        with open(self.file_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Invalid schedules JSON: expected an array.")

        for record in data:
            source_id = record.get("id")
            train_number = str(record.get("train_number", "")).strip()
            station_code = str(record.get("station_code", "")).strip().upper()

            arrival_time = record.get("arrival")
            if arrival_time and str(arrival_time).strip() != "None":
                arrival_time = str(arrival_time).strip()
            else:
                arrival_time = None

            departure_time = record.get("departure")
            if departure_time and str(departure_time).strip() != "None":
                departure_time = str(departure_time).strip()
            else:
                departure_time = None

            day = record.get("day")
            # day can be None in the source
            if day is not None:
                try:
                    day = int(day)
                except (ValueError, TypeError):
                    day = None

            yield ParsedSchedule(
                source_id=source_id,
                train_number=train_number,
                station_code=station_code,
                arrival_time=arrival_time,
                departure_time=departure_time,
                day=day,
            )
