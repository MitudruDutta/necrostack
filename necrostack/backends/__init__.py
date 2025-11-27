"""Backend implementations for event queuing."""

from necrostack.backends.base import Backend
from necrostack.backends.inmemory import InMemoryBackend

__all__ = ["Backend", "InMemoryBackend"]
