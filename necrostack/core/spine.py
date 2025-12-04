"""Spine dispatcher for NecroStack event routing.

The Spine is the central dispatcher that:
- Pulls events from a backend
- Routes them to matching Organs based on event_type
- Enqueues any returned events back to the backend

IMPORTANT: Spine does NOT maintain any internal queue. All queue operations
go through the backend.
"""

import asyncio
import inspect
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from necrostack.core.event import Event
from necrostack.core.logging import configure_spine_logger
from necrostack.core.organ import Organ

if TYPE_CHECKING:
    from necrostack.backends.base import Backend

# Circuit breaker defaults
DEFAULT_MAX_CONSECUTIVE_FAILURES = 10


class EnqueueFailureMode(Enum):
    """Strategy for handling enqueue failures."""

    FAIL = "fail"
    RETRY = "retry"
    STORE = "store"


class HandlerFailureMode(Enum):
    """Strategy for handling handler failures.

    LOG: Log the error and continue (event is acked, no retry)
    STORE: Store failed event in DLQ (event is acked)
    NACK: Don't ack the event (relies on backend retry mechanism)
    """

    LOG = "log"
    STORE = "store"
    NACK = "nack"


class EnqueueError(Exception):
    """Raised when enqueue fails in FAIL/RETRY mode."""

    def __init__(self, original: Exception):
        self.original = original
        super().__init__(str(original))


class BackendUnavailableError(Exception):
    """Raised when backend fails consecutively beyond threshold.

    Attributes:
        failure_count: Number of consecutive failures that triggered this error.
        last_error: The last exception message from the backend.
    """

    def __init__(self, message: str, failure_count: int = 0, last_error: str | None = None):
        self.failure_count = failure_count
        self.last_error = last_error
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        if self.last_error:
            return f"{base} (last error: {self.last_error})"
        return base


class FailedEventStore(Protocol):
    """Protocol for storing failed events for later retry."""

    async def store(self, event: Event, error: Exception) -> None: ...
    def get_failed_events(self) -> list[tuple[Event, Exception]]: ...
    def clear(self) -> None: ...


class InMemoryFailedEventStore:
    """Simple in-memory failed event store with bounded size."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._events: list[tuple[Event, Exception]] = []
        self._max_size = max_size
        self._dropped_count = 0

    def __bool__(self) -> bool:
        """Always truthy so 'store or default' works correctly."""
        return True

    async def store(self, event: Event, error: Exception) -> None:
        if len(self._events) >= self._max_size:
            # Drop oldest to make room (FIFO eviction)
            self._events.pop(0)
            self._dropped_count += 1
        self._events.append((event, error))

    def get_failed_events(self) -> list[tuple[Event, Exception]]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to size limit."""
        return self._dropped_count


@dataclass
class SpineStats:
    """Statistics from a Spine run."""

    events_processed: int = 0
    events_emitted: int = 0
    enqueue_failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    handler_errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    backend_errors: int = 0
    ack_errors: int = 0


class Spine:
    """Central event dispatcher."""

    def __init__(
        self,
        organs: list[Organ],
        backend: "Backend",
        max_steps: int = 10_000,
        enqueue_failure_mode: EnqueueFailureMode = EnqueueFailureMode.STORE,
        handler_failure_mode: HandlerFailureMode = HandlerFailureMode.LOG,
        failed_event_store: FailedEventStore | None = None,
        retry_attempts: int = 3,
        retry_base_delay: float = 0.1,
        max_consecutive_backend_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
        handler_timeout: float = 30.0,
    ) -> None:
        self.organs = organs
        self.backend = backend
        self.max_steps = max_steps
        self.enqueue_failure_mode = enqueue_failure_mode
        self.handler_failure_mode = handler_failure_mode
        self.failed_event_store = failed_event_store or InMemoryFailedEventStore()
        self.retry_attempts = retry_attempts
        self.retry_base_delay = retry_base_delay
        self.max_consecutive_backend_failures = max_consecutive_backend_failures
        self.handler_timeout = handler_timeout
        self._log = configure_spine_logger()
        self._running = False
        self._stats = SpineStats()
        self._consecutive_pull_failures = 0
        self._last_backend_error: str | None = None

        self._validate_organs()

    def _validate_organs(self) -> None:
        for organ in self.organs:
            if not isinstance(organ.listens_to, list):
                raise TypeError(
                    f"{organ.name}.listens_to must be a list[str], "
                    f"got {type(organ.listens_to).__name__}"
                )
            for item in organ.listens_to:
                if not isinstance(item, str):
                    raise TypeError(
                        f"{organ.name}.listens_to must contain only strings, "
                        f"found {type(item).__name__}: {item!r}"
                    )

    async def _invoke_handler(self, organ: Organ, event: Event) -> Event | list[Event] | None:
        """Invoke handler with timeout and return type validation."""
        result = organ.handle(event)
        if inspect.iscoroutine(result):
            try:
                result = await asyncio.wait_for(result, timeout=self.handler_timeout)
            except TimeoutError:
                raise TimeoutError(f"Handler {organ.name} timed out after {self.handler_timeout}s")

        # Validate return type
        if result is None:
            return None
        if isinstance(result, Event):
            return result
        if isinstance(result, list):
            for i, item in enumerate(result):
                if not isinstance(item, Event):
                    raise TypeError(
                        f"Handler {organ.name} returned list with non-Event at index {i}: "
                        f"got {type(item).__name__}"
                    )
            return result
        raise TypeError(
            f"Handler {organ.name} must return Event, list[Event], or None, "
            f"got {type(result).__name__}"
        )

    def stop(self) -> None:
        self._running = False

    def get_stats(self) -> SpineStats:
        """Return a copy of current statistics.

        Returns a snapshot that is safe to inspect without affecting internal state.
        """
        return SpineStats(
            events_processed=self._stats.events_processed,
            events_emitted=self._stats.events_emitted,
            enqueue_failures=defaultdict(int, self._stats.enqueue_failures),
            handler_errors=defaultdict(int, self._stats.handler_errors),
            backend_errors=self._stats.backend_errors,
            ack_errors=self._stats.ack_errors,
        )

    def get_enqueue_failure_count(self, event_type: str | None = None) -> int:
        if event_type is not None:
            return self._stats.enqueue_failures.get(event_type, 0)
        return sum(self._stats.enqueue_failures.values())

    async def _handle_enqueue_failure(self, event: Event, error: Exception) -> None:
        self._stats.enqueue_failures[event.event_type] += 1

        if self.enqueue_failure_mode == EnqueueFailureMode.FAIL:
            self._log.error(
                f"Enqueue failed (mode=fail): {error}",
                extra={
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "error": str(error),
                    "failure_mode": "fail",
                },
            )
            raise EnqueueError(error)

        elif self.enqueue_failure_mode == EnqueueFailureMode.RETRY:
            last_error = error
            for attempt in range(self.retry_attempts):
                delay = self.retry_base_delay * (2**attempt)
                self._log.warning(
                    f"Enqueue failed, retrying in {delay}s ({attempt + 1}/{self.retry_attempts})",
                    extra={
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "error": str(last_error),
                        "failure_mode": "retry",
                        "attempt": attempt + 1,
                    },
                )
                await asyncio.sleep(delay)
                try:
                    await self.backend.enqueue(event)
                    return
                except Exception as e:
                    last_error = e

            self._log.error(
                f"Enqueue failed after {self.retry_attempts} retries: {last_error}",
                extra={
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "error": str(last_error),
                    "failure_mode": "retry",
                },
            )
            raise EnqueueError(last_error)

        else:  # STORE mode
            self._log.warning(
                f"Enqueue failed, storing in DLQ: {error}",
                extra={
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "error": str(error),
                    "failure_mode": "store",
                },
            )
            await self.failed_event_store.store(event, error)

    async def run(self, start_event: Event | None = None) -> SpineStats:
        self._stats = SpineStats()
        self._running = True
        self._consecutive_pull_failures = 0

        if start_event is not None:
            try:
                await self.backend.enqueue(start_event)
            except Exception as e:
                self._log.error(
                    f"Failed to enqueue start event: {e}",
                    extra={
                        "event_id": start_event.id,
                        "event_type": start_event.event_type,
                        "error": str(e),
                    },
                )
                raise

        while self._running:
            if self._stats.events_processed >= self.max_steps:
                raise RuntimeError("Max steps exceeded")

            # Circuit breaker for backend failures
            if self._consecutive_pull_failures >= self.max_consecutive_backend_failures:
                raise BackendUnavailableError(
                    f"Backend unavailable after {self._consecutive_pull_failures} failures",
                    failure_count=self._consecutive_pull_failures,
                    last_error=self._last_backend_error,
                )

            try:
                event = await self.backend.pull(timeout=1.0)
                self._consecutive_pull_failures = 0  # Reset on success
                self._last_backend_error = None
            except Exception as e:
                self._consecutive_pull_failures += 1
                self._stats.backend_errors += 1
                self._last_backend_error = str(e)
                self._log.error(
                    f"Backend pull failed ({self._consecutive_pull_failures}/"
                    f"{self.max_consecutive_backend_failures}): {e}",
                    extra={
                        "error": str(e),
                        "consecutive_failures": self._consecutive_pull_failures,
                    },
                )
                continue

            if event is None:
                continue

            self._stats.events_processed += 1
            handler_failed = False
            handler_error: Exception | None = None

            for organ in self.organs:
                if event.event_type not in organ.listens_to:
                    continue

                self._log.info(
                    f"Dispatching {event.event_type} to {organ.name}",
                    extra={
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "organ": organ.name,
                    },
                )

                try:
                    emitted = await self._invoke_handler(organ, event)

                    if emitted is not None:
                        events_to_enqueue = [emitted] if isinstance(emitted, Event) else emitted
                        emitted_types = []

                        for new_event in events_to_enqueue:
                            try:
                                await self.backend.enqueue(new_event)
                                emitted_types.append(new_event.event_type)
                                self._stats.events_emitted += 1
                            except Exception as e:
                                await self._handle_enqueue_failure(new_event, e)

                        if emitted_types:
                            self._log.info(
                                f"Handler {organ.name} emitted events",
                                extra={
                                    "event_id": event.id,
                                    "event_type": event.event_type,
                                    "organ": organ.name,
                                    "emitted": emitted_types,
                                },
                            )

                except EnqueueError:
                    raise  # Re-raise EnqueueError so callers can catch it

                except Exception as e:
                    handler_failed = True
                    handler_error = e
                    self._stats.handler_errors[organ.name] += 1
                    self._log.error(
                        f"Handler {organ.name} raised exception: {e}",
                        extra={
                            "event_id": event.id,
                            "event_type": event.event_type,
                            "organ": organ.name,
                            "error": str(e),
                        },
                    )

            # Handle based on handler_failure_mode
            if handler_failed:
                if self.handler_failure_mode == HandlerFailureMode.STORE:
                    # Store in DLQ and ack
                    await self.failed_event_store.store(event, handler_error)
                    self._log.warning(
                        f"Stored failed event in DLQ: {event.event_type}",
                        extra={
                            "event_id": event.id,
                            "event_type": event.event_type,
                            "error": str(handler_error),
                        },
                    )
                    try:
                        await self.backend.ack(event)
                    except Exception as e:
                        self._stats.ack_errors += 1
                        self._log.error(
                            f"Failed to ack event after DLQ store: {e}",
                            extra={
                                "event_id": event.id,
                                "event_type": event.event_type,
                                "error": str(e),
                            },
                        )
                elif self.handler_failure_mode == HandlerFailureMode.NACK:
                    # Don't ack - event stays pending for backend retry
                    self._log.warning(
                        f"Event not acked due to handler failure (will retry): {event.event_type}",
                        extra={
                            "event_id": event.id,
                            "event_type": event.event_type,
                        },
                    )
                # LOG mode: just log (already done above), ack the event
                else:
                    try:
                        await self.backend.ack(event)
                    except Exception as e:
                        self._stats.ack_errors += 1
                        self._log.error(
                            f"Failed to ack event after handler error (LOG mode): {e}",
                            extra={
                                "event_id": event.id,
                                "event_type": event.event_type,
                                "error": str(e),
                            },
                        )
            else:
                # All handlers succeeded - ack the event
                try:
                    await self.backend.ack(event)
                except Exception as e:
                    self._stats.ack_errors += 1
                    self._log.error(
                        f"Failed to ack event: {e}",
                        extra={
                            "event_id": event.id,
                            "event_type": event.event_type,
                            "error": str(e),
                        },
                    )

        return self._stats
