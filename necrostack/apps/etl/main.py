"""ETL demo application entrypoint.

This demo showcases the NecroStack event-driven architecture through a
simple ETL (Extract, Transform, Load) pipeline. The event chain flows as:

    ETL_START → RAW_DATA_LOADED → DATA_CLEANED → DATA_TRANSFORMED → summary output

Usage:
    python -m necrostack.apps.etl.main
"""

import asyncio
from collections.abc import Callable

from necrostack.apps.etl.organs import (
    CleanData,
    ExportSummary,
    ExtractCSV,
    TransformData,
)
from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.spine import Spine, SpineStats

SAMPLE_CSV_DATA = """name,age,salary,department
Alice,30,75000,Engineering
Bob,25,55000,Marketing
Charlie,35,85000,Engineering
Diana,28,62000,Sales
Eve,32,78000,Engineering
Frank,,45000,Marketing
Grace,29,67000,Sales
Henry,40,95000,Engineering
Ivy,27,58000,Marketing
Jack,33,72000,Sales
"""


async def run_etl(
    csv_data: str = SAMPLE_CSV_DATA,
    source_name: str = "employees.csv",
    output_callback: Callable[[str], None] | None = None,
) -> tuple[SpineStats, ExportSummary]:
    """Run a complete ETL pipeline.

    Args:
        csv_data: CSV string data to process.
        source_name: Name identifier for the data source.
        output_callback: Optional callback for capturing summary output.

    Returns:
        A tuple of (SpineStats, ExportSummary):
        - SpineStats: Processing metrics including events_processed (int),
          events_emitted (int), handler_errors (dict), and backend_errors (int).
        - ExportSummary: The organ instance with last_summary (str) containing
          the formatted output text with row counts and numeric statistics.

    Example:
        stats, summary = await run_etl()
        print(f"Processed {stats.events_processed} events")
        print(summary.last_summary)  # "=== ETL Summary for 'employees.csv' ===..."
    """
    backend = InMemoryBackend()
    spine: Spine | None = None

    def stop_spine() -> None:
        if spine is not None:
            spine.stop()

    export_summary = ExportSummary(output_callback=output_callback, on_complete=stop_spine)
    organs = [
        ExtractCSV(),
        CleanData(),
        TransformData(),
        export_summary,
    ]

    spine = Spine(organs=organs, backend=backend)

    start_event = Event(
        event_type="ETL_START",
        payload={
            "csv_data": csv_data,
            "source_name": source_name,
        },
    )

    stats = await spine.run(start_event)
    return stats, export_summary


def main() -> None:
    """Main entry point for the ETL demo."""
    print("📊 Starting ETL Pipeline... 📊\n")
    stats, _ = asyncio.run(run_etl())
    print(f"\n✅ ETL complete: {stats.events_processed} events processed")


if __name__ == "__main__":
    main()
