"""TransformData organ: DATA_CLEANED → DATA_TRANSFORMED."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class TransformData(Organ):
    """Handles DATA_CLEANED events and emits DATA_TRANSFORMED.

    Transforms cleaned data by computing aggregations and statistics.
    """

    listens_to = ["DATA_CLEANED"]

    def handle(self, event: Event) -> Event:
        """Transform the cleaned data with aggregations.

        Args:
            event: The DATA_CLEANED event with cleaned records.

        Returns:
            A DATA_TRANSFORMED event with transformed data and statistics.
        """
        records = event.payload.get("records", [])
        source_name = event.payload.get("source_name", "unknown")
        headers = event.payload.get("headers", [])

        # Compute basic statistics for numeric fields
        numeric_stats = {}
        for header in headers:
            values = []
            for record in records:
                try:
                    val = float(record.get(header, ""))
                    values.append(val)
                except (ValueError, TypeError):
                    continue

            if values:
                total = sum(values)
                numeric_stats[header] = {
                    "min": min(values),
                    "max": max(values),
                    "sum": total,
                    "avg": total / len(values),
                    "count": len(values),
                }

        return Event(
            event_type="DATA_TRANSFORMED",
            payload={
                "source_name": source_name,
                "headers": headers,
                "records": records,
                "row_count": len(records),
                "numeric_stats": numeric_stats,
            },
        )
