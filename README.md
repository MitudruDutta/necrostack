# NecroStack

Minimal async-first event-driven micro-framework for Python 3.11+.

## Features

- **Event** — Typed, immutable, validated message objects using Pydantic 
- **Organ** — Pluggable modules that listen to specific event types
- **Spine** — Queue-based dispatcher that routes events to Organs

## Installation

```bash
pip install necrostack
```

For Redis Streams backend support:

```bash
pip install necrostack[redis]
```

## Quick Start

```python
import asyncio
from necrostack import Event, Organ, Spine
from necrostack.backends import InMemoryBackend

# Define an event
class UserCreated(Event):
    event_type: str = "user.created"

# Define an organ (handler)
class WelcomeEmailOrgan(Organ):
    listens_to = ["user.created"]

    def handle(self, event: Event) -> None:
        print(f"Sending welcome email for event {event.id}")

# Run the system
async def main():
    backend = InMemoryBackend()
    spine = Spine(
        organs=[WelcomeEmailOrgan()],
        backend=backend,
        max_steps=100
    )

    await spine.emit(UserCreated(payload={"user_id": "123"}))
    await spine.run()

asyncio.run(main())
```

## Core Concepts

### Events

Events are immutable Pydantic models with automatic ID and timestamp generation:

```python
from necrostack import Event

class OrderPlaced(Event):
    event_type: str = "order.placed"

event = OrderPlaced(payload={"order_id": "456", "amount": 99.99})
print(event.id)        # Auto-generated UUID
print(event.timestamp) # Auto-generated datetime
```

### Organs

Organs are event handlers that declare which events they listen to:

```python
from necrostack import Organ, Event

class InventoryOrgan(Organ):
    listens_to = ["order.placed"]

    async def handle(self, event: Event) -> Event | None:
        # Process the event
        # Optionally return new events to emit
        return None
```

### Spine

The Spine is the central dispatcher that routes events to organs:

```python
from necrostack import Spine
from necrostack.backends import InMemoryBackend

spine = Spine(
    organs=[InventoryOrgan(), ShippingOrgan()],
    backend=InMemoryBackend(),
    max_steps=1000  # Prevent infinite loops
)
```

## Backends

### In-Memory Backend (Development)

```python
from necrostack.backends import InMemoryBackend

backend = InMemoryBackend()
```

### Redis Streams Backend (Production)

```python
from necrostack.backends import RedisBackend

backend = RedisBackend(url="redis://localhost:6379", stream_key="events")
```

## License

MIT
