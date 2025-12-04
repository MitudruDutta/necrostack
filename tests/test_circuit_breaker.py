"""Tests for Spine circuit breaker functionality."""

from collections.abc import Callable

import pytest

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import (
    BackendUnavailableError,
    HandlerFailureMode,
    InMemoryFailedEventStore,
    Spine,
)


class AlwaysFailingBackend:
    """Backend that always fails on pull."""

    async def enqueue(self, event: Event) -> None:
        pass

    async def pull(self, timeout: float = 1.0) -> Event | None:
        raise ConnectionError("Backend unavailable")

    async def ack(self, event: Event) -> None:
        pass


class FailNTimesThenSucceed:
    """Backend that fails N times then works."""

    def __init__(self, fail_count: int):
        self._fail_count = fail_count
        self._attempts = 0
        self._queue: list[Event] = []

    async def enqueue(self, event: Event) -> None:
        self._queue.append(event)

    async def pull(self, timeout: float = 1.0) -> Event | None:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise ConnectionError(f"Failure {self._attempts}")
        if self._queue:
            return self._queue.pop(0)
        return None

    async def ack(self, event: Event) -> None:
        pass


class TestCircuitBreaker:
    """Tests for backend failure circuit breaker."""

    @pytest.mark.timeout(5)
    async def test_raises_after_max_consecutive_failures(self):
        """Spine SHALL raise BackendUnavailableError after max consecutive failures."""
        backend = AlwaysFailingBackend()
        spine = Spine(
            organs=[],
            backend=backend,
            max_consecutive_backend_failures=3,
        )

        with pytest.raises(BackendUnavailableError) as exc_info:
            await spine.run()

        error_message = str(exc_info.value)
        assert "3" in error_message
        assert "failures" in error_message

    @pytest.mark.timeout(5)
    async def test_resets_counter_on_success(self):
        """Circuit breaker counter SHALL reset after successful pull."""
        backend = FailNTimesThenSucceed(fail_count=2)
        spine: Spine | None = None

        class StopOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event) -> None:
                if spine is not None:
                    spine.stop()

        spine = Spine(
            organs=[StopOrgan()],
            backend=backend,
            max_consecutive_backend_failures=5,
        )

        # Should succeed - 2 failures then success
        stats = await spine.run(Event(event_type="TEST", payload={}))
        assert stats.backend_errors == 2
        assert stats.events_processed == 1

    @pytest.mark.timeout(5)
    async def test_stats_tracks_backend_errors(self):
        """SpineStats SHALL track backend_errors count."""
        backend = AlwaysFailingBackend()
        spine = Spine(
            organs=[],
            backend=backend,
            max_consecutive_backend_failures=5,
        )

        with pytest.raises(BackendUnavailableError):
            await spine.run()

        assert spine.get_stats().backend_errors == 5

    @pytest.mark.timeout(5)
    async def test_default_max_failures_is_10(self):
        """Default max_consecutive_backend_failures SHALL be 10."""
        backend = InMemoryBackend()
        spine = Spine(organs=[], backend=backend)
        assert spine.max_consecutive_backend_failures == 10


class AckTrackingBackend:
    """Backend that tracks ack calls."""

    def __init__(self):
        self._queue: list[Event] = []
        self.acked_events: list[Event] = []
        self._stop_callback: Callable[[], None] | None = None

    async def enqueue(self, event: Event) -> None:
        self._queue.append(event)

    async def pull(self, timeout: float = 1.0) -> Event | None:
        if self._queue:
            return self._queue.pop(0)
        # Stop spine when queue is empty via callback
        if self._stop_callback:
            self._stop_callback()
        return None

    async def ack(self, event: Event) -> None:
        self.acked_events.append(event)


class TestSpineAcknowledgment:
    """Tests for Spine event acknowledgment."""

    @pytest.mark.timeout(5)
    async def test_ack_called_after_successful_processing(self):
        """Spine SHALL call ack() after all handlers succeed."""
        backend = AckTrackingBackend()

        class PassOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event) -> None:
                pass

        spine = Spine(organs=[PassOrgan()], backend=backend)
        backend._stop_callback = spine.stop
        event = Event(event_type="TEST", payload={})

        await spine.run(event)

        assert len(backend.acked_events) == 1
        assert backend.acked_events[0].id == event.id

    @pytest.mark.timeout(5)
    async def test_no_ack_when_handler_fails_with_nack_mode(self):
        """Spine SHALL NOT call ack() when handler fails and mode is NACK."""
        backend = AckTrackingBackend()

        class FailOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event) -> None:
                raise ValueError("Handler failed")

        spine = Spine(
            organs=[FailOrgan()],
            backend=backend,
            handler_failure_mode=HandlerFailureMode.NACK,
        )
        backend._stop_callback = spine.stop
        event = Event(event_type="TEST", payload={})

        await spine.run(event)

        # Event should NOT be acked since handler failed and mode is NACK
        assert len(backend.acked_events) == 0

    @pytest.mark.timeout(5)
    async def test_handler_failure_stored_in_dlq_with_store_mode(self):
        """Handler failures SHALL go to DLQ when mode is STORE."""
        backend = AckTrackingBackend()
        dlq = InMemoryFailedEventStore()

        class FailOrgan(Organ):
            listens_to = ["TEST"]

            def handle(self, event: Event) -> None:
                raise ValueError("Handler failed")

        spine = Spine(
            organs=[FailOrgan()],
            backend=backend,
            handler_failure_mode=HandlerFailureMode.STORE,
            failed_event_store=dlq,
        )
        backend._stop_callback = spine.stop
        event = Event(event_type="TEST", payload={})

        await spine.run(event)

        # Event should be in DLQ
        assert len(dlq) == 1
        failed_event, error = dlq.get_failed_events()[0]
        assert failed_event.id == event.id
        assert "Handler failed" in str(error)

        # Event should be acked after storing in DLQ (STORE mode acks after DLQ storage)
        assert len(backend.acked_events) == 1
