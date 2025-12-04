"""In-memory backend using asyncio.Queue for FIFO event storage."""

import asyncio

from necrostack.core.event import Event


class BackendFullError(Exception):
    """Raised when backend queue is full and cannot accept more events."""

    pass


class InMemoryBackend:
    """Async FIFO backend using asyncio.Queue.

    This backend is suitable for development and testing. It provides
    no durability guarantees—events are lost if the process terminates.

    The queue lives entirely within this backend; Spine does not maintain
    any internal event storage.

    Args:
        max_size: Maximum queue size. 0 means unbounded (default).
    """

    def __init__(self, max_size: int = 0) -> None:
        """Initialize the in-memory queue."""
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size

    async def enqueue(self, event: Event) -> None:
        """Store an event in FIFO order.

        Args:
            event: The Event to enqueue.

        Raises:
            BackendFullError: If queue is full (when max_size > 0).
        """
        if self._max_size > 0:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                raise BackendFullError(f"Queue full (max_size={self._max_size}), cannot enqueue event")
        else:
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

    def qsize(self) -> int:
        """Return current queue size."""
        return self._queue.qsize()
