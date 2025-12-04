"""Core components for NecroStack event-driven framework.

This module exposes the primary types, constants, and utilities:

Types:
    Event: Immutable, validated event message with UUID, timestamp, type, and payload.
    Organ: Abstract base class for event handlers.
    Spine: Central event dispatcher with configurable failure handling.
    SpineStats: Statistics dataclass from a Spine run.

Failure Handling:
    EnqueueFailureMode: Enum for failure strategies (FAIL, RETRY, STORE).
    EnqueueError: Raised when enqueue fails in FAIL/RETRY mode.
    BackendUnavailableError: Raised when backend fails beyond threshold.
    FailedEventStore: Protocol for storing failed events.
    InMemoryFailedEventStore: Simple in-memory implementation.

Constants:
    MAX_PAYLOAD_SIZE: Maximum payload size in bytes (1MB).
"""

from necrostack.core.event import MAX_PAYLOAD_SIZE, Event
from necrostack.core.organ import Organ
from necrostack.core.spine import (
    BackendUnavailableError,
    EnqueueError,
    EnqueueFailureMode,
    FailedEventStore,
    InMemoryFailedEventStore,
    Spine,
    SpineStats,
)

__all__ = [
    "Event",
    "MAX_PAYLOAD_SIZE",
    "Organ",
    "Spine",
    "SpineStats",
    "EnqueueFailureMode",
    "EnqueueError",
    "BackendUnavailableError",
    "FailedEventStore",
    "InMemoryFailedEventStore",
]
