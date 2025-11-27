"""InterpretResponse organ: ANSWER_GENERATED → OMEN_REVEALED."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class InterpretResponse(Organ):
    """Handles ANSWER_GENERATED events and emits OMEN_REVEALED."""

    listens_to = ["ANSWER_GENERATED"]

    def handle(self, event: Event) -> Event:
        """Interpret the spirit's answer and reveal an omen.

        Args:
            event: The ANSWER_GENERATED event with the spirit's response.

        Returns:
            An OMEN_REVEALED event with the interpreted omen.
        """
        spirit_name = event.payload.get("spirit_name", "Unknown Spirit")
        answer = event.payload.get("answer", "")

        # TODO: Replace with actual interpretation logic that analyzes the answer content.
        # Currently a placeholder that incorporates the answer into the interpretation.
        omen = f"The words of {spirit_name} foretell: A great change approaches."
        interpretation = f"The spirits suggest patience and vigilance. (Based on: {answer[:50]}{'...' if len(answer) > 50 else ''})" if answer else "The spirits suggest patience and vigilance."

        return Event(
            event_type="OMEN_REVEALED",
            payload={
                "spirit_name": spirit_name,
                "original_answer": answer,
                "omen": omen,
                "interpretation": interpretation,
            },
        )
