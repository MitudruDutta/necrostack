# Design Document

## Overview

NecroStack is a minimal, async-first event-driven micro-framework for Python 3.11+. The architecture follows a simple pipeline pattern: Events flow through a Spine dispatcher which routes them to registered Organs based on event type. The framework prioritizes simplicity and clarity over feature richness.

### Core Design Principles

1. **Minimal API Surface**: Three core classes (Event, Organ, Spine) with clear responsibilities
2. **Async-First, Sync-Friendly**: Native async support with seamless sync handler execution
3. **Pluggable Backends**: Abstract backend interface with in-memory and Redis implementations
4. **Type Safety**: Full type hints with Pydantic v2 validation
5. **No Magic**: Explicit registration via `listens_to`, no decorators or metaclass tricks

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Application                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │ Event A │    │ Event B │    │ Event C │   (User Events)│
│  └────┬────┘    └────┬────┘    └────┬────┘                │
│       │              │              │                      │
│       └──────────────┼──────────────┘                      │
│                      ▼                                      │
│              ┌───────────────┐                             │
│              │    Spine      │  (Dispatcher)               │
│              │  ┌─────────┐  │                             │
│              │  │ Backend │  │  (Queue)                    │
│              │  └─────────┘  │                             │
│              └───────┬───────┘                             │
│                      │                                      │
│       ┌──────────────┼──────────────┐                      │
│       ▼              ▼              ▼                      │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │ Organ A │    │ Organ B │    │ Organ C │   (Handlers)   │
│  └─────────┘    └─────────┘    └─────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Event Flow

1. Application or Organ emits an Event
2. Event is enqueued to the Backend
3. Spine pulls Event from Backend
4. Spine finds all Organs with matching `listens_to`
5. Spine invokes each Organ's `handle()` method
6. Returned Events are enqueued back to Backend
7. Repeat until queue is empty or max_steps reached

## Components and Interfaces

### Event (Base Class)

```python
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Any

class Event(BaseModel):
    """Base class for all events in NecroStack."""

    model_config = {"frozen": True}

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="String identifier used for routing")
    payload: dict[str, Any] = Field(default_factory=dict)

    def model_dump_jsonable(self) -> dict:
        """Return a JSON-serializable representation."""
        return self.model_dump()

```

### Organ (Base Class)

```python
from abc import ABC, abstractmethod
from typing import ClassVar, Sequence, Awaitable
from .event import Event

class Organ(ABC):
    """Base class for all event handlers."""

    listens_to: ClassVar[list[str]] = []

    @abstractmethod
    def handle(self, event: Event) -> (
        Event | Sequence[Event] | None | Awaitable[Event | Sequence[Event] | None]
    ):
        """
        Process an event.

        May be:
        - synchronous: return Event, list[Event], or None
        - asynchronous: return awaitable resolving to same types
        """
        ...
```

### Backend (Protocol)

```python
import asyncio
from .base import Backend
from ..core.event import Event

class InMemoryBackend(Backend):
    """Async FIFO backend using asyncio.Queue."""

    def __init__(self) -> None:
        self._queue = asyncio.Queue()

    async def enqueue(self, event: Event) -> None:
        await self._queue.put(event)

    async def pull(self, timeout: float | None = None) -> Event | None:
        try:
            if timeout is None:
                return await self._queue.get()
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def ack(self, event: Event) -> None:
        """No-op for in-memory backend."""
        return None

    async def close(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()

        ...
```

### Spine (Dispatcher)

```python
import inspect
import logging
from typing import Sequence
from .event import Event
from .organ import Organ
from .backends.base import Backend

class Spine:
    """Central event dispatcher."""

    def __init__(self, organs: list[Organ], backend: Backend, max_steps: int | None = None) -> None:
        self.organs = organs
        self.backend = backend
        self.max_steps = max_steps or 10_000
        self._running = False
        self.log = logging.getLogger("necrostack.spine")

    async def emit(self, event: Event) -> None:
        await self.backend.enqueue(event)

    async def _invoke_handler(self, organ: Organ, event: Event):
        handler = organ.handle
        if inspect.iscoroutinefunction(handler):
            return await handler(event)
        else:
            return handler(event)

        ...
```

## Data Models

### Event Schema

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier, auto-generated |
| timestamp | datetime | Creation time, auto-generated |
| event_type | str (ClassVar) | Event type identifier for routing |
| (payload) | varies | User-defined fields via subclassing |

### Serialization Format

Events serialize to JSON-compatible dictionaries:

```json
# Redis stream entry format (JSON serialized)
{
    "event": "<JSON string from event.model_dump()>"
}

```

### Backend Message Format (Redis)

```json
await redis.xadd(
    self.stream_key,
    {"event": json.dumps(event.model_dump())}
)

```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Event Serialization Round-Trip

*For any* valid Event instance, serializing to JSON and then deserializing should produce an Event that is equivalent to the original (same id, timestamp, event_type, and all payload fields).

**Validates: Requirements 1.4, 1.5**

### Property 2: Event Immutability and Auto-Fields

*For any* valid Event created with user-provided payload data, the resulting Event should have a non-None UUID id, a non-None timestamp, and attempting to modify any field should raise an error (frozen model).

**Validates: Requirements 1.3**

### Property 3: Invalid Event Rejection

*For any* Event subclass with required fields, instantiation with missing or type-invalid data should raise a Pydantic ValidationError.

**Validates: Requirements 1.2**

### Property 4: Event Routing Correctness

*For any* Event with a given event_type and any set of Organs, the Spine should invoke the `handle()` method of exactly those Organs whose `listens_to` list contains that event_type.

**Validates: Requirements 2.2, 2.3, 3.3**

### Property 5: Handler Return Value Processing

*For any* Organ handler invocation, if the handler returns Event(s), those Events should be enqueued to the backend; if the handler returns None, no Events should be enqueued.

**Validates: Requirements 2.6, 2.7**

### Property 6: Organ Invocation Order

*For any* Event that matches multiple Organs, the Spine should invoke their handlers in the exact order the Organs were provided to the Spine constructor (deterministic ordering).

**Validates: Requirements 3.4**

### Property 7: Error Resilience

*For any* sequence of Events where some handlers raise exceptions, the Spine should continue processing subsequent Events (exceptions should not halt the processing loop).

**Validates: Requirements 3.5**

### Property 8: Max-Steps Termination

*For any* Spine configured with max_steps=N, the processing loop should terminate after at most N event processing iterations, regardless of how many events are in the queue.

**Validates: Requirements 3.7**

### Property 9: Backend FIFO Ordering

*For any* sequence of Events enqueued to the in-memory backend, dequeuing should return them in the same order they were enqueued (FIFO).

**Validates: Requirements 4.2**

### Property 10: Invalid Organ Signature Detection

*For any* Organ subclass where the `handle()` method has an incorrect signature (wrong parameter count or types), registration with Spine should raise a descriptive error.

**Validates: Requirements 7.2**

## Error Handling

### Event Validation Errors

- Pydantic `ValidationError` raised on invalid Event instantiation
- Error includes field-level details for debugging
- No partial Event objects created on validation failure

### Handler Exceptions

- Exceptions in `handle()` are caught by Spine
- Error is logged with event context (id, type)
- Processing continues with next event
- Failed events are not re-enqueued (MVP behavior)

### Backend Errors

- Connection failures trigger reconnection attempts (Redis)
- Timeout on empty queue returns `None`, not exception
- Backend close errors are logged but don't propagate

### Spine Lifecycle Errors

- Invalid Organ registration raises `TypeError` at init time
- Duplicate event_type in single Organ is allowed
- Empty organs list is valid (events are consumed but not processed)

## Testing Strategy

### Property-Based Testing Framework

The project will use **Hypothesis** for property-based testing. Hypothesis is the standard PBT library for Python with excellent Pydantic integration.

Configuration:
- Minimum 100 examples per property test
- Explicit seed logging for reproducibility
- Custom strategies for Event and Organ generation

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures and strategies
├── test_event.py            # Event validation and serialization
├── test_organ.py            # Organ registration and handling
├── test_spine.py            # Dispatcher logic and lifecycle
├── test_backend_memory.py   # In-memory backend
└── test_backend_redis.py    # Redis backend (integration)
```

### Property Test Annotations

Each property-based test must include a comment linking to the design document:

```python
# **Feature: necrostack-framework, Property 1: Event Serialization Round-Trip**
@given(event=valid_events())
def test_event_round_trip(event: Event):
    ...
```

### Unit Tests

Unit tests complement property tests for:
- Specific edge cases (empty strings, boundary values)
- Integration points (Redis connection handling)
- Error message verification
- Async/sync handler execution paths

### Test Coverage Goals

- All correctness properties implemented as Hypothesis tests
- Critical paths have unit test coverage
- Redis tests run against real Redis (not mocked) in CI

## Project Structure

```
necrostack/
├── __init__.py              # Public API exports
├── core/
│   ├── __init__.py
│   ├── event.py             # Event base class
│   ├── organ.py             # Organ base class
│   └── spine.py             # Spine dispatcher
├── backends/
│   ├── __init__.py
│   ├── base.py              # Backend protocol
│   ├── memory.py            # In-memory backend
│   └── redis.py             # Redis Streams backend
└── py.typed                 # PEP 561 marker

tests/
├── conftest.py
├── test_event.py
├── test_organ.py
├── test_spine.py
├── test_backend_memory.py
└── test_backend_redis.py

pyproject.toml
README.md
.gitignore
```
