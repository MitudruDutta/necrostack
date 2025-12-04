"""Tests for Spine failure modes and FailedEventStore."""

import asyncio

import pytest

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import (
    EnqueueFailureMode,
    InMemoryFailedEventStore,
    Spine,
    SpineStats,
)


class FailOnNthEnqueue:
    """Backend that fails on the Nth enqueue call."""

    def __init__(self, fail_on: int = 2):
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._enqueue_count = 0
        self._fail_on = fail_on

    async def enqueue(self, event: Event) -> None:
        self._enqueue_count += 1
        if self._enqueue_count == self._fail_on:
            raise ConnectionError(f"Simulated failure on enqueue #{self._enqueue_count}")
        await self._queue.put(event)

    async def pull(self, timeout: float = 1.0) -> Event | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def ack(self, event: Event) -> None:
        pass


# =============================================================================
# InMemoryFailedEventStore Tests
# =============================================================================


class TestInMemoryFailedEventStore:
    """Tests for InMemoryFailedEventStore."""

    @pytest.fixture
    def store(self):
        return InMemoryFailedEventStore()

    async def test_store_saves_event_and_error(self, store):
        event = Event(event_type="FAILED", payload={"data": "test"})
        error = ValueError("Test error")
        await store.store(event, error)

        failed = store.get_failed_events()
        assert len(failed) == 1
        assert failed[0][0] == event
        assert failed[0][1] == error

    async def test_store_preserves_order(self, store):
        events = [Event(event_type=f"FAIL_{i}", payload={}) for i in range(3)]
        errors = [ValueError(f"Error {i}") for i in range(3)]

        for event, error in zip(events, errors):
            await store.store(event, error)

        failed = store.get_failed_events()
        assert len(failed) == 3

        # Verify events are in insertion order
        for i, (stored_event, stored_error) in enumerate(failed):
            assert stored_event.event_type == f"FAIL_{i}"
            assert stored_event.id == events[i].id
            assert str(stored_error) == f"Error {i}"

    async def test_clear_removes_all_events(self, store):
        for i in range(3):
            await store.store(Event(event_type="FAIL", payload={}), ValueError("err"))

        assert len(store) == 3
        store.clear()
        assert len(store) == 0

    async def test_len_returns_count(self, store):
        assert len(store) == 0
        await store.store(Event(event_type="FAIL", payload={}), ValueError("err"))
        assert len(store) == 1


# =============================================================================
# EnqueueFailureMode.FAIL Tests
# =============================================================================


class TestFailMode:
    """Tests for EnqueueFailureMode.FAIL."""

    @pytest.mark.timeout(5)
    async def test_fail_mode_raises_immediately(self):
        """FAIL mode SHALL raise EnqueueError wrapping the original exception."""
        from necrostack.core.spine import EnqueueError

        class EmitOrgan(Organ):
            listens_to = ["TRIGGER"]

            def handle(self, event: Event) -> Event:
                return Event(event_type="EMITTED", payload={})

        # Fail on 2nd enqueue (the emitted event)
        backend = FailOnNthEnqueue(fail_on=2)
        spine = Spine(
            organs=[EmitOrgan()],
            backend=backend,
            enqueue_failure_mode=EnqueueFailureMode.FAIL,
        )

        with pytest.raises(EnqueueError) as exc_info:
            await spine.run(Event(event_type="TRIGGER", payload={}))

        assert "Simulated failure" in str(exc_info.value)
        assert isinstance(exc_info.value.original, ConnectionError)

    @pytest.mark.timeout(5)
    async def test_fail_mode_increments_failure_count(self):
        """FAIL mode SHALL increment failure count before raising."""
        from necrostack.core.spine import EnqueueError

        class EmitOrgan(Organ):
            listens_to = ["TRIGGER"]

            def handle(self, event: Event) -> Event:
                return Event(event_type="EMITTED", payload={})

        backend = FailOnNthEnqueue(fail_on=2)
        spine = Spine(
            organs=[EmitOrgan()],
            backend=backend,
            enqueue_failure_mode=EnqueueFailureMode.FAIL,
        )

        with pytest.raises(EnqueueError):
            await spine.run(Event(event_type="TRIGGER", payload={}))

        assert spine.get_enqueue_failure_count("EMITTED") == 1


# =============================================================================
# EnqueueFailureMode.STORE Tests
# =============================================================================


class TestStoreMode:
    """Tests for EnqueueFailureMode.STORE."""

    @pytest.mark.timeout(5)
    async def test_store_mode_saves_to_failed_event_store(self):
        """STORE mode SHALL save failed events to the failed_event_store."""

        class EmitAndStop(Organ):
            listens_to = ["TRIGGER"]

            def __init__(self, spine_ref):
                super().__init__()
                self._spine_ref = spine_ref

            def handle(self, event: Event) -> Event:
                if self._spine_ref[0]:
                    self._spine_ref[0].stop()
                return Event(event_type="EMITTED", payload={})

        # Fail on 2nd enqueue (the emitted event)
        backend = FailOnNthEnqueue(fail_on=2)
        spine_ref: list = [None]

        spine = Spine(
            organs=[EmitAndStop(spine_ref)],
            backend=backend,
            enqueue_failure_mode=EnqueueFailureMode.STORE,
        )
        spine_ref[0] = spine

        await spine.run(Event(event_type="TRIGGER", payload={}))

        # Check the spine's internal failed_event_store
        failed = spine.failed_event_store.get_failed_events()
        assert len(failed) == 1
        assert failed[0][0].event_type == "EMITTED"
        assert isinstance(failed[0][1], ConnectionError)

    @pytest.mark.timeout(5)
    async def test_store_mode_continues_processing_after_failure(self):
        """STORE mode SHALL continue processing after storing failed event.

        Uses a backend that fails once to verify:
        1. The failed event is stored
        2. The spine continues to process subsequent events
        """
        processed_events: list[str] = []
        spine_ref: list = [None]

        # Use FailOnNthEnqueue configured to fail on 2nd enqueue
        backend = FailOnNthEnqueue(fail_on=2)

        class EmitMultiple(Organ):
            """Emits multiple events - one will fail, others should succeed."""

            listens_to = ["START"]

            def handle(self, event: Event) -> list[Event]:
                return [
                    Event(event_type="EVENT_A", payload={}),  # This will fail (2nd enqueue)
                    Event(event_type="EVENT_B", payload={}),  # This should succeed
                    Event(event_type="EVENT_C", payload={}),  # This should succeed
                ]

        class TrackingOrgan(Organ):
            """Tracks which events were processed."""

            listens_to = ["EVENT_A", "EVENT_B", "EVENT_C"]

            def handle(self, event: Event) -> None:
                processed_events.append(event.event_type)
                # Stop after processing both successful events
                if len(processed_events) >= 2 and spine_ref[0]:
                    spine_ref[0].stop()

        spine = Spine(
            organs=[EmitMultiple(), TrackingOrgan()],
            backend=backend,
            enqueue_failure_mode=EnqueueFailureMode.STORE,
        )
        spine_ref[0] = spine

        await spine.run(Event(event_type="START", payload={}))

        # Verify: one event was stored as failed (use spine's internal store)
        failed_events = spine.failed_event_store.get_failed_events()
        assert len(failed_events) == 1
        failed_event, failed_error = failed_events[0]
        assert failed_event.event_type == "EVENT_A"
        assert isinstance(failed_error, ConnectionError)

        # Verify: subsequent events were still processed
        assert "EVENT_B" in processed_events
        assert "EVENT_C" in processed_events
        assert "EVENT_A" not in processed_events  # Failed event wasn't enqueued


# =============================================================================
# EnqueueFailureMode.RETRY Tests
# =============================================================================


class TestRetryMode:
    """Tests for EnqueueFailureMode.RETRY."""

    @pytest.mark.timeout(5)
    async def test_retry_mode_retries_on_failure(self):
        """RETRY mode SHALL retry with exponential backoff."""

        class RecoveringBackend:
            def __init__(self, fail_count: int = 2):
                self._queue: asyncio.Queue[Event] = asyncio.Queue()
                self._enqueue_attempts = 0
                self._fail_count = fail_count
                self._first_enqueue_done = False

            async def enqueue(self, event: Event) -> None:
                # Let the first enqueue (start event) succeed
                if not self._first_enqueue_done:
                    self._first_enqueue_done = True
                    await self._queue.put(event)
                    return

                self._enqueue_attempts += 1
                if self._enqueue_attempts <= self._fail_count:
                    raise ConnectionError(f"Attempt {self._enqueue_attempts} failed")
                await self._queue.put(event)

            async def pull(self, timeout: float = 1.0) -> Event | None:
                try:
                    return await asyncio.wait_for(self._queue.get(), timeout=timeout)
                except TimeoutError:
                    return None

            async def ack(self, event: Event) -> None:
                pass

        class EmitAndStop(Organ):
            listens_to = ["START"]

            def __init__(self, spine_ref):
                super().__init__()
                self._spine_ref = spine_ref

            def handle(self, event: Event) -> Event:
                if self._spine_ref[0]:
                    self._spine_ref[0].stop()
                return Event(event_type="EMITTED", payload={})

        backend = RecoveringBackend(fail_count=2)
        spine_ref: list = [None]

        spine = Spine(
            organs=[EmitAndStop(spine_ref)],
            backend=backend,
            enqueue_failure_mode=EnqueueFailureMode.RETRY,
            retry_attempts=3,
            retry_base_delay=0.001,
        )
        spine_ref[0] = spine

        await spine.run(Event(event_type="START", payload={}))
        # 2 failures + 1 success = 3 attempts
        assert backend._enqueue_attempts == 3

    @pytest.mark.timeout(5)
    async def test_retry_mode_raises_after_exhaustion(self):
        """RETRY mode SHALL raise after all retries exhausted."""

        class AlwaysFailOnSecond:
            def __init__(self):
                self._queue: asyncio.Queue[Event] = asyncio.Queue()
                self._first_done = False

            async def enqueue(self, event: Event) -> None:
                if not self._first_done:
                    self._first_done = True
                    await self._queue.put(event)
                    return
                raise ConnectionError("Always fails")

            async def pull(self, timeout: float = 1.0) -> Event | None:
                try:
                    return await asyncio.wait_for(self._queue.get(), timeout=timeout)
                except TimeoutError:
                    return None

            async def ack(self, event: Event) -> None:
                pass

        class EmitOrgan(Organ):
            listens_to = ["TRIGGER"]

            def handle(self, event: Event) -> Event:
                return Event(event_type="EMITTED", payload={})

        backend = AlwaysFailOnSecond()
        spine = Spine(
            organs=[EmitOrgan()],
            backend=backend,
            enqueue_failure_mode=EnqueueFailureMode.RETRY,
            retry_attempts=2,
            retry_base_delay=0.001,
        )

        from necrostack.core.spine import EnqueueError

        with pytest.raises(EnqueueError) as exc_info:
            await spine.run(Event(event_type="TRIGGER", payload={}))

        # Verify the original error is preserved
        assert isinstance(exc_info.value.original, ConnectionError)


# =============================================================================
# SpineStats Tests
# =============================================================================


class TestSpineStats:
    """Tests for SpineStats tracking."""

    @pytest.mark.timeout(5)
    async def test_stats_tracks_events_processed(self):
        backend = InMemoryBackend()
        spine_ref: list = [None]
        count = 0

        class CountingOrgan(Organ):
            listens_to = ["COUNT"]

            def handle(self, event: Event) -> Event | None:
                nonlocal count
                count += 1
                if count >= 3:
                    if spine_ref[0]:
                        spine_ref[0].stop()
                    return None
                return Event(event_type="COUNT", payload={})

        spine = Spine(organs=[CountingOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="COUNT", payload={}))
        assert stats.events_processed == 3

    @pytest.mark.timeout(5)
    async def test_stats_tracks_events_emitted(self):
        backend = InMemoryBackend()
        spine_ref: list = [None]

        class EmitMultiple(Organ):
            listens_to = ["START"]

            def handle(self, event: Event) -> list[Event]:
                if spine_ref[0]:
                    spine_ref[0].stop()
                return [Event(event_type="A", payload={}) for _ in range(5)]

        spine = Spine(organs=[EmitMultiple()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="START", payload={}))
        assert stats.events_emitted == 5

    @pytest.mark.timeout(5)
    async def test_stats_tracks_handler_errors(self):
        backend = InMemoryBackend()
        spine_ref: list = [None]

        class FailingOrgan(Organ):
            listens_to = ["FAIL"]

            def handle(self, event: Event) -> None:
                if spine_ref[0]:
                    spine_ref[0].stop()
                raise ValueError("Handler failed")

        spine = Spine(organs=[FailingOrgan()], backend=backend)
        spine_ref[0] = spine

        stats = await spine.run(Event(event_type="FAIL", payload={}))
        assert stats.handler_errors["FailingOrgan"] == 1

    def test_get_stats_returns_current_stats(self):
        backend = InMemoryBackend()
        spine = Spine(organs=[], backend=backend)

        stats = spine.get_stats()
        assert isinstance(stats, SpineStats)
        assert stats.events_processed == 0
