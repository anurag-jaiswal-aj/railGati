"""CLI for the data ingestion pipeline."""

import argparse
import json
from pathlib import Path

from railgati.db import get_session_factory
from railgati.ingestion.datameet import DatameetParser
from railgati.ingestion.pipeline import Pipeline
from railgati.ingestion.timetable_pipeline import TimetablePipeline


def main() -> None:
    """Run the ingestion CLI."""
    parser = argparse.ArgumentParser(description="RailGati Data Ingestion Pipeline")
    parser.add_argument(
        "--type",
        choices=["stations", "timetable"],
        default="stations",
        help="Type of data to ingest",
    )
    parser.add_argument(
        "--source",
        choices=["datameet"],
        required=True,
        help="The data source to ingest",
    )
    parser.add_argument(
        "--input",
        help="Path to the raw stations data file",
    )
    parser.add_argument(
        "--trains",
        help="Path to the raw trains data file (for timetable)",
    )
    parser.add_argument(
        "--schedules",
        help="Path to the raw schedules data file (for timetable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline without committing to the database",
    )

    args = parser.parse_args()

    session_factory = get_session_factory()

    if args.type == "stations":
        if not args.input:
            parser.error("--input is required for stations ingestion")
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input file '{args.input}' does not exist.")
            return

        if args.source == "datameet":
            data_parser = DatameetParser(input_path)
            with session_factory() as db:
                pipeline = Pipeline(db, dry_run=args.dry_run)
                result = pipeline.run(str(input_path), data_parser.parse())
                result.print_report()

                if result.rejections and result.snapshot_id:
                    rejections_file = (
                        input_path.parent.parent
                        / "processed"
                        / f"snapshot_{result.snapshot_id}_rejections.json"
                    )
                    rejections_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(rejections_file, "w") as f:
                        json.dump(result.rejections, f, indent=2)
                    print(f"Detailed rejections written to {rejections_file}")

    elif args.type == "timetable":
        if not args.trains or not args.schedules:
            parser.error("--trains and --schedules are required for timetable ingestion")
        trains_path = Path(args.trains)
        schedules_path = Path(args.schedules)

        if not trains_path.exists():
            print(f"Error: Trains file '{args.trains}' does not exist.")
            return
        if not schedules_path.exists():
            print(f"Error: Schedules file '{args.schedules}' does not exist.")
            return

        if args.source == "datameet":
            trains_parser = DatameetParser(trains_path)
            schedules_parser = DatameetParser(schedules_path)

            with session_factory() as db:
                pipeline = TimetablePipeline(db, dry_run=args.dry_run)
                result = pipeline.run_timetable(
                    str(trains_path),
                    str(schedules_path),
                    trains_parser.parse_trains(),
                    schedules_parser.parse_schedules(),
                )
                result.print_report()

                if result.rejections and result.snapshot_id:
                    rejections_file = (
                        trains_path.parent.parent
                        / "processed"
                        / f"timetable_snapshot_{result.snapshot_id}_rejections.json"
                    )
                    rejections_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(rejections_file, "w") as f:
                        json.dump(result.rejections, f, indent=2)
                    print(f"Detailed rejections written to {rejections_file}")


if __name__ == "__main__":
    main()

