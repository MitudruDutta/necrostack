"""Backend protocol for event queuing.

ALL queue logic lives in backends, not Spine. The Spine dispatcher
delegates all event storage and retrieval to the backend implementation.
"""

from typing import Protocol

from necrostack.core.event import Event


class Backend(Protocol):
    """Protocol defining the interface for event queue backends.

    Backends are responsible for:
    - Storing events (enqueue)
    - Retrieving events in order (pull)
    - Acknowledging processed events (ack)

    The Spine dispatcher does NOT maintain any internal queue—all queue
    operations go through the backend.
    """

    async def enqueue(self, event: Event) -> None:
        """Store an event in the queue.

        Args:
            event: The Event to enqueue.
        """
        ...

    async def pull(self, timeout: float = 1.0) -> Event | None:
        """Retrieve the next event from the queue.

        Args:
            timeout: Maximum seconds to wait for an event.

        Returns:
            The next Event, or None if timeout expires with no event available.
        """
        ...

    async def ack(self, event: Event) -> None:
        """Acknowledge that an event has been processed.

        For non-durable backends, this may be a no-op.

        Args:
            event: The Event to acknowledge.
        """
        ...
