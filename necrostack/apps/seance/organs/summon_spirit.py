"""SummonSpirit organ: SUMMON_RITUAL → SPIRIT_APPEARED."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class SummonSpirit(Organ):
    """Handles SUMMON_RITUAL events and emits SPIRIT_APPEARED."""

    listens_to = ["SUMMON_RITUAL"]

    def handle(self, event: Event) -> Event:
        """Summon a spirit from the ritual.

        Args:
            event: The SUMMON_RITUAL event with optional ritual details.

        Returns:
            A SPIRIT_APPEARED event with spirit information.
        """
        ritual_name = event.payload.get("ritual", "unknown ritual")
        spirit_name = event.payload.get("spirit_name", "Ancient One")

        return Event(
            event_type="SPIRIT_APPEARED",
            payload={
                "spirit_name": spirit_name,
                "summoned_by": ritual_name,
                "message": f"The spirit '{spirit_name}' has been summoned through {ritual_name}.",
            },
        )
