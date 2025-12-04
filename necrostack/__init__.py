"""NecroStack - Async-first event-driven micro-framework for Python."""

from necrostack.backends import Backend, InMemoryBackend, RedisBackend
from necrostack.core import (
    BackendUnavailableError,
    EnqueueError,
    EnqueueFailureMode,
    Event,
    FailedEventStore,
    HandlerFailureMode,
    InMemoryFailedEventStore,
    Organ,
    Spine,
    SpineStats,
)

__version__ = "0.1.0"

__all__ = [
    # Core
    "Event",
    "Organ",
    "Spine",
    "SpineStats",
    # Failure handling
    "EnqueueFailureMode",
    "HandlerFailureMode",
    "EnqueueError",
    "BackendUnavailableError",
    "FailedEventStore",
    "InMemoryFailedEventStore",
    # Backends
    "Backend",
    "InMemoryBackend",
    "RedisBackend",
    # Meta
    "__version__",
]
