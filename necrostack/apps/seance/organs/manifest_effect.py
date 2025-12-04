"""ManifestEffect organ: OMEN_REVEALED → print output."""

import logging
from collections.abc import Callable
from typing import Any

from necrostack.core.event import Event
from necrostack.core.organ import Organ

logger = logging.getLogger(__name__)


class ManifestEffect(Organ):
    """Handles OMEN_REVEALED events and prints the final output.

    This is a terminal organ that signals completion via an on_complete callback
    or by emitting a completion event, rather than directly controlling the spine.
    """

    listens_to = ["OMEN_REVEALED"]

    def __init__(
        self,
        name: str | None = None,
        output_callback: Callable[..., Any] | None = None,
        on_complete: Callable[[], Any] | None = None,
        spine_ref: list[Any] | None = None,
    ):
        """Initialize ManifestEffect.

        Args:
            name: Optional name for the organ.
            output_callback: Optional callback for output (useful for testing).
            on_complete: Optional callback invoked when processing completes.
                        Preferred over spine_ref for signaling completion.
            spine_ref: Deprecated. Use on_complete callback instead.
                      If provided, expects a list where spine_ref[0] has a stop() method.
        """
        super().__init__(name)
        self._output_callback = output_callback or print
        self._on_complete = on_complete
        self._spine_ref = spine_ref
        self.last_output: str | None = None

    def handle(self, event: Event) -> Event:
        """Manifest the omen's effect by printing the result.

        Returns:
            A SEANCE_COMPLETE event to signal completion to the coordinator.
        """
        spirit_name = event.payload.get("spirit_name", "Unknown Spirit")
        omen = event.payload.get("omen", "No omen revealed")
        interpretation = event.payload.get("interpretation", "")

        output = (
            f"\n{'=' * 50}\n"
            f"🔮 SÉANCE COMPLETE 🔮\n"
            f"{'=' * 50}\n"
            f"Spirit: {spirit_name}\n"
            f"Omen: {omen}\n"
            f"Interpretation: {interpretation}\n"
            f"{'=' * 50}\n"
        )

        self.last_output = output
        self._output_callback(output)

        # Signal completion - prefer callback over direct spine control
        if self._on_complete is not None:
            try:
                self._on_complete()
            except Exception as e:
                logger.exception(f"on_complete callback failed: {e}")
        elif self._spine_ref is not None and len(self._spine_ref) > 0 and self._spine_ref[0]:
            # Fallback to spine_ref with defensive checks
            try:
                stop_method = getattr(self._spine_ref[0], "stop", None)
                if callable(stop_method):
                    stop_method()
            except Exception as e:
                logger.exception(f"Failed to stop spine: {e}")

        # Emit completion event for coordinator pattern
        return Event(
            event_type="SEANCE_COMPLETE",
            payload={"spirit_name": spirit_name, "omen": omen},
        )
