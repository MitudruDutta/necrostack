# Notification Pipeline - NecroStack Example

A production-style multi-channel notification system demonstrating NecroStack's core capabilities.

## Architecture

```
NOTIFICATION_REQUESTED
        │
        ▼
┌───────────────┐
│ ValidateOrgan │──► NOTIFICATION_FAILED (invalid requests)
└───────────────┘
        │ valid
        ▼
NOTIFICATION_VALIDATED
        │
        ▼
┌───────────────┐
│  RouterOrgan  │──► Fan-out to channels
└───────────────┘
        │
        ├──► EMAIL_SEND_REQUESTED ──► EmailOrgan (async) ──► EMAIL_DELIVERED
        ├──► SMS_SEND_REQUESTED ────► SmsOrgan (sync) ────► SMS_DELIVERED
        └──► PUSH_SEND_REQUESTED ──► PushOrgan (async) ──► PUSH_DELIVERED
                                                                │
                                                                ▼
                                                    ┌─────────────────┐
                                                    │   AuditOrgan    │
                                                    └─────────────────┘
                                                                │
                                                                ▼
                                                    DELIVERY_COMPLETED
```

## Features Demonstrated

| Feature | Implementation |
|---------|----------------|
| Event immutability | All events are Pydantic frozen models |
| Sync handlers | `ValidateOrgan`, `RouterOrgan`, `SmsOrgan`, `AuditOrgan` |
| Async handlers | `EmailOrgan`, `PushOrgan` |
| Multi-event emission | `RouterOrgan` emits 1-3 events per notification |
| Validation | `ValidateOrgan` checks all required fields |
| Retry logic | `EmailOrgan` has 30% failure rate, Spine retries |
| DLQ | `SmsOrgan` permanent failures go to `InMemoryFailedEventStore` |
| Structured logging | JSON logs with event_id, event_type, organ |

## Organs

### ValidateOrgan (sync)
- Validates user_id, channels, message, priority
- Emits `NOTIFICATION_VALIDATED` or `NOTIFICATION_FAILED`

### RouterOrgan (sync)
- Looks up user contact info
- Emits channel-specific events based on requested channels

### EmailOrgan (async)
- Simulates SMTP delivery with 30% transient failure rate
- Demonstrates Spine's retry mechanism

### SmsOrgan (sync)
- Simulates SMS gateway
- Blocked numbers cause permanent failures → DLQ

### PushOrgan (async)
- Simulates FCM/APNs push delivery
- Always succeeds (demonstrates reliable async handler)

### AuditOrgan (sync)
- Listens to all `*_DELIVERED` events
- Records audit trail

## Running

```bash
cd examples/notification_pipeline

# Demo with sample notifications
python main.py

# Load from JSON file
python main.py --file sample_notifications.json

# Load from CSV file  
python main.py --file sample_notifications.csv

# Interactive mode
python main.py --interactive

# Stress test
python main.py --stress --count 200
```

## Interactive Mode

```
> user_001 email,sms 'Your order shipped!' high
  ✓ Queued: user_001 → ['email', 'sms']
> user_002 push 'New message' normal
  ✓ Queued: user_002 → ['push']
> send
  (processes all queued notifications)
> quit
```

## File Formats

**JSON** (`sample_notifications.json`):
```json
{
  "notifications": [
    {"user_id": "user_001", "channels": ["email", "sms"], "message": "Hello!", "priority": "high"}
  ]
}
```

**CSV** (`sample_notifications.csv`):
```csv
user_id,channels,message,priority
user_001,email|sms,Hello!,high
```

## Expected Output

```
======================================================================
NECROSTACK NOTIFICATION PIPELINE DEMO
======================================================================

Processing 5 notification requests...

--- Notification 1 ---
User: user_001
Channels: ['email', 'sms', 'push']
Message: Your order #12345 has shipped!...

Events processed: 7
Events emitted: 6

--- Notification 2 ---
...

======================================================================
DEAD LETTER QUEUE (Failed Events)
======================================================================
  Event: SMS_SEND_REQUESTED
  ID: ...
  Error: SMS delivery permanently failed: +1555000000 is blocked

======================================================================
AUDIT LOG (Successful Deliveries)
======================================================================
  User: user_003
  Channel: push
  Delivered: 2024-...

======================================================================
PIPELINE COMPLETE
======================================================================
```

## Configuration

The Spine is configured with:

```python
Spine(
    organs=[...],
    backend=InMemoryBackend(),
    max_steps=500,
    enqueue_failure_mode=EnqueueFailureMode.STORE,
    failed_event_store=InMemoryFailedEventStore(),
    retry_attempts=3,
    retry_base_delay=0.05,
)
```

- `max_steps=500`: Prevents infinite loops
- `EnqueueFailureMode.STORE`: Failed enqueues go to DLQ instead of crashing
- `retry_attempts=3`: Transient failures get 3 retry attempts
- `retry_base_delay=0.05`: Exponential backoff starting at 50ms
