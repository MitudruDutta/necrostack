"""ExportSummary organ: DATA_TRANSFORMED → print summary."""

from collections.abc import Callable

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class ExportSummary(Organ):
    """Handles DATA_TRANSFORMED events and prints a summary.

    Final stage of the ETL pipeline that outputs the transformation results.
    """

    listens_to = ["DATA_TRANSFORMED"]

    def __init__(
        self,
        name: str | None = None,
        output_callback: Callable[[str], None] | None = None,
    ):
        """Initialize the ExportSummary organ.

        Args:
            name: Optional name for the organ.
            output_callback: Optional callback for capturing output (useful for testing).
        """
        super().__init__(name)
        self.output_callback = output_callback
        self.last_summary = None

    def handle(self, event: Event) -> None:
        """Export and print the data summary.

        Args:
            event: The DATA_TRANSFORMED event with transformed data.

        Returns:
            None (terminal organ in the pipeline).
        """
        source_name = event.payload.get("source_name", "unknown")
        row_count = event.payload.get("row_count", 0)
        headers = event.payload.get("headers", [])
        numeric_stats = event.payload.get("numeric_stats", {})

        summary_lines = [
            f"=== ETL Summary for '{source_name}' ===",
            f"Total rows processed: {row_count}",
            f"Columns: {', '.join(headers)}",
        ]

        if numeric_stats:
            summary_lines.append("\nNumeric Statistics:")
            for field, stats in numeric_stats.items():
                if not isinstance(stats, dict):
                    continue

                # Extract and validate each stat value
                stat_values = {}
                for key in ("min", "max", "avg", "sum"):
                    val = stats.get(key)
                    if isinstance(val, (int, float)):
                        stat_values[key] = f"{val:.2f}"
                    else:
                        # Try to coerce to float, otherwise use placeholder
                        try:
                            stat_values[key] = f"{float(val):.2f}"
                        except (TypeError, ValueError):
                            stat_values[key] = "N/A"

                summary_lines.append(
                    f"  {field}: min={stat_values['min']}, max={stat_values['max']}, "
                    f"avg={stat_values['avg']}, sum={stat_values['sum']}"
                )

        summary = "\n".join(summary_lines)
        self.last_summary = summary

        if self.output_callback:
            self.output_callback(summary)
        else:
            print(summary)
