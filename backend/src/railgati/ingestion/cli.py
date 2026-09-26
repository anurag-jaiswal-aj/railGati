"""CLI for the data ingestion pipeline."""

import argparse
from pathlib import Path

from railgati.db import get_session_factory
from railgati.ingestion.datameet import DatameetParser
from railgati.ingestion.pipeline import Pipeline


def main() -> None:
    """Run the ingestion CLI."""
    parser = argparse.ArgumentParser(description="RailGati Data Ingestion Pipeline")
    parser.add_argument(
        "--source",
        choices=["datameet"],
        required=True,
        help="The data source to ingest",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the raw data file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline without committing to the database",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{args.input}' does not exist.")
        return

    session_factory = get_session_factory()

    if args.source == "datameet":
        data_parser = DatameetParser(input_path)
        with session_factory() as db:
            pipeline = Pipeline(db, dry_run=args.dry_run)
            result = pipeline.run(str(input_path), data_parser.parse())
            result.print_report()


if __name__ == "__main__":
    main()
