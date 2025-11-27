# NecroStack

A minimal, async-first event-driven micro-framework for Python 3.11+.

## What is NecroStack?

NecroStack provides three core abstractions for building event-driven applications:

- **Event** — An immutable, Pydantic-validated message with automatic ID and timestamp
- **Organ** — A pluggable event handler that processes events and may emit new ones
- **Spine** — A queue-driven dispatcher that routes events to Organs

## Features

- 🔄 Async-first design with sync handler support
- ✅ Pydantic validation for type-safe events
- 🔌 Pluggable backends (InMemory, Redis Streams)
- 📝 Structured JSON logging
- 🛡️ Loop protection with configurable max steps
- 🎯 Simple, composable architecture

## Installation

```bash
# Basic installation
pip install necrostack

# With Redis support
pip install necrostack[redis]

# Development (editable mode)
pip install -e ".[dev]"
```

## Quickstart

```python
import asyncio
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import Spine
from necrostack.backends.inmemory import InMemoryBackend

class GreetOrgan(Organ):
    listens_to = ["GREET"]

    def handle(self, event: Event) -> Event:
        name = event.payload.get("name", "World")
        return Event(event_type="GREETED", payload={"message": f"Hello, {name}!"})

class PrintOrgan(Organ):
    listens_to = ["GREETED"]

    def handle(self, event: Event) -> None:
        print(event.payload["message"])

async def main():
    organs = [GreetOrgan(), PrintOrgan()]
    backend = InMemoryBackend()
    spine = Spine(organs=organs, backend=backend)

    start_event = Event(event_type="GREET", payload={"name": "NecroStack"})
    await spine.run(start_event)

asyncio.run(main())
```

## Project Structure

```
necrostack/
├── core/           # Event, Organ, Spine
├── backends/       # InMemoryBackend, RedisBackend
├── utils/          # Helpers and utilities
└── apps/           # Demo applications (Séance, ETL)
```

## Backends

### InMemoryBackend (Development)

Simple async FIFO queue for development and testing:

```python
from necrostack.backends.inmemory import InMemoryBackend

backend = InMemoryBackend()
```

### RedisBackend (Production)

Redis Streams backend for persistence and durability:

```python
from necrostack.backends.redis_backend import RedisBackend

backend = RedisBackend(redis_url="redis://localhost:6379", stream_key="necrostack:events")
```

**MVP Limitations:**
- No consumer group support (Phase 2)
- `ack()` is a no-op
- At-least-once semantics

## Roadmap

- [ ] Consumer group support for RedisBackend
- [ ] Dead-letter queue
- [ ] Retry & backoff logic
- [ ] Metrics and observability hooks

## License

MIT
