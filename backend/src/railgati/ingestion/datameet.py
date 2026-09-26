"""Datameet GeoJSON parser."""

import json
from collections.abc import Generator
from pathlib import Path

from railgati.ingestion.schema import ParsedStation


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

        for feature in data["features"]:
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
                code=code,
                name=name,
                state=state,
                zone=zone,
                latitude=latitude,
                longitude=longitude,
            )
