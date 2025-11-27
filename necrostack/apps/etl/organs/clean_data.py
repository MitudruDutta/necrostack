"""CleanData organ: RAW_DATA_LOADED → DATA_CLEANED."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class CleanData(Organ):
    """Handles RAW_DATA_LOADED events and emits DATA_CLEANED.

    Cleans raw data by removing empty values and normalizing strings.
    """

    listens_to = ["RAW_DATA_LOADED"]

    def handle(self, event: Event) -> Event:
        """Clean the raw data records.

        Args:
            event: The RAW_DATA_LOADED event with raw records.

        Returns:
            A DATA_CLEANED event with cleaned records.
        """
        records = event.payload.get("records", [])
        source_name = event.payload.get("source_name", "unknown")
        headers = event.payload.get("headers", [])

        cleaned_records = []
        removed_count = 0

        for record in records:
            # Skip records with any empty values
            if any(v == "" or v is None for v in record.values()):
                removed_count += 1
                continue

            # Normalize string values (strip whitespace, lowercase)
            cleaned_record = {}
            for key, value in record.items():
                if isinstance(value, str):
                    cleaned_record[key] = value.strip().lower()
                else:
                    cleaned_record[key] = value
            cleaned_records.append(cleaned_record)

        return Event(
            event_type="DATA_CLEANED",
            payload={
                "source_name": source_name,
                "headers": headers,
                "records": cleaned_records,
                "row_count": len(cleaned_records),
                "removed_count": removed_count,
            },
        )
