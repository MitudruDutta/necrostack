"""Séance demo application entrypoint.

This demo showcases the NecroStack event-driven architecture through a
mystical séance simulation. The event chain flows as:

    SUMMON_RITUAL → SPIRIT_APPEARED → ANSWER_GENERATED → OMEN_REVEALED → output

Usage:
    python -m necrostack.apps.seance.main
"""

import asyncio

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.spine import Spine

from necrostack.apps.seance.organs import (
    SummonSpirit,
    AskQuestion,
    InterpretResponse,
    ManifestEffect,
)


async def run_seance(
    spirit_name: str = "Ancient One",
    ritual: str = "Midnight Invocation",
    question: str = "What wisdom do you bring?",
) -> None:
    """Run a complete séance session.

    Args:
        spirit_name: Name of the spirit to summon.
        ritual: Name of the ritual being performed.
        question: Question to ask the spirit.
    """
    # Create the backend
    backend = InMemoryBackend()

    # Create organs in the order they should be invoked
    organs = [
        SummonSpirit(),
        AskQuestion(),
        InterpretResponse(),
        ManifestEffect(),
    ]

    # Create the Spine dispatcher
    spine = Spine(organs=organs, backend=backend)

    # Create the initial event
    start_event = Event(
        event_type="SUMMON_RITUAL",
        payload={
            "ritual": ritual,
            "spirit_name": spirit_name,
            "question": question,
        },
    )

    # Run the séance
    await spine.run(start_event)


def main() -> None:
    """Main entry point for the Séance demo."""
    print("🕯️  Beginning the Séance... 🕯️")
    asyncio.run(run_seance())


if __name__ == "__main__":
    main()
