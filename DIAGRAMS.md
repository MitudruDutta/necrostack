# NecroStack Architecture Diagrams

> Visual representations for presentations and documentation

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        NecroStack System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐              │
│  │  Event   │─────▶│  Spine   │─────▶│  Organ   │              │
│  │ (Input)  │      │(Dispatch)│      │(Handler) │              │
│  └──────────┘      └─────┬────┘      └────┬─────┘              │
│                          │                 │                    │
│                          │                 ├──▶ Event (Output)  │
│                          ▼                 │                    │
│                    ┌──────────┐            │                    │
│                    │ Backend  │◀───────────┘                    │
│                    │(Storage) │                                 │
│                    └──────────┘                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### Event Structure

```
┌────────────────────────────────┐
│          Event                 │
├────────────────────────────────┤
│ • id: UUID (auto-generated)    │
│ • timestamp: DateTime (auto)   │
│ • event_type: str (required)   │
│ • payload: dict[str, Any]      │
│                                │
│ Properties:                    │
│ ✓ Immutable (frozen)           │
│ ✓ Type-safe (Pydantic)         │
│ ✓ JSON-serializable            │
└────────────────────────────────┘
```

### Organ Lifecycle

```
Event Received
      ↓
┌─────────────┐
│ Pre-Check   │ ← Is event type in listens_to?
└──────┬──────┘
       │ Yes
       ↓
┌─────────────┐
│   Handle    │ ← Execute handler (sync or async)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Emit      │ ← Return Event | list[Event] | None
└──────┬──────┘
       │
       ↓
  Enqueue to Backend
```

### Spine Processing Loop

```
    ┌────────────────┐
    │  Pull Event    │◀──────────┐
    │  from Backend  │           │
    └────────┬───────┘           │
             │                   │
             ↓                   │
    ┌────────────────┐           │
    │ Find Matching  │           │
    │    Organs      │           │
    └────────┬───────┘           │
             │                   │
             ↓                   │
    ┌────────────────┐           │
    │   Execute      │           │
    │   Handlers     │           │
    └────────┬───────┘           │
             │                   │
             ↓                   │
    ┌────────────────┐           │
    │ Enqueue New    │           │
    │    Events      │           │
    └────────┬───────┘           │
             │                   │
             ↓                   │
    ┌────────────────┐           │
    │  Ack Original  │           │
    │     Event      │           │
    └────────┬───────┘           │
             │                   │
             ↓                   │
         Max Steps?──────No──────┘
             │ Yes
             ↓
        Terminate
```

## Backend Architecture

### In-Memory Backend

```
┌──────────────────────────────┐
│     InMemoryBackend          │
├──────────────────────────────┤
│                              │
│  ┌────────────────────────┐  │
│  │  asyncio.Queue         │  │
│  │  (FIFO)                │  │
│  │                        │  │
│  │  ┌──────┐  ┌──────┐   │  │
│  │  │Event │→ │Event │→  │  │
│  │  └──────┘  └──────┘   │  │
│  └────────────────────────┘  │
│                              │
│  Characteristics:            │
│  • Non-durable               │
│  • Single process            │
│  • Zero dependencies         │
│  • Fast (10k+ events/sec)    │
└──────────────────────────────┘
```

### Redis Backend

```
┌────────────────────────────────────────────────────┐
│              RedisBackend                          │
├────────────────────────────────────────────────────┤
│                                                    │
│  ┌──────────────────────────────────────────┐     │
│  │         Redis Streams                    │     │
│  │                                          │     │
│  │  Main Stream         Dead-Letter Queue  │     │
│  │  ┌────────┐          ┌────────┐         │     │
│  │  │ Event  │          │ Failed │         │     │
│  │  │ Event  │          │ Event  │         │     │
│  │  │ Event  │          └────────┘         │     │
│  │  └────────┘                             │     │
│  │       ↓                                  │     │
│  │  Consumer Group                          │     │
│  │  ┌────────────────┐                      │     │
│  │  │ Consumer 1     │                      │     │
│  │  │ Consumer 2     │                      │     │
│  │  │ Consumer N     │                      │     │
│  │  └────────────────┘                      │     │
│  └──────────────────────────────────────────┘     │
│                                                    │
│  Features:                                         │
│  • Durable                                         │
│  • Multi-process/node                              │
│  • At-least-once delivery                          │
│  • Auto-retry & DLQ                                │
│  • Connection pooling                              │
└────────────────────────────────────────────────────┘
```

## Failure Handling

### Enqueue Failure Modes

```
Event → Enqueue Failed
         │
         ├── FAIL Mode
         │   └── Raise Exception
         │       └── Stop Processing
         │
         ├── RETRY Mode
         │   └── Exponential Backoff
         │       ├── Success → Continue
         │       └── Failure → Raise Exception
         │
         └── STORE Mode
             └── Write to DLQ
                 └── Continue Processing
```

### Handler Failure Modes

```
Handler Throws Exception
         │
         ├── LOG Mode
         │   ├── Log Error
         │   ├── Ack Event
         │   └── Continue
         │
         ├── STORE Mode
         │   ├── Write to DLQ
         │   ├── Ack Event
         │   └── Continue
         │
         └── NACK Mode
             ├── Don't Ack
             └── Backend Retries
```

## Example: Notification Pipeline

```
                    NOTIFICATION_REQUESTED
                            │
                            ▼
                    ┌───────────────┐
                    │ ValidateOrgan │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
     NOTIFICATION_VALIDATED    NOTIFICATION_FAILED
              │                      (to DLQ)
              ▼
      ┌───────────────┐
      │  RouterOrgan  │
      └───────┬───────┘
              │
      ┌───────┴────────┬────────────────┬────────────┐
      │                │                │            │
      ▼                ▼                ▼            │
EMAIL_SEND_REQ   SMS_SEND_REQ   PUSH_SEND_REQ       │
      │                │                │            │
      ▼                ▼                ▼            │
┌──────────┐    ┌──────────┐    ┌──────────┐        │
│EmailOrgan│    │ SmsOrgan │    │PushOrgan │        │
│ (async)  │    │  (sync)  │    │ (async)  │        │
└────┬─────┘    └────┬─────┘    └────┬─────┘        │
     │               │               │               │
     ▼               ▼               ▼               │
EMAIL_DELIVERED  SMS_DELIVERED  PUSH_DELIVERED       │
     │               │               │               │
     └───────────────┴───────────────┴───────────────┘
                     │
                     ▼
              ┌──────────────┐
              │  AuditOrgan  │
              └──────┬───────┘
                     │
                     ▼
             DELIVERY_COMPLETED
```

## Example: Trading Order Book

```
                    ORDER_SUBMITTED
                            │
                            ▼
                    ┌───────────────┐
                    │ ValidateOrder │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
      ORDER_VALIDATED              ORDER_REJECTED
              │
              ▼
      ┌────────────────┐
      │ MatchingEngine │
      └────────┬───────┘
               │
    ┌──────────┼──────────┬─────────────┐
    │          │          │             │
    ▼          ▼          ▼             ▼
ORDER_    ORDER_     ORDER_      TRADE_EXECUTED
FILLED   PARTIAL    QUEUED            │
                                      ▼
                              ┌────────────────┐
                              │ SettlementOrgan│
                              │    (async)     │
                              └────────┬───────┘
                                       │
                          ┌────────────┴────────────┐
                          │                         │
                          ▼                         ▼
                  SETTLEMENT_COMPLETE    SETTLEMENT_FAILED
                          │                    (to DLQ)
                          ▼
                  ┌───────────────┐
                  │  RiskManager  │
                  └───────┬───────┘
                          │
                     ┌────┴────┐
                     │         │
                     ▼         ▼
              RISK_ALERT    (normal)
                               │
                               ▼
                       ┌──────────────┐
                       │  AuditTrail  │
                       └──────────────┘
```

## Scaling Strategy

### Development Phase
```
┌──────────────────────────┐
│   Single Process         │
│                          │
│   ┌─────────────────┐    │
│   │ InMemoryBackend │    │
│   │                 │    │
│   │  All Organs     │    │
│   └─────────────────┘    │
│                          │
│  Fast iteration          │
│  Simple debugging        │
└──────────────────────────┘
```

### Production Phase
```
┌────────────────────────────────────────────┐
│         Multi-Process/Node                 │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │         Redis (Central)              │  │
│  └────────┬─────────────────────┬───────┘  │
│           │                     │          │
│  ┌────────▼────────┐   ┌────────▼────────┐ │
│  │   Process 1     │   │   Process 2     │ │
│  │                 │   │                 │ │
│  │  Consumer Group │   │  Consumer Group │ │
│  │  "workers"      │   │  "workers"      │ │
│  │                 │   │                 │ │
│  │  Organs A, B    │   │  Organs C, D    │ │
│  └─────────────────┘   └─────────────────┘ │
│                                            │
│  Horizontal scaling                        │
│  Load balancing                            │
│  High availability                         │
└────────────────────────────────────────────┘
```

## Observability Flow

```
Event Received
      │
      ▼
┌─────────────────┐
│ Log: Received   │ ← event_id, event_type, timestamp
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Log: Dispatched │ ← event_id, organ name
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Log: Completed  │ ← event_id, emitted events, duration
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Log: Enqueued   │ ← new event_ids
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Log: Acked      │ ← original event_id
└─────────────────┘

All logs are:
• Structured JSON
• Correlated by event_id
• Timestamped (UTC)
• Leveled (DEBUG/INFO/ERROR)
```

## Event-Driven Patterns Supported

### 1. Event Notification
```
Service A → Event → Service B (notified)
```

### 2. Event-Carried State Transfer
```
Service A → Event (with full data) → Service B (no query needed)
```

### 3. Event Sourcing
```
Commands → Events → Event Store → State Reconstruction
```

### 4. CQRS
```
Write Model → Events → Read Model (projection)
```

### 5. Saga Pattern
```
Step1 → Event → Step2 → Event → Step3
  ↓                                 ↓
Compensate ←── Event ←── Failed ────┘
```

---

## Using These Diagrams

### In Presentations
- Copy the ASCII diagrams into slides as monospace text
- Use them in Markdown-based presentation tools (e.g., Marp, reveal.js)
- Convert to visual diagrams using tools like Mermaid or PlantUML

### In Documentation
- Include directly in Markdown files
- Reference in code comments
- Use in architecture decision records (ADRs)

### For Teaching
- Walk through each box step-by-step
- Trace event flow with a pointer
- Show examples alongside diagrams
