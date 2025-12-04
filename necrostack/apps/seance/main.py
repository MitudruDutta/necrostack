"""Séance demo application entrypoint.

This demo showcases the NecroStack event-driven architecture through a
mystical séance simulation. The event chain flows as:

    SUMMON_RITUAL → SPIRIT_APPEARED → ANSWER_GENERATED → OMEN_REVEALED → output

Usage:
    python -m necrostack.apps.seance.main
"""

import asyncio

from necrostack.apps.seance.organs import (
    AskQuestion,
    InterpretResponse,
    ManifestEffect,
    SummonSpirit,
)
from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.spine import Spine, SpineStats


async def run_seance(
    spirit_name: str = "Ancient One",
    ritual: str = "Midnight Invocation",
    question: str = "What wisdom do you bring?",
) -> SpineStats:
    """Run a complete séance session."""
    backend = InMemoryBackend()
    spine: Spine | None = None

    def stop_spine() -> None:
        if spine is not None:
            spine.stop()

    organs = [
        SummonSpirit(),
        AskQuestion(),
        InterpretResponse(),
        ManifestEffect(on_complete=stop_spine),
    ]

    spine = Spine(organs=organs, backend=backend)

    start_event = Event(
        event_type="SUMMON_RITUAL",
        payload={
            "ritual": ritual,
            "spirit_name": spirit_name,
            "question": question,
        },
    )

    return await spine.run(start_event)


def main() -> None:
    """Main entry point for the Séance demo."""
    print("🕯️  Beginning the Séance... 🕯️\n")
    stats = asyncio.run(run_seance())
    print(f"\n✨ Séance complete: {stats.events_processed} events processed")


if __name__ == "__main__":
    main()
