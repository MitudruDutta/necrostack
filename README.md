# NecroStack

A minimal, async-first event-driven micro-framework for Python, designed for building reactive, composable systems with formal guarantees on event flow and processing semantics.

## Abstract

NecroStack implements a lightweight event-driven architecture (EDA) pattern that decouples event producers from consumers through a central dispatcher mechanism. The framework provides three core abstractions—**Event**, **Organ**, and **Spine**—that together form a complete reactive processing pipeline with pluggable storage backends, structured observability, and configurable fault tolerance strategies.

The design prioritizes:
- **Composability**: Independent, single-responsibility handlers that can be combined arbitrarily
- **Testability**: Pure functional handlers with deterministic behavior
- **Observability**: Structured JSON logging with correlation IDs throughout the event lifecycle
- **Fault Isolation**: Configurable failure modes that prevent cascade failures

## Theoretical Foundation

### Event-Driven Architecture (EDA)

NecroStack implements the **Event-Carried State Transfer** pattern, where events carry all necessary state for processing, eliminating the need for shared mutable state between handlers. This approach provides several formal properties:

1. **Temporal Decoupling**: Producers and consumers operate independently in time
2. **Spatial Decoupling**: Components have no direct references to each other
3. **Synchronization Decoupling**: Asynchronous communication eliminates blocking dependencies

### Processing Model

The framework follows a **single-threaded cooperative multitasking** model using Python's `asyncio`. Events are processed sequentially from a FIFO queue, with each handler potentially emitting zero or more new events that are enqueued for subsequent processing.

```
┌─────────────────────────────────────────────────────────────────┐
│                         Event Flow                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐     │
│   │ Backend │───▶│  Spine  │───▶│  Organ  │───▶│ Backend │     │
│   │ (pull)  │    │(dispatch)│   │(handle) │    │(enqueue)│     │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘     │
│        ▲                                            │          │
│        └────────────────────────────────────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Termination Guarantees

To prevent infinite event loops, NecroStack enforces a configurable `max_steps` limit (default: 10,000). When exceeded, the dispatcher raises a `RuntimeError`, ensuring bounded execution time for any event chain.

## Core Abstractions

### Event

An **Event** is an immutable, Pydantic-validated message representing a discrete occurrence in the system.

```python
from necrostack.core.event import Event

event = Event(
    event_type="ORDER_PLACED",
    payload={"order_id": "12345", "amount": 99.99}
)
```

**Properties:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID v4, auto-generated |
| `timestamp` | `datetime` | UTC timestamp, auto-generated |
| `event_type` | `str` | Non-empty string identifier (whitespace-stripped) |
| `payload` | `dict[str, Any]` | Arbitrary JSON-serializable data |

**Invariants:**
- Events are frozen (immutable) after creation
- `event_type` must be non-empty after whitespace stripping
- Extra fields are forbidden (`extra="forbid"`)

### Organ

An **Organ** is a pluggable event handler that subscribes to specific event types and may emit new events.

```python
from necrostack.core.organ import Organ
from necrostack.core.event import Event

class OrderProcessor(Organ):
    listens_to = ["ORDER_PLACED"]
    
    def handle(self, event: Event) -> Event | list[Event] | None:
        # Process the order and emit confirmation
        return Event(
            event_type="ORDER_CONFIRMED",
            payload={"order_id": event.payload["order_id"]}
        )
```

**Handler Signatures:**
- Synchronous: `def handle(self, event: Event) -> Event | list[Event] | None`
- Asynchronous: `async def handle(self, event: Event) -> Event | list[Event] | None`

**Design Principles:**
- Single Responsibility: Each Organ handles one logical concern
- Stateless Preferred: Handlers should be pure functions when possible
- Explicit Subscriptions: `listens_to` declares intent clearly

### Spine

The **Spine** is the central dispatcher that orchestrates event routing between Organs and the storage backend.

```python
from necrostack.core.spine import Spine, EnqueueFailureMode
from necrostack.backends.inmemory import InMemoryBackend

spine = Spine(
    organs=[OrderProcessor(), NotificationSender()],
    backend=InMemoryBackend(),
    max_steps=10_000,
    enqueue_failure_mode=EnqueueFailureMode.STORE
)

await spine.run(start_event)
```

**Configuration Options:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `organs` | `list[Organ]` | required | Registered event handlers |
| `backend` | `Backend` | required | Storage backend implementation |
| `max_steps` | `int` | 10,000 | Maximum events before RuntimeError |
| `enqueue_failure_mode` | `EnqueueFailureMode` | STORE | Failure handling strategy |
| `retry_attempts` | `int` | 3 | Retry count for RETRY mode |
| `retry_base_delay` | `float` | 0.1 | Base delay (seconds) for exponential backoff |

**Failure Modes:**
- `FAIL`: Re-raise exception immediately, halt processing
- `RETRY`: Exponential backoff retry before failing
- `STORE`: Persist to dead-letter store, continue processing

## Backend Architecture

Backends implement the `Backend` protocol, providing a consistent interface for event persistence:

```python
class Backend(Protocol):
    async def enqueue(self, event: Event) -> None: ...
    async def pull(self, timeout: float = 1.0) -> Event | None: ...
    async def ack(self, event: Event) -> None: ...
```

### InMemoryBackend

A non-durable FIFO queue using `asyncio.Queue`, suitable for development and testing.

```python
from necrostack.backends.inmemory import InMemoryBackend

backend = InMemoryBackend()
```

**Characteristics:**
- Zero external dependencies
- No persistence (events lost on process termination)
- Ideal for unit testing and local development

### RedisBackend

A durable backend using Redis Streams for persistent event storage with automatic reconnection.

```python
from necrostack.backends.redis_backend import RedisBackend

backend = RedisBackend(
    redis_url="redis://localhost:6379",
    stream_key="myapp:events"
)
```

**Characteristics:**
- Uses `XADD`/`XREAD` for stream operations
- Automatic reconnection on connection failures
- JSON serialization via Pydantic's `model_dump()`
- Blocking reads with configurable timeout

**Features:**
- Consumer groups with `XREADGROUP`/`XACK` for at-least-once delivery
- Automatic pending message recovery via `XPENDING`/`XCLAIM`
- Dead-letter queue for poison messages (configurable max retries)
- Connection pooling and automatic reconnection
- Health checks and metrics tracking

**Configuration Options:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `redis_url` | `str` | required | Redis connection URL |
| `stream_key` | `str` | `"necrostack:events"` | Redis stream key |
| `consumer_group` | `str` | `"necrostack"` | Consumer group name |
| `consumer_name` | `str` | auto-generated | Unique consumer identifier |
| `pool_size` | `int` | 10 | Connection pool size |
| `max_retries` | `int` | 3 | Max delivery attempts before DLQ |
| `claim_min_idle_ms` | `int` | 30000 | Min idle time (ms) before claiming pending messages |
| `dlq_stream` | `str` | `"{stream_key}:dlq"` | Dead-letter queue stream key |

**Health Checks & Metrics:**
```python
# Health check returns BackendHealth dataclass
health = await backend.health()
print(health.healthy)      # True/False
print(health.latency_ms)   # Response time in milliseconds
print(health.details)      # {"stream_length": 42, "consumer_group": "...", ...}

# Metrics via RedisMetrics dataclass
metrics = backend.metrics
print(metrics.events_enqueued)    # Total events added
print(metrics.events_pulled)      # Total events retrieved
print(metrics.events_acked)       # Total events acknowledged
print(metrics.events_failed)      # Total events moved to DLQ
print(metrics.reconnections)      # Connection recovery count
print(metrics.pending_recovered)  # Messages recovered via XCLAIM
```

**Consumer Groups & Message Acknowledgment:**
```python
from necrostack.backends.redis_backend import RedisBackend

# Consumer groups are created automatically on first operation
backend = RedisBackend(
    redis_url="redis://localhost:6379",
    stream_key="myapp:events",
    consumer_group="workers",
    consumer_name="worker-1",  # Unique per instance
)

# Pull and acknowledge messages
event = await backend.pull(timeout=5.0)
if event:
    # Process event...
    await backend.ack(event)  # XACK - removes from pending

# Negative acknowledge (move to DLQ immediately)
await backend.nack(event, reason="Processing failed")
```

**Pending Message Recovery:**
```python
# Pending messages are automatically recovered during pull()
# when they exceed claim_min_idle_ms (default: 30 seconds)
backend = RedisBackend(
    redis_url="redis://localhost:6379",
    claim_min_idle_ms=5000,  # Claim after 5 seconds idle
    max_retries=3,           # Move to DLQ after 3 failed attempts
)

# Recovery happens transparently - pull() checks pending first
event = await backend.pull()  # May return a recovered message
if backend.metrics.pending_recovered > 0:
    print("Recovered pending messages from failed consumers")
```

**Connection Pooling & Reconnection:**
Connection pooling (`pool_size`) and automatic reconnection are enabled by default and require no configuration. The backend automatically reconnects on connection loss and tracks reconnection count in `metrics.reconnections`.

## Observability

### Structured JSON Logging

NecroStack provides structured JSON logging with automatic correlation via event IDs:

```json
{
  "timestamp": "2024-01-15T10:30:45.123456+00:00",
  "level": "INFO",
  "message": "Dispatching ORDER_PLACED to OrderProcessor",
  "logger": "necrostack.spine",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "ORDER_PLACED",
  "organ": "OrderProcessor"
}
```

**Log Fields:**
- `timestamp`: ISO 8601 UTC timestamp
- `level`: Log level (DEBUG, INFO, WARNING, ERROR)
- `message`: Human-readable description
- `event_id`: Correlation ID for tracing
- `event_type`: Event type being processed
- `organ`: Handler name (when applicable)
- `emitted`: List of emitted event types (when applicable)

### Metrics

Enqueue failure counts are tracked per event type:

```python
# Get total failures
total = spine.get_enqueue_failure_count()

# Get failures for specific event type
order_failures = spine.get_enqueue_failure_count("ORDER_PLACED")
```

## Installation

```bash
# Core installation
pip install necrostack

# With Redis support
pip install necrostack[redis]

# Development dependencies
pip install necrostack[dev]

# All dependencies
pip install necrostack[all]
```

**Requirements:**
- Python 3.11+
- pydantic >= 2.0
- redis >= 5.0 (optional, for RedisBackend)

## Usage Examples

### Basic Event Chain

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
    spine = Spine(
        organs=[GreetOrgan(), PrintOrgan()],
        backend=InMemoryBackend()
    )
    await spine.run(Event(event_type="GREET", payload={"name": "NecroStack"}))

asyncio.run(main())
```

### Async Handler with External I/O

```python
class AsyncDataFetcher(Organ):
    listens_to = ["FETCH_DATA"]

    async def handle(self, event: Event) -> Event:
        url = event.payload["url"]
        # Simulate async HTTP request
        await asyncio.sleep(0.1)
        return Event(
            event_type="DATA_FETCHED",
            payload={"url": url, "data": {"status": "ok"}}
        )
```

### Multi-Event Emission

```python
class OrderSplitter(Organ):
    listens_to = ["BULK_ORDER"]

    def handle(self, event: Event) -> list[Event]:
        items = event.payload.get("items", [])
        return [
            Event(event_type="ITEM_ORDER", payload={"item": item})
            for item in items
        ]
```

### Graceful Shutdown

```python
async def run_with_shutdown():
    spine = Spine(organs=[...], backend=backend)
    
    # Start processing in background
    task = asyncio.create_task(spine.run(start_event))
    
    # Signal shutdown after some condition
    await asyncio.sleep(10)
    spine.stop()
    
    await task
```

## Demo Applications

### Séance Demo

A mystical event chain demonstrating the framework's composability:

```
SUMMON_RITUAL → SPIRIT_APPEARED → ANSWER_GENERATED → OMEN_REVEALED
```

```bash
python -m necrostack.apps.seance.main
```

### ETL Pipeline Demo

A practical data processing pipeline:

```
ETL_START → RAW_DATA_LOADED → DATA_CLEANED → DATA_TRANSFORMED
```

```bash
python -m necrostack.apps.etl.main
```

## Project Structure

```
necrostack/
├── core/
│   ├── event.py          # Event model with Pydantic validation
│   ├── organ.py          # Abstract base class for handlers
│   ├── spine.py          # Central dispatcher with failure handling
│   └── logging.py        # Structured JSON logging utilities
├── backends/
│   ├── base.py           # Backend protocol definition
│   ├── inmemory.py       # asyncio.Queue-based backend
│   └── redis_backend.py  # Redis Streams backend
├── apps/
│   ├── seance/           # Mystical demo application
│   └── etl/              # ETL pipeline demo
└── utils/                # Helper utilities
```

## Testing

NecroStack uses pytest with pytest-asyncio for async test support and Hypothesis for property-based testing:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=necrostack

# Run specific test file
pytest tests/test_spine.py

# Run with Hypothesis CI profile (more examples)
pytest --hypothesis-profile=ci
```

## Roadmap

### Phase 2 (Completed ✓)
- [x] Consumer group support for RedisBackend (`XREADGROUP`/`XACK`)
- [x] Dead-letter queue integration
- [x] Pending message recovery (`XPENDING`/`XCLAIM`)

### Phase 3 (Planned — v1.1, Q2 2025)
Focuses on production observability and extensibility.

- [ ] Metrics export (Prometheus/OpenTelemetry) — enables production monitoring dashboards
- [ ] Distributed tracing integration — required for microservice debugging
- [ ] Configurable retry/backoff per event type — allows fine-grained failure handling
- [ ] Event schema registry — enables schema evolution and validation
- [ ] Middleware support — prerequisite for decorator syntax; enables cross-cutting concerns
- [ ] Decorator syntax for Organs — depends on middleware support; improves DX

### Phase 4 (Future — v2.0)
Advanced features for complex deployments.

- [ ] Event replay and time-travel debugging — requires schema registry for version compatibility
- [ ] Multi-backend routing — enables hybrid cloud and failover scenarios

## Contributing

Contributions are welcome. Please ensure:
- All tests pass (`pytest`)
- Code is formatted (`black .`)
- Linting passes (`ruff check .`)
- Type hints are complete

## License

MIT License. See [LICENSE](LICENSE) for details.

## References

- Hohpe, G., & Woolf, B. (2003). *Enterprise Integration Patterns*. Addison-Wesley.
- Fowler, M. (2017). "Event-Driven Architecture." martinfowler.com.
- Python asyncio documentation: https://docs.python.org/3/library/asyncio.html
- Pydantic v2 documentation: https://docs.pydantic.dev/
- Redis Streams: https://redis.io/docs/data-types/streams/
