"""Backend protocol for NecroStack."""

from typing import Protocol

from necrostack.core.event import Event


class Backend(Protocol):
    """Protocol defining the interface for event queue backends.
    
    Backends are responsible for storing, retrieving, and acknowledging
    events in the NecroStack processing pipeline.
    """

    async def enqueue(self, event: Event) -> None:
        """Add an event to the queue.
        
        Args:
            event: The event to enqueue
        """
        ...

    async def pull(self, timeout: float | None = None) -> Event | None:
        """Retrieve the next event from the queue.
        
        Args:
            timeout: Maximum time to wait for an event in seconds.
                    None means wait indefinitely.
        
        Returns:
            The next event, or None if timeout is reached with no event available.
        """
        ...

    async def ack(self, event: Event) -> None:
        """Acknowledge successful processing of an event.
        
        Args:
            event: The event to acknowledge
        """
        ...

    async def close(self) -> None:
        """Close the backend and release resources."""
        ...
