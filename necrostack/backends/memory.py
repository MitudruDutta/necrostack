"""In-memory backend for NecroStack."""

import asyncio

from necrostack.core.event import Event


class InMemoryBackend:
    """Async FIFO backend using asyncio.Queue.
    
    This backend is suitable for development and testing. Events are stored
    in memory and will be lost on process termination.
    """

    def __init__(self) -> None:
        """Initialize the in-memory backend with an empty queue."""
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    async def enqueue(self, event: Event) -> None:
        """Add an event to the queue.
        
        Args:
            event: The event to enqueue
        """
        await self._queue.put(event)

    async def pull(self, timeout: float | None = None) -> Event | None:
        """Retrieve the next event from the queue in FIFO order.
        
        Args:
            timeout: Maximum time to wait for an event in seconds.
                    None means wait indefinitely.
        
        Returns:
            The next event, or None if timeout is reached with no event available.
        """
        try:
            if timeout is None:
                return await self._queue.get()
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def ack(self, event: Event) -> None:
        """Acknowledge successful processing of an event.
        
        This is a no-op for the in-memory backend.
        
        Args:
            event: The event to acknowledge
        """
        pass

    async def close(self) -> None:
        """Close the backend and clear the queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
