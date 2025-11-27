"""Organ base class for NecroStack event handlers."""

from abc import ABC, abstractmethod
from typing import Awaitable, ClassVar

from necrostack.core.event import Event


class Organ(ABC):
    """Base class for event handlers.

    Organs are pluggable components that handle events and may emit new events.
    Each Organ declares which event types it listens to via the `listens_to`
    class attribute.

    Note: Validation of `listens_to` happens in Spine during registration,
    not in the Organ itself.
    """

    listens_to: ClassVar[list[str]] = []

    def __init__(self, name: str | None = None) -> None:
        """Initialize the Organ.

        Args:
            name: Optional name for the organ. Defaults to the class name.
        """
        self.name = name or self.__class__.__name__

    @abstractmethod
    def handle(
        self,
        event: Event,
    ) -> Event | list[Event] | None | Awaitable[Event | list[Event] | None]:
        """Handle an incoming event.

        Args:
            event: The event to handle.

        Returns:
            An Event, a list of Events, None, or an awaitable resolving to the same.
        """
        ...
