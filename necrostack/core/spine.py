"""Spine dispatcher for NecroStack event routing.

The Spine is the central dispatcher that:
- Pulls events from a backend
- Routes them to matching Organs based on event_type
- Enqueues any returned events back to the backend

IMPORTANT: Spine does NOT maintain any internal queue. All queue operations
go through the backend.
"""

import inspect
import logging
from typing import TYPE_CHECKING

from necrostack.core.event import Event
from necrostack.core.logging import configure_spine_logger
from necrostack.core.organ import Organ

if TYPE_CHECKING:
    from necrostack.backends.base import Backend


class Spine:
    """Central event dispatcher.

    The Spine pulls events from a backend, routes them to Organs whose
    `listens_to` contains the event's `event_type`, and enqueues any
    returned events back to the backend.

    Attributes:
        organs: List of Organ instances to dispatch events to.
        backend: The Backend implementation for event queuing.
        max_steps: Maximum number of events to process before raising RuntimeError.
    """

    def __init__(
        self,
        organs: list[Organ],
        backend: "Backend",
        max_steps: int = 10_000,
    ) -> None:
        """Initialize the Spine dispatcher.

        Args:
            organs: List of Organ instances to register.
            backend: Backend implementation for event queuing.
            max_steps: Maximum events to process (default 10,000).

        Raises:
            TypeError: If any organ's listens_to is not a list of strings.
        """
        self.organs = organs
        self.backend = backend
        self.max_steps = max_steps
        self._log = configure_spine_logger()
        self._running = False

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
                                self._log.error(
                                    f"Failed to enqueue event: {e}",
                                    extra={
                                        "event_id": str(new_event.id),
                                        "event_type": new_event.event_type,
                                        "error": str(e),
                                    },
                                )

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
