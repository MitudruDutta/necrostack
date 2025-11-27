"""ExportSummary organ: DATA_TRANSFORMED → print summary."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class ExportSummary(Organ):
    """Handles DATA_TRANSFORMED events and prints a summary.
    
    Final stage of the ETL pipeline that outputs the transformation results.
    """

    listens_to = ["DATA_TRANSFORMED"]

    def __init__(self, name: str | None = None, output_callback: callable = None):
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
                summary_lines.append(
                    f"  {field}: min={stats['min']:.2f}, max={stats['max']:.2f}, "
                    f"avg={stats['avg']:.2f}, sum={stats['sum']:.2f}"
                )

        summary = "\n".join(summary_lines)
        self.last_summary = summary

        if self.output_callback:
            self.output_callback(summary)
        else:
            print(summary)

        return None
