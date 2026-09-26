"""Data structures for the ingestion pipeline."""

from dataclasses import dataclass, field


@dataclass
class ParsedStation:
    """A station record extracted from a raw source and normalized."""

    code: str
    name: str
    state: str | None = None
    zone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class IngestionResult:
    """The result of an ingestion run."""

    source_name: str
    snapshot_id: int | None
    records_read: int = 0
    records_parsed: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    duplicates: int = 0
    invalid_coordinates: int = 0
    missing_required_fields: int = 0
    warnings: list[str] = field(default_factory=list)
    status: str = "PENDING"

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []

    def print_report(self) -> None:
        """Print a clear report of the ingestion run."""
        print("=" * 50)
        print("DATA QUALITY REPORT")
        print("=" * 50)
        print(f"Source:                  {self.source_name}")
        print(f"Snapshot:                {self.snapshot_id}")
        print(f"Status:                  {self.status}")
        print("-" * 50)
        print(f"Records read:            {self.records_read}")
        print(f"Records parsed:          {self.records_parsed}")
        print(f"Records accepted:        {self.records_accepted}")
        print(f"Records rejected:        {self.records_rejected}")
        print("-" * 50)
        print(f"Duplicates:              {self.duplicates}")
        print(f"Invalid coordinates:     {self.invalid_coordinates}")
        print(f"Missing required fields: {self.missing_required_fields}")
        if self.warnings:
            print("-" * 50)
            print("Warnings:")
            for w in self.warnings[:10]:
                print(f"  - {w}")
            if len(self.warnings) > 10:
                print(f"  ... and {len(self.warnings) - 10} more.")
        print("=" * 50)
