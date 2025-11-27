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
import logging
from collections import defaultdict
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from necrostack.core.event import Event
from necrostack.core.logging import configure_spine_logger
from necrostack.core.organ import Organ

if TYPE_CHECKING:
    from necrostack.backends.base import Backend


class EnqueueFailureMode(Enum):
    """Strategy for handling enqueue failures."""

    FAIL = "fail"  # Re-raise exception to stop processing
    RETRY = "retry"  # Retry with exponential backoff before failing
    STORE = "store"  # Store in dead-letter store for later retry


class FailedEventStore(Protocol):
    """Protocol for storing failed events for later retry."""

    async def store(self, event: Event, error: Exception) -> None:
        """Store a failed event.

        Args:
            event: The Event that failed to enqueue.
            error: The exception that caused the failure.
        """
        ...


class InMemoryFailedEventStore:
    """Simple in-memory failed event store for testing."""

    def __init__(self) -> None:
        self.events: list[tuple[Event, Exception]] = []

    async def store(self, event: Event, error: Exception) -> None:
        """Store a failed event in memory."""
        self.events.append((event, error))


class Spine:
    """Central event dispatcher.

    The Spine pulls events from a backend, routes them to Organs whose
    `listens_to` contains the event's `event_type`, and enqueues any
    returned events back to the backend.

    Attributes:
        organs: List of Organ instances to dispatch events to.
        backend: The Backend implementation for event queuing.
        max_steps: Maximum number of events to process before raising RuntimeError.
        enqueue_failure_mode: Strategy for handling enqueue failures.
        failed_event_store: Store for failed events (used with STORE mode).
        retry_attempts: Number of retry attempts (used with RETRY mode).
        retry_base_delay: Base delay in seconds for exponential backoff.
    """

    def __init__(
        self,
        organs: list[Organ],
        backend: "Backend",
        max_steps: int = 10_000,
        enqueue_failure_mode: EnqueueFailureMode = EnqueueFailureMode.STORE,
        failed_event_store: FailedEventStore | None = None,
        retry_attempts: int = 3,
        retry_base_delay: float = 0.1,
    ) -> None:
        """Initialize the Spine dispatcher.

        Args:
            organs: List of Organ instances to register.
            backend: Backend implementation for event queuing.
            max_steps: Maximum events to process (default 10,000).
            enqueue_failure_mode: Strategy for handling enqueue failures.
            failed_event_store: Store for failed events. If None and mode is STORE,
                an InMemoryFailedEventStore is created.
            retry_attempts: Number of retry attempts for RETRY mode (default 3).
            retry_base_delay: Base delay in seconds for exponential backoff (default 0.1).

        Raises:
            TypeError: If any organ's listens_to is not a list of strings.
        """
        self.organs = organs
        self.backend = backend
        self.max_steps = max_steps
        self.enqueue_failure_mode = enqueue_failure_mode
        self.failed_event_store = failed_event_store or InMemoryFailedEventStore()
        self.retry_attempts = retry_attempts
        self.retry_base_delay = retry_base_delay
        self._log = configure_spine_logger()
        self._running = False
        self._enqueue_failures: dict[str, int] = defaultdict(int)

        # Validate organs during registration (Requirements 2.3, 3.1)
        self._validate_organs()

    def _validate_organs(self) -> None:
        """Validate that all organs have valid listens_to attributes.

        Raises:
            TypeError: If listens_to is not a list or contains non-strings.
        """
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


    async def _invoke_handler(
        self, organ: Organ, event: Event
    ) -> Event | list[Event] | None:
        """Invoke an organ's handler, handling both sync and async handlers.

        Args:
            organ: The Organ to invoke.
            event: The Event to pass to the handler.

        Returns:
            The handler's return value (Event, list of Events, or None).
        """
        result = organ.handle(event)
        # Handle async handlers by awaiting them (Requirement 3.4)
        if inspect.iscoroutine(result):
            return await result
        return result

    def stop(self) -> None:
        """Signal the Spine to stop processing after the current event."""
        self._running = False

    def get_enqueue_failure_count(self, event_type: str | None = None) -> int:
        """Get the count of enqueue failures.

        Args:
            event_type: If provided, return failures for this event type only.
                If None, return total failures across all event types.

        Returns:
            The number of enqueue failures.
        """
        if event_type is not None:
            return self._enqueue_failures.get(event_type, 0)
        return sum(self._enqueue_failures.values())

    async def _handle_enqueue_failure(self, event: Event, error: Exception) -> None:
        """Handle an enqueue failure according to the configured strategy.

        Args:
            event: The Event that failed to enqueue.
            error: The exception that caused the failure.

        Raises:
            Exception: Re-raises the error if mode is FAIL or RETRY exhausted.
        """
        # Increment metrics counter
        self._enqueue_failures[event.event_type] += 1

        if self.enqueue_failure_mode == EnqueueFailureMode.FAIL:
            self._log.error(
                f"Enqueue failed (mode=fail), stopping: {error}",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "error": str(error),
                    "failure_mode": "fail",
                    "total_failures": self._enqueue_failures[event.event_type],
                },
            )
            raise error

        elif self.enqueue_failure_mode == EnqueueFailureMode.RETRY:
            last_error = error
            for attempt in range(self.retry_attempts):
                delay = self.retry_base_delay * (2**attempt)
                self._log.warning(
                    f"Enqueue failed, retrying in {delay}s (attempt {attempt + 1}/{self.retry_attempts})",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "error": str(last_error),
                        "failure_mode": "retry",
                        "attempt": attempt + 1,
                        "max_attempts": self.retry_attempts,
                        "delay": delay,
                    },
                )
                await asyncio.sleep(delay)
                try:
                    await self.backend.enqueue(event)
                    self._log.info(
                        f"Enqueue succeeded on retry attempt {attempt + 1}",
                        extra={
                            "event_id": str(event.id),
                            "event_type": event.event_type,
                            "attempt": attempt + 1,
                        },
                    )
                    return
                except Exception as e:
                    last_error = e

            # All retries exhausted
            self._log.error(
                f"Enqueue failed after {self.retry_attempts} retries: {last_error}",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "error": str(last_error),
                    "failure_mode": "retry",
                    "total_failures": self._enqueue_failures[event.event_type],
                },
            )
            raise last_error

        else:  # STORE mode
            self._log.warning(
                f"Enqueue failed, storing in dead-letter store: {error}",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "error": str(error),
                    "failure_mode": "store",
                    "total_failures": self._enqueue_failures[event.event_type],
                },
            )
            await self.failed_event_store.store(event, error)

    async def run(self, start_event: Event | None = None) -> None:
        """Run the event dispatch loop.

        Pulls events from the backend, routes them to matching Organs,
        and enqueues any returned events.

        Args:
            start_event: Optional initial event to enqueue before starting.

        Raises:
            RuntimeError: If max_steps is exceeded.
        """
        steps = 0
        self._running = True

        # Enqueue start event if provided
        if start_event is not None:
            try:
                await self.backend.enqueue(start_event)
            except Exception as e:
                self._log.error(
                    f"Failed to enqueue start event: {e}",
                    extra={
                        "event_id": str(start_event.id),
                        "event_type": start_event.event_type,
                        "error": str(e),
                    },
                )
                raise

        # Main dispatch loop (Requirement 3.2)
        while self._running:
            # Check max_steps before processing (Requirement 3.7)
            if steps >= self.max_steps:
                raise RuntimeError("Max steps exceeded")

            # Pull next event from backend
            try:
                event = await self.backend.pull(timeout=1.0)
            except Exception as e:
                self._log.error(
                    f"Backend pull failed: {e}",
                    extra={"error": str(e)},
                )
                # Continue loop on backend errors - don't crash
                continue

            # On timeout (None), continue the loop (Requirement 3.8)
            if event is None:
                continue

            steps += 1

            # Route to matching organs (Requirement 3.3)
            for organ in self.organs:
                if event.event_type not in organ.listens_to:
                    continue

                self._log.info(
                    f"Dispatching {event.event_type} to {organ.name}",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "organ": organ.name,
                    },
                )

                try:
                    # Invoke handler (sync or async) - Requirement 3.4
                    emitted = await self._invoke_handler(organ, event)

                    # Enqueue returned events (Requirement 3.5)
                    if emitted is not None:
                        events_to_enqueue = (
                            [emitted] if isinstance(emitted, Event) else emitted
                        )
                        emitted_types = []

                        for new_event in events_to_enqueue:
                            try:
                                await self.backend.enqueue(new_event)
                                emitted_types.append(new_event.event_type)
                            except Exception as e:
                                await self._handle_enqueue_failure(new_event, e)

                        if emitted_types:
                            self._log.info(
                                f"Handler {organ.name} emitted events",
                                extra={
                                    "event_id": str(event.id),
                                    "event_type": event.event_type,
                                    "organ": organ.name,
                                    "emitted": emitted_types,
                                },
                            )

                except Exception as e:
                    # Log handler exceptions without crashing the loop
                    self._log.error(
                        f"Handler {organ.name} raised exception: {e}",
                        extra={
                            "event_id": str(event.id),
                            "event_type": event.event_type,
                            "organ": organ.name,
                            "error": str(e),
                        },
                    )
                    # Continue to next organ - don't crash the loop
