1. Introduction

NecroStack is a minimal, async-first event-driven micro-framework for Python 3.11+.
It provides three core abstractions:

Event — A typed, immutable, validated message object

Organ — A pluggable module that listens to specific event types

Spine — A queue-based dispatcher that routes events to Organs and enqueues resulting events

NecroStack prioritizes simplicity, modularity, and clarity.
It supports two queue backends:

In-memory backend (MVP, dev mode)

Redis Streams backend (MVP-light, Phase 2 for full consumer groups)

The framework uses Pydantic v2 for event validation and is designed to be fully type-safe with excellent developer experience.

2. Glossary

Event — Immutable Pydantic-based message object with ID, type, payload, and timestamp.

Organ — A modular component implementing a handle(event) method and declaring the events it listens to via listens_to.

Spine — Central dispatcher that processes events in FIFO order, calling Organs and enqueuing emitted events.

Backend — A queue implementation for storing, retrieving, and acknowledging events.

Handler — The Organ’s handle(event) method that processes incoming events.

3. Requirements
Requirement 1: Event Definition and Validation

User Story:
As a developer, I want typed, validated events so my application can maintain data integrity throughout processing.

Acceptance Criteria

WHEN a developer defines an Event THEN NecroStack SHALL provide a base Event class extending pydantic.BaseModel.

WHEN an Event is instantiated with invalid data THEN NecroStack SHALL raise a Pydantic validation error with descriptive messages.

WHEN an Event is created with valid data THEN NecroStack SHALL assign:

a unique identifier

a creation timestamp

immutable fields (frozen model)

WHEN an Event is serialized THEN NecroStack SHALL produce a JSON-compatible dict.

WHEN an Event is deserialized THEN NecroStack SHALL reconstruct the original Event with full schema validation.

Requirement 2: Organ Registration and Event Handling

User Story:
As a developer, I want to create modular event handlers so that I can build clean, extensible event-driven workflows.

Acceptance Criteria

WHEN a developer creates an Organ class THEN NecroStack SHALL provide a base Organ class.

WHEN an Organ sets listens_to = ["SOME_EVENT"] THEN NecroStack SHALL automatically register it for those event types.

WHEN the Spine routes an event THEN NecroStack SHALL invoke the Organ’s handle(self, event) method.

WHEN an Organ handler is asynchronous THEN NecroStack SHALL await its execution.

WHEN an Organ handler is synchronous THEN NecroStack SHALL call it directly.

WHEN a handler returns an Event or a sequence of Events THEN NecroStack SHALL enqueue them.

WHEN a handler returns None THEN NecroStack SHALL treat it as a terminal step with no further action.

Important:
There SHALL NOT be decorator-based registration of handlers.
NecroStack uses only the listens_to list + single handle() method.

Requirement 3: Spine Dispatcher Operations

User Story:
As a developer, I want a reliable dispatcher that routes events to handlers efficiently and safely.

Acceptance Criteria

WHEN the Spine is initialized THEN it SHALL accept:

a list of Organs

a backend instance

optional configuration (e.g., max_steps)

WHEN the Spine starts THEN it SHALL continuously pull events from the backend.

WHEN an event is received THEN the Spine SHALL:

find all Organs whose listens_to contains the event type

invoke their handlers

WHEN multiple Organs listen to the same event THEN Spine SHALL invoke them in deterministic registration order.

WHEN a handler raises an exception THEN the Spine SHALL:

log the error

continue processing remaining events

WHEN the Spine receives a shutdown request THEN it SHALL:

finish processing in-flight events

gracefully stop pulling new events

Spine SHALL prevent infinite event loops using:

a max-steps guard

optional per-run deduplication of event IDs

Requirement 4: In-Memory Backend (MVP)

User Story:
As a developer, I want a fast, simple queue backend for development and testing.

Acceptance Criteria

WHEN the in-memory backend initializes THEN it SHALL create an async-compatible queue (e.g., asyncio.Queue).

WHEN an event is enqueued THEN it SHALL be stored in FIFO order.

WHEN an event is dequeued THEN the backend SHALL return the oldest event.

WHEN the backend queue is empty THEN pull() SHALL block until an event is available or timeout occurs.

WHEN the backend shuts down THEN it SHALL discard pending events and release resources.

Requirement 5: Redis Streams Backend (MVP-Light + Phase 2)

User Story:
As a developer, I want a durable, distributed backend for production environments.

Acceptance Criteria (MVP-Light, Implementable in Hackathon)

WHEN the Redis backend initializes THEN it SHALL open a connection to Redis.

WHEN an event is enqueued THEN it SHALL serialize the event and call XADD.

WHEN pulling events THEN the backend SHALL use XREAD (simple consumer) with blocking timeout.

WHEN processing is done THEN ack() MAY be a no-op in MVP.

WHEN Redis connection fails THEN backend SHALL attempt transparent reconnection.

Acceptance Criteria (Phase 2, Not Required for Hackathon)

Full consumer group support (XGROUP CREATE, XREADGROUP, XACK)

Pending list recovery

Dead-letter queue support

Exponential backoff retry and connection lifecycle management

Requirement 6: Project Structure and Packaging

User Story:
As a developer, I want clear organization and modern packaging so I can easily install and extend NecroStack.

Acceptance Criteria

WHEN installed THEN NecroStack SHALL be importable as necrostack.

WHEN published THEN NecroStack SHALL include a complete pyproject.toml with:

name, version, authors, license, classifiers

dependencies for core and extras

WHEN a developer installs necrostack[redis] THEN Redis dependencies SHALL also install.

WHEN importing necrostack THEN top-level imports SHALL include:

Event

Organ

Spine

Requirement 7: Type Safety and Developer Experience

User Story:
As a developer, I want a strongly typed framework with great IDE support.

Acceptance Criteria

All public APIs SHALL include precise type hints.

IF an Organ declares incorrect handler signature THEN NecroStack SHALL raise a descriptive error at registration time.

WHEN events flow through the system THEN type information SHALL be preserved throughout processing.

Documentation SHALL clearly describe typing expectations.

4. Non-Functional Requirements

Code SHALL follow PEP 8 & type-check cleanly under mypy.

Logging SHALL use structured JSON by default.

Framework SHALL be dependency-light (Pydantic + Redis optional).

Tests SHALL exist for:

Event validation

Organ handler dispatch

Spine loop

In-memory backend

The codebase SHALL run on Python 3.11+.

5. Phase Breakdown (Implementation Strategy)

To support hackathon execution:

MVP Phase:

Event model

Organ

Spine

In-memory backend

Basic Redis XADD/XREAD backend

Phase 2 (Post-hackathon):

Full Redis Streams consumer groups

Dead-letter queues

Backoff policies

Event replay

Phase 3:

Optional workflow DSL

Optional OpenTelemetry integration

Optional web studio