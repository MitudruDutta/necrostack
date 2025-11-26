"""Organ base class for NecroStack."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Awaitable, ClassVar, Sequence

if TYPE_CHECKING:
    from .event import Event


class Organ(ABC):
    """Base class for all event handlers in NecroStack.
    
    Organs are modular components that listen to specific event types
    and process them via the handle() method.
    
    Usage:
        class MyOrgan(Organ):
            listens_to = ["my_event_type"]
            
            def handle(self, event: Event) -> Event | None:
                # Process event
                return None
    """

    listens_to: ClassVar[list[str]] = []

    @abstractmethod
    def handle(
        self, event: "Event"
    ) -> (
        "Event"
        | Sequence["Event"]
        | None
        | Awaitable["Event" | Sequence["Event"] | None]
    ):
        """Process an event.
        
        May be synchronous or asynchronous. Return values:
        - Event: Single event to be enqueued
        - Sequence[Event]: Multiple events to be enqueued
        - None: Terminal step, no further action
        - Awaitable: Async version of any of the above
        
        Args:
            event: The event to process
            
        Returns:
            Event(s) to enqueue, or None for terminal processing
        """
        ...
