"""Integration tests for the Séance demo application.

Validates: Requirements 8.1 - Complete event chain execution
"""

import asyncio

import pytest

from necrostack.apps.seance.organs import (
    AskQuestion,
    InterpretResponse,
    ManifestEffect,
    SummonSpirit,
)
from necrostack.core.event import Event
from necrostack.core.spine import Spine


class StoppingBackend:
    """Backend that stops spine after processing events."""

    def __init__(self, spine_ref, max_events=10):
        self._queue = None
        self._events_returned = 0
        self._max_events = max_events
        self._spine_ref = spine_ref

    def _get_queue(self):
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    async def enqueue(self, event):
        await self._get_queue().put(event)

    async def pull(self, timeout=1.0):
        if self._events_returned >= self._max_events:
            if self._spine_ref[0]:
                self._spine_ref[0].stop()
            return None
        try:
            event = await asyncio.wait_for(self._get_queue().get(), timeout=timeout)
            self._events_returned += 1
            return event
        except TimeoutError:
            if self._spine_ref[0]:
                self._spine_ref[0].stop()
            return None

    async def ack(self, event):
        pass


@pytest.mark.asyncio
async def test_seance_complete_event_chain():
    """Test that the complete Séance event chain executes correctly.

    Event chain: SUMMON_RITUAL → SPIRIT_APPEARED → ANSWER_GENERATED → OMEN_REVEALED
    """
    # Track outputs
    outputs = []
    spine_ref = [None]

    # Create backend and organs
    backend = StoppingBackend(spine_ref, max_events=10)
    manifest = ManifestEffect(output_callback=outputs.append)

    organs = [
        SummonSpirit(),
        AskQuestion(),
        InterpretResponse(),
        manifest,
    ]

    spine = Spine(organs=organs, backend=backend)
    spine_ref[0] = spine

    # Create initial event
    start_event = Event(
        event_type="SUMMON_RITUAL",
        payload={
            "ritual": "Test Ritual",
            "spirit_name": "Test Spirit",
            "question": "What is the answer?",
        },
    )

    # Run the séance
    await spine.run(start_event)

    # Verify output was produced
    assert len(outputs) == 1
    output = outputs[0]

    # Verify output contains expected content
    assert "SÉANCE COMPLETE" in output
    assert "Test Spirit" in output
    assert "Omen:" in output
    assert "Interpretation:" in output


@pytest.mark.asyncio
async def test_seance_default_values():
    """Test that Séance works with default payload values."""
    outputs = []
    spine_ref = [None]

    backend = StoppingBackend(spine_ref, max_events=10)
    manifest = ManifestEffect(output_callback=outputs.append)

    organs = [
        SummonSpirit(),
        AskQuestion(),
        InterpretResponse(),
        manifest,
    ]

    spine = Spine(organs=organs, backend=backend)
    spine_ref[0] = spine

    # Minimal event with empty payload dictionary
    start_event = Event(event_type="SUMMON_RITUAL")

    await spine.run(start_event)

    # Should still complete successfully
    assert len(outputs) == 1
    assert "SÉANCE COMPLETE" in outputs[0]


@pytest.mark.asyncio
async def test_seance_organ_chain_order():
    """Test that organs are invoked in the correct order."""
    invocation_order = []
    spine_ref = [None]

    class TrackingSummonSpirit(SummonSpirit):
        def handle(self, event):
            invocation_order.append("SummonSpirit")
            return super().handle(event)

    class TrackingAskQuestion(AskQuestion):
        def handle(self, event):
            invocation_order.append("AskQuestion")
            return super().handle(event)

    class TrackingInterpretResponse(InterpretResponse):
        def handle(self, event):
            invocation_order.append("InterpretResponse")
            return super().handle(event)

    class TrackingManifestEffect(ManifestEffect):
        def handle(self, event):
            invocation_order.append("ManifestEffect")
            return super().handle(event)

    backend = StoppingBackend(spine_ref, max_events=10)
    organs = [
        TrackingSummonSpirit(),
        TrackingAskQuestion(),
        TrackingInterpretResponse(),
        TrackingManifestEffect(output_callback=lambda x: None),
    ]

    spine = Spine(organs=organs, backend=backend)
    spine_ref[0] = spine
    start_event = Event(event_type="SUMMON_RITUAL")

    await spine.run(start_event)

    # Verify correct order
    assert invocation_order == [
        "SummonSpirit",
        "AskQuestion",
        "InterpretResponse",
        "ManifestEffect",
    ]
