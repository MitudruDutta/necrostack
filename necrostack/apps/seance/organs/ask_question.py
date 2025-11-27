"""AskQuestion organ: SPIRIT_APPEARED → ANSWER_GENERATED."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class AskQuestion(Organ):
    """Handles SPIRIT_APPEARED events and emits ANSWER_GENERATED."""

    listens_to = ["SPIRIT_APPEARED"]

    def handle(self, event: Event) -> Event:
        """Ask the spirit a question and receive an answer.

        Args:
            event: The SPIRIT_APPEARED event with spirit information.

        Returns:
            An ANSWER_GENERATED event with the spirit's response.
        """
        spirit_name = event.payload.get("spirit_name", "Unknown Spirit")
        question = event.payload.get("question", "What wisdom do you bring?")

        # TODO: Replace with actual QA/generative function to produce dynamic answers.
        # Currently a placeholder that incorporates the question into the response.
        answer = (
            f"The {spirit_name} speaks in response to '{question}': "
            f"'The path you seek lies within shadows and light.'"
        )

        return Event(
            event_type="ANSWER_GENERATED",
            payload={
                "spirit_name": spirit_name,
                "question": question,
                "answer": answer,
            },
        )
