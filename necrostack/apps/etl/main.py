"""ETL demo application entrypoint.

This demo showcases the NecroStack event-driven architecture through a
simple ETL (Extract, Transform, Load) pipeline. The event chain flows as:

    ETL_START → RAW_DATA_LOADED → DATA_CLEANED → DATA_TRANSFORMED → summary output

Usage:
    python -m necrostack.apps.etl.main
"""

import asyncio
from typing import Callable, Optional

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.spine import Spine

from necrostack.apps.etl.organs import (
    ExtractCSV,
    CleanData,
    TransformData,
    ExportSummary,
)


# Embedded sample CSV data for the demo
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
    output_callback: Optional[Callable[[str], None]] = None,
) -> ExportSummary:
    """Run a complete ETL pipeline.

    Args:
        csv_data: CSV data to process.
        source_name: Name of the data source.
        output_callback: Optional callback for capturing output (useful for testing).

    Returns:
        The ExportSummary organ instance (for testing access to last_summary).
    """
    # Create the backend
    backend = InMemoryBackend()

    # Create organs in the order they should be invoked
    export_summary = ExportSummary(output_callback=output_callback)
    organs = [
        ExtractCSV(),
        CleanData(),
        TransformData(),
        export_summary,
    ]

    # Create the Spine dispatcher
    spine = Spine(organs=organs, backend=backend)

    # Create the initial event
    start_event = Event(
        event_type="ETL_START",
        payload={
            "csv_data": csv_data,
            "source_name": source_name,
        },
    )

    # Run the ETL pipeline
    await spine.run(start_event)

    return export_summary


def main() -> None:
    """Main entry point for the ETL demo."""
    print("📊 Starting ETL Pipeline... 📊\n")
    asyncio.run(run_etl())


if __name__ == "__main__":
    main()
