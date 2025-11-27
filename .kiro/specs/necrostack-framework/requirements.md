# Requirements Document — NecroStack

## Introduction

NecroStack is a minimal, async-first event-driven micro-framework for Python 3.11+. It provides three core abstractions: **Event** (a typed, immutable message), **Organ** (a pluggable event handler), and **Spine** (a queue-driven dispatcher). The framework supports two backends (in-memory and Redis Streams), uses Pydantic for validation, and prioritizes simplicity and production-minded clarity.

## Glossary

- **Event**: A Pydantic-validated, immutable message object containing `id`, `timestamp`, `event_type`, and `payload`.
- **Organ**: A pluggable component that handles events and may emit new events.
- **Spine**: The central dispatcher that pulls events from a backend, routes them to Organs, and enqueues any returned events.
- **Backend**: A queue abstraction implementing async `enqueue`, `pull`, and `ack`.
- **Handler**: The Organ’s `handle(event)` method.
- **Event Type**: A string identifier (UPPER_SNAKE_CASE) used for routing.

---

# Requirement 1: Event Model

**User Story:** As a developer, I want validated, immutable events with strong typing.

### Acceptance Criteria

1. Events SHALL be instances of a Pydantic BaseModel.
2. Events SHALL generate a UUID automatically if no id is provided.
3. Events SHALL set the current UTC timestamp automatically.
4. Events SHALL require a non-empty `event_type: str`.
5. Events SHALL forbid unknown fields (`extra="forbid"`).
6. Events SHALL support JSON serialization via `model_dump()`.
7. Deserialization SHALL reconstruct a valid Event instance.

---

# Requirement 2: Organ Base Class

**User Story:** As a developer, I want modular event handlers with a predictable interface.

### Acceptance Criteria

1. Organ SHALL inherit from `ABC`.
2. Organ SHALL define a class attribute `listens_to: list[str]`.
3. `Spine` SHALL validate that `listens_to` contains only strings during registration.
4. Organ SHALL automatically use its class name as its `name` attribute.
5. Organ subclasses SHALL implement `handle(self, event)`.
6. `handle()` SHALL accept exactly one `Event` argument.
7. `handle()` SHALL return:  
   - an `Event`,  
   - a sequence of `Event`s,  
   - `None`,  
   - or an awaitable resolving to the same.

---

# Requirement 3: Spine Dispatcher

**User Story:** As a developer, I want a dispatcher that reliably routes events to the correct organs.

### Acceptance Criteria

1. Spine SHALL accept a list of Organ instances, a Backend, and `max_steps` (default 10,000).
2. Spine.run() SHALL repeatedly call `backend.pull()` to fetch events.
3. Spine SHALL dispatch events to all Organs whose `listens_to` contains `event.event_type`.
4. Async handlers SHALL be awaited; sync handlers SHALL be called directly.
5. If a handler returns an Event or list of Events, Spine SHALL enqueue them via `backend.enqueue`.
6. Spine SHALL invoke Organs in the order provided to its constructor.
7. If processing exceeds `max_steps`, Spine SHALL raise `RuntimeError("Max steps exceeded")`.
8. If `backend.pull()` returns `None` (timeout), Spine SHALL continue.
9. Spine SHALL use structured logging (JSON logs) for dispatching and handler results.

---

# Requirement 4: Backend Protocol

**User Story:** As a developer, I want pluggable backends.

### Acceptance Criteria

1. Backend SHALL define async methods: `enqueue(Event)`, `pull(timeout)`, `ack(Event)`.
2. `enqueue()` SHALL store the event.
3. `pull()` SHALL return the next event or `None` on timeout.
4. `ack()` MAY be a no-op in non-durable backends.

---

# Requirement 5: InMemoryBackend

**User Story:** I want a simple backend for development.

### Acceptance Criteria

1. InMemoryBackend SHALL use `asyncio.Queue` internally.
2. `enqueue()` SHALL put the event in FIFO order.
3. `pull(timeout)` SHALL block until an event is available or timeout.
4. On timeout, `pull()` SHALL return `None`.
5. `ack()` SHALL be a no-op.

---

# Requirement 6: RedisBackend (MVP + Phase 2)

**User Story:** I want a Redis Streams backend for persistence.

### MVP Acceptance Criteria

1. RedisBackend SHALL accept `redis_url` and `stream_key` (default `"necrostack:events"`).
2. `enqueue()` SHALL serialize events using `event.model_dump()` and call `XADD`.
3. `pull()` SHALL use `XREAD` with blocking timeout.
4. `ack()` SHALL be a no-op in MVP.
5. RedisBackend SHALL automatically reconnect if connection drops.

### Phase 2 (Not required for MVP)

1. Add consumer group support (`XREADGROUP`, `XACK`).
2. Add dead-letter queue.
3. Add retry & backoff logic.

---

# Requirement 7: Project Structure

1. Project SHALL use `necrostack/core`, `necrostack/backends`, `necrostack/utils`, `necrostack/apps` (app-specific organs live under `necrostack/apps/{app}/organs/`).
2. Packaging SHALL use `pyproject.toml`.
3. `.gitignore` SHALL exclude Python artifacts.
4. README SHALL describe features, architecture, and quickstart.

---

# Requirement 8: Séance Demo Application

### Acceptance Criteria

1. Demo SHALL include the event chain:

   - `SUMMON_RITUAL` → `SPIRIT_APPEARED`  
   - `SPIRIT_APPEARED` → `ANSWER_GENERATED`  
   - `ANSWER_GENERATED` → `OMEN_REVEALED`  
   - `OMEN_REVEALED` → printed output

2. Each stage SHALL be implemented as an Organ.
3. Demo SHALL run using InMemoryBackend.

---

# Requirement 9: ETL Demo Application

### Acceptance Criteria

1. Demo SHALL include the event chain:

   - `ETL_START` → `RAW_DATA_LOADED`  
   - `RAW_DATA_LOADED` → `DATA_CLEANED`  
   - `DATA_CLEANED` → `DATA_TRANSFORMED`  
   - `DATA_TRANSFORMED` → printed summary

---

# Requirement 10: Test Suite

### Acceptance Criteria

1. Tests SHALL use pytest.
2. Event tests SHALL cover validation, default fields, serialization.
3. Spine tests SHALL cover routing, sync/async handling, max_steps.
4. InMemoryBackend tests SHALL cover FIFO behavior.
5. End-to-end tests SHALL verify full Organ chains for Séance & ETL demos.
