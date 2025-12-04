"""Brutal edge case tests for production resilience.

These tests attempt to break NecroStack with malicious inputs,
resource exhaustion, and failure scenarios.
"""

import asyncio

import pydantic
import pytest

from necrostack.backends.inmemory import BackendFullError, InMemoryBackend
from necrostack.core.event import MAX_PAYLOAD_SIZE, Event
from necrostack.core.organ import Organ
from necrostack.core.spine import (
    InMemoryFailedEventStore,
    Spine,
)


class StoppingBackend(InMemoryBackend):
    """Backend that stops the spine when queue is empty."""

    def __init__(self, spine_ref: list, max_size: int = 0):
        super().__init__(max_size)
        self._spine_ref = spine_ref

    async def pull(self, timeout: float = 1.0) -> Event | None:
        event = await super().pull(timeout)
        if event is None and self._spine_ref[0]:
            self._spine_ref[0].stop()
        return event


# =============================================================================
# Event Model Edge Cases
# =============================================================================


class TestEventEdgeCases:
    """Brutal tests for Event model."""

    def test_payload_exactly_at_limit(self):
        """Payload at exactly 1MB should succeed."""
        # Account for JSON overhead: {"k": "..."}
        data = "x" * (MAX_PAYLOAD_SIZE - 10)
        event = Event(event_type="TEST", payload={"k": data})
        assert len(event.payload["k"]) == MAX_PAYLOAD_SIZE - 10

    def test_payload_one_byte_over_limit(self):
        """Payload 1 byte over limit should fail."""
        data = "x" * MAX_PAYLOAD_SIZE
        with pytest.raises(ValueError, match="exceeds maximum size"):
            Event(event_type="TEST", payload={"data": data})

    def test_payload_with_unicode_counts_bytes_not_chars(self):
        """Unicode payload should count bytes, not characters."""
        # Each emoji is 4 bytes in UTF-8
        emoji = "🔥" * (MAX_PAYLOAD_SIZE // 4 + 1)
        with pytest.raises(ValueError, match="exceeds maximum size"):
            Event(event_type="TEST", payload={"emoji": emoji})

    def test_deeply_nested_payload(self):
        """Deeply nested payload should serialize correctly."""
        nested = {"level": 0}
        current = nested
        for i in range(100):
            current["child"] = {"level": i + 1}
            current = current["child"]

        event = Event(event_type="TEST", payload=nested)
        assert event.payload["child"]["child"]["level"] == 2

    def test_payload_with_non_serializable_type_fails(self):
        """Non-JSON-serializable types should fail validation."""
        with pytest.raises(ValueError, match="JSON-serializable"):
            Event(event_type="TEST", payload={"func": lambda x: x})

    def test_empty_event_type_after_strip(self):
        """Whitespace-only event_type should fail."""
        with pytest.raises(ValueError, match="must not be empty"):
            Event(event_type="   \t\n  ", payload={})

    def test_invalid_uuid_format(self):
        """Invalid UUID format should fail."""
        with pytest.raises(ValueError, match="UUID"):
            Event(id="not-a-uuid", event_type="TEST", payload={})

    def test_uuid_v1_rejected(self):
        """UUID v1 (time-based) should be rejected."""
        # UUID v1 has version nibble = 1
        with pytest.raises(ValueError, match="UUID"):
            Event(id="550e8400-e29b-11d4-a716-446655440000", event_type="TEST", payload={})

    def test_event_immutability(self):
        """Event should be immutable after creation."""
        event = Event(event_type="TEST", payload={"key": "value"})
        with pytest.raises((pydantic.ValidationError, AttributeError, TypeError)):
            event.event_type = "MODIFIED"


# =============================================================================
# Handler Return Type Edge Cases
# =============================================================================


class TestHandlerReturnTypes:
    """Tests for handler return type validation."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_handler_returns_string_logged_as_error(self):
        """Handler returning string should be logged as error."""
        spine_ref = [None]

        class BadOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event) -> str:
                return "not an event"

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[BadOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.handler_errors["BadOrgan"] == 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_handler_returns_list_with_non_event_logged(self):
        """Handler returning list with non-Event should be logged as error."""
        spine_ref = [None]

        class BadOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event):
                return [Event(event_type="OK", payload={}), "not an event"]

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[BadOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.handler_errors["BadOrgan"] == 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_handler_returns_dict_logged_as_error(self):
        """Handler returning dict should be logged as error."""
        spine_ref = [None]

        class BadOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event):
                return {"event_type": "FAKE"}

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[BadOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.handler_errors["BadOrgan"] == 1


# =============================================================================
# Handler Timeout Edge Cases
# =============================================================================


class TestHandlerTimeout:
    """Tests for handler timeout behavior."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_slow_handler_times_out_and_logged(self):
        """Handler exceeding timeout should be logged as error."""
        spine_ref = [None]

        class SlowOrgan(Organ):
            listens_to = ["TEST"]

            async def handle(self, event: Event):
                await asyncio.sleep(10)  # Way longer than timeout
                return None

        backend = StoppingBackend(spine_ref)
        spine = Spine(
            organs=[SlowOrgan()],
            backend=backend,
            handler_timeout=0.1,
        )
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.handler_errors["SlowOrgan"] == 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_handler_just_under_timeout_succeeds(self):
        """Handler completing just before timeout should succeed."""
        spine_ref = [None]

        class FastOrgan(Organ):
            listens_to = ["TEST"]

            async def handle(self, event: Event):
                await asyncio.sleep(0.05)
                return None

        backend = StoppingBackend(spine_ref)
        spine = Spine(
            organs=[FastOrgan()],
            backend=backend,
            handler_timeout=1.0,
        )
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.events_processed == 1


# =============================================================================
# Backend Backpressure Edge Cases
# =============================================================================


class TestBackpressure:
    """Tests for backpressure handling."""

    @pytest.mark.asyncio
    async def test_bounded_queue_rejects_when_full(self):
        """Bounded queue should reject enqueue when full."""
        backend = InMemoryBackend(max_size=2)

        await backend.enqueue(Event(event_type="E1", payload={}))
        await backend.enqueue(Event(event_type="E2", payload={}))

        with pytest.raises(BackendFullError, match="Queue full"):
            await backend.enqueue(Event(event_type="E3", payload={}))

    @pytest.mark.asyncio
    async def test_unbounded_queue_accepts_many(self):
        """Unbounded queue should accept many events."""
        backend = InMemoryBackend(max_size=0)

        for i in range(1000):
            await backend.enqueue(Event(event_type=f"E{i}", payload={}))

        assert backend.qsize() == 1000


# =============================================================================
# DLQ Edge Cases
# =============================================================================


class TestDLQEdgeCases:
    """Tests for Dead Letter Queue behavior."""

    @pytest.mark.asyncio
    async def test_dlq_bounded_drops_oldest(self):
        """Bounded DLQ should drop oldest events when full."""
        store = InMemoryFailedEventStore(max_size=3)

        for i in range(5):
            await store.store(
                Event(event_type=f"E{i}", payload={}),
                Exception(f"Error {i}"),
            )

        assert len(store) == 3
        assert store.dropped_count == 2

        # Should have E2, E3, E4 (oldest E0, E1 dropped)
        events = store.get_failed_events()
        types = [e.event_type for e, _ in events]
        assert types == ["E2", "E3", "E4"]


# =============================================================================
# Infinite Loop Prevention
# =============================================================================


class TestInfiniteLoopPrevention:
    """Tests for infinite loop detection."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_self_emitting_handler_hits_max_steps(self):
        """Handler that emits same event type should hit max_steps."""

        class InfiniteOrgan(Organ):
            listens_to = ["LOOP"]

            def handle(self, event: Event):
                return Event(event_type="LOOP", payload={})

        spine = Spine(
            organs=[InfiniteOrgan()],
            backend=InMemoryBackend(),
            max_steps=10,
        )

        with pytest.raises(RuntimeError, match="Max steps exceeded"):
            await spine.run(Event(event_type="LOOP", payload={}))

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_ping_pong_handlers_hit_max_steps(self):
        """Two handlers ping-ponging should hit max_steps."""

        class PingOrgan(Organ):
            listens_to = ["PING"]

            def handle(self, event: Event):
                return Event(event_type="PONG", payload={})

        class PongOrgan(Organ):
            listens_to = ["PONG"]

            def handle(self, event: Event):
                return Event(event_type="PING", payload={})

        spine = Spine(
            organs=[PingOrgan(), PongOrgan()],
            backend=InMemoryBackend(),
            max_steps=10,
        )

        with pytest.raises(RuntimeError, match="Max steps exceeded"):
            await spine.run(Event(event_type="PING", payload={}))


# =============================================================================
# Exception Handling Edge Cases
# =============================================================================


class TestExceptionHandling:
    """Tests for exception handling in handlers."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_sync_handler_exception_logged_not_raised(self):
        """Sync handler exception should be logged, not propagated."""
        spine_ref = [None]

        class FailingOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event):
                raise ValueError("Intentional failure")

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[FailingOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.handler_errors["FailingOrgan"] == 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_async_handler_exception_logged_not_raised(self):
        """Async handler exception should be logged, not propagated."""
        spine_ref = [None]

        class AsyncFailingOrgan(Organ):
            listens_to = ["TEST"]

            async def handle(self, event: Event):
                raise RuntimeError("Async failure")

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[AsyncFailingOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.handler_errors["AsyncFailingOrgan"] == 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_multiple_handlers_one_fails_others_run(self):
        """If one handler fails, others should still run."""
        results = []
        spine_ref = [None]

        class FailingOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event):
                raise ValueError("I fail")

        class SuccessOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event):
                results.append("success")
                return None

        backend = StoppingBackend(spine_ref)
        spine = Spine(
            organs=[FailingOrgan(), SuccessOrgan()],
            backend=backend,
        )
        spine_ref[0] = spine

        await spine.run(Event(event_type="TEST", payload={}))
        assert "success" in results


# =============================================================================
# Fanout Edge Cases
# =============================================================================


class TestFanout:
    """Tests for multi-event emission."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_handler_emits_empty_list(self):
        """Handler returning empty list should emit nothing."""
        spine_ref = [None]

        class EmptyOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event):
                return []

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[EmptyOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.events_emitted == 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_handler_emits_many_events(self):
        """Handler emitting many events should enqueue all."""
        processed = []
        spine_ref = [None]

        class FanoutOrgan(Organ):
            listens_to = ["START"]

            def handle(self, event: Event):
                return [Event(event_type="CHILD", payload={"i": i}) for i in range(10)]

        class CollectorOrgan(Organ):
            listens_to = ["CHILD"]

            def handle(self, event: Event):
                processed.append(event.payload["i"])
                return None

        backend = StoppingBackend(spine_ref)
        spine = Spine(
            organs=[FanoutOrgan(), CollectorOrgan()],
            backend=backend,
        )
        spine_ref[0] = spine

        await spine.run(Event(event_type="START", payload={}))
        assert sorted(processed) == list(range(10))
