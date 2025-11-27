"""ExtractCSV organ: ETL_START → RAW_DATA_LOADED."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class ExtractCSV(Organ):
    """Handles ETL_START events and emits RAW_DATA_LOADED.
    
    Extracts CSV data from the event payload and loads it as raw records.
    """

    listens_to = ["ETL_START"]

    def handle(self, event: Event) -> Event:
        """Extract CSV data from the event payload.

        Args:
            event: The ETL_START event with CSV data in payload.

        Returns:
            A RAW_DATA_LOADED event with parsed records.
        """
        csv_data = event.payload.get("csv_data", "")
        source_name = event.payload.get("source_name", "unknown")

        # Parse CSV data into records
        stripped_data = csv_data.strip()
        if not stripped_data:
            return Event(
                event_type="RAW_DATA_LOADED",
                payload={
                    "source_name": source_name,
                    "headers": [],
                    "records": [],
                    "row_count": 0,
                },
            )
        
        lines = stripped_data.split("\n")

        headers = [h.strip() for h in lines[0].split(",")]
        records = []

        for line in lines[1:]:
            if line.strip():
                values = [v.strip() for v in line.split(",")]
                record = dict(zip(headers, values))
                records.append(record)

        return Event(
            event_type="RAW_DATA_LOADED",
            payload={
                "source_name": source_name,
                "headers": headers,
                "records": records,
                "row_count": len(records),
            },
        )
