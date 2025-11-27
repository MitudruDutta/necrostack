"""ManifestEffect organ: OMEN_REVEALED → print output."""

from collections.abc import Callable
from typing import Any

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class ManifestEffect(Organ):
    """Handles OMEN_REVEALED events and prints the final output."""

    listens_to = ["OMEN_REVEALED"]

    def __init__(self, name: str | None = None, output_callback: Callable[..., Any] | None = None):
        """Initialize ManifestEffect.

        Args:
            name: Optional name for the organ.
            output_callback: Optional callback for output (useful for testing).
                           If None, prints to stdout.
        """
        super().__init__(name)
        self._output_callback = output_callback or print
        self.last_output: str | None = None

    def handle(self, event: Event) -> None:
        """Manifest the omen's effect by printing the result.

        Args:
            event: The OMEN_REVEALED event with the final omen.

        Returns:
            None (terminal organ in the chain).
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
