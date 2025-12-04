"""ExportSummary organ: DATA_TRANSFORMED → print summary."""

import logging
from collections.abc import Callable
from typing import Any

from necrostack.core.event import Event
from necrostack.core.organ import Organ

logger = logging.getLogger(__name__)


class ExportSummary(Organ):
    """Handles DATA_TRANSFORMED events and prints a summary.

    This is a terminal organ that signals completion via an on_complete callback
    or by emitting a completion event, rather than directly controlling the spine.

    Completion Signaling:
        The organ supports dual completion signaling for compatibility:
        1. If on_complete callback is provided, it is called first
        2. Else if spine_ref is provided, spine_ref[0].stop() is called
        3. An ETL_COMPLETE event is always emitted for coordinator patterns

        If the callback or stop() fails, the exception is re-raised after logging
        to ensure callers/coordinators can detect the failure.
    """

    listens_to = ["DATA_TRANSFORMED"]

    def __init__(
        self,
        name: str | None = None,
        output_callback: Callable[[str], None] | None = None,
        on_complete: Callable[[], Any] | None = None,
        spine_ref: list[Any] | None = None,
    ):
        """Initialize the ExportSummary organ.

        Args:
            name: Optional name for the organ.
            output_callback: Optional callback for capturing output (useful for testing).
            on_complete: Optional callback invoked when processing completes.
                        Preferred over spine_ref for signaling completion.
            spine_ref: Deprecated. Use on_complete callback instead.
                      If provided, expects a list where spine_ref[0] has a stop() method.
        """
        super().__init__(name)
        self.output_callback = output_callback
        self._on_complete = on_complete
        self._spine_ref = spine_ref
        self.last_summary: str | None = None

    def handle(self, event: Event) -> Event | None:
        """Export and print the data summary.

        Returns:
            An ETL_COMPLETE event to signal completion to the coordinator.
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
            for stat_field, stats in numeric_stats.items():
                if not isinstance(stats, dict):
                    continue

                stat_values = {}
                for key in ("min", "max", "avg", "sum"):
                    val = stats.get(key)
                    if isinstance(val, (int, float)):
                        stat_values[key] = f"{val:.2f}"
                    else:
                        try:
                            stat_values[key] = f"{float(val):.2f}"
                        except (TypeError, ValueError):
                            stat_values[key] = "N/A"

                summary_lines.append(
                    f"  {stat_field}: min={stat_values['min']}, max={stat_values['max']}, "
                    f"avg={stat_values['avg']}, sum={stat_values['sum']}"
                )

        summary = "\n".join(summary_lines)
        self.last_summary = summary

        if self.output_callback:
            self.output_callback(summary)
        else:
            print(summary)

        # Signal completion - prefer callback over direct spine control
        # Intentional dual signaling: callback/stop AND event emission for compatibility
        if self._on_complete is not None:
            try:
                self._on_complete()
            except Exception as e:
                logger.exception(f"on_complete callback failed: {e}")
                raise
        elif self._spine_ref is not None and len(self._spine_ref) > 0 and self._spine_ref[0]:
            # Fallback to spine_ref with defensive checks
            try:
                stop_method = getattr(self._spine_ref[0], "stop", None)
                if callable(stop_method):
                    stop_method()
            except Exception as e:
                logger.exception(f"Failed to stop spine: {e}")
                raise

        # Emit completion event for coordinator pattern
        return Event(
            event_type="ETL_COMPLETE",
            payload={"source_name": source_name, "row_count": row_count},
        )
