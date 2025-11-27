"""In-memory backend using asyncio.Queue for FIFO event storage."""

import asyncio

from necrostack.core.event import Event


class InMemoryBackend:
    """Async FIFO backend using asyncio.Queue.

    This backend is suitable for development and testing. It provides
    no durability guarantees—events are lost if the process terminates.

    The queue lives entirely within this backend; Spine does not maintain
    any internal event storage.
    """

    def __init__(self) -> None:
        """Initialize the in-memory queue."""
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    async def enqueue(self, event: Event) -> None:
        """Store an event in FIFO order.

        Args:
            event: The Event to enqueue.
        """
        await self._queue.put(event)

    async def pull(self, timeout: float = 1.0) -> Event | None:
        """Retrieve the next event, blocking up to timeout seconds.

        Args:
            timeout: Maximum seconds to wait for an event.

        Returns:
            The next Event in FIFO order, or None if timeout expires.
        """
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None

    async def ack(self, event: Event) -> None:
        """Acknowledge event processing (no-op for in-memory backend).

        Args:
            event: The Event to acknowledge.
        """
        pass
