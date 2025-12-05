# Frequently Asked Questions (FAQ)

## General Questions

### What is NecroStack?

NecroStack is a lightweight, async-first event-driven micro-framework for Python. It helps you build reactive systems using event-driven architecture patterns without the complexity of traditional message brokers like Kafka or RabbitMQ.

### Why the name "NecroStack"?

The name combines "necro" (relating to death/revival) with "stack" (technology stack). It's a playful reference to bringing systems to life through events, with Organs (handlers) and a Spine (dispatcher) forming the framework's "anatomy."

### Who should use NecroStack?

NecroStack is ideal for:
- **Startups** that need to move fast without infrastructure overhead
- **Python developers** building event-driven systems
- **Teams** wanting to start simple and scale later
- **Projects** that need workflow orchestration, notifications, or data pipelines
- **Anyone** who finds Kafka/RabbitMQ overkill for their use case

### Is NecroStack production-ready?

Yes, with some caveats:
- ✅ Core abstractions are stable and well-tested
- ✅ Redis backend provides production-grade features (DLQ, retry, horizontal scaling)
- ✅ We use it in production ourselves
- ⚠️ Version 0.x means the API may change based on feedback
- ⚠️ Do your own evaluation for your specific use case

For production use, we recommend:
- Using the Redis backend for durability
- Comprehensive testing of your handlers
- Monitoring and logging integration
- Starting with a non-critical workload

---

## Technical Questions

### How does NecroStack compare to Celery?

**Key Differences:**

| Aspect | NecroStack | Celery |
|--------|-----------|--------|
| Paradigm | Event-driven | Task-oriented |
| Coupling | Loose (events only) | Tight (direct task calls) |
| Setup | Zero infrastructure | Requires broker |
| Learning Curve | Minimal (3 concepts) | Moderate |
| Async Support | Native async/await | Partial |
| Type Safety | Built-in (Pydantic) | Manual |

**When to use NecroStack:**
- Event-driven workflows
- Loose coupling between components
- Want to start with zero infrastructure

**When to use Celery:**
- Already invested in Celery
- Need advanced scheduling (cron, eta)
- Task-oriented mindset works for you

### How does NecroStack compare to Kafka?

**Key Differences:**

| Aspect | NecroStack | Kafka |
|--------|-----------|-------|
| Throughput | 5-10k events/sec | 100k+ messages/sec |
| Latency | <10ms | <5ms (optimized) |
| Setup | `pip install` | Zookeeper + Kafka cluster |
| Ops Complexity | Low | High |
| Persistence | Optional (Redis) | Always persistent |
| Scale | Horizontal (Redis) | Distributed by design |

**When to use NecroStack:**
- You don't need massive throughput
- You want simple operations
- Developer productivity matters
- You're prototyping or in early stages

**When to use Kafka:**
- You need 100k+ messages/sec
- You have complex stream processing
- You need message replay
- You have DevOps resources

### Can I use both sync and async handlers?

Yes! NecroStack supports both:

```python
class SyncHandler(Organ):
    listens_to = ["EVENT_A"]
    def handle(self, event: Event):  # Regular function
        return Event("EVENT_B", {...})

class AsyncHandler(Organ):
    listens_to = ["EVENT_B"]
    async def handle(self, event: Event):  # Async function
        await some_io_operation()
        return Event("EVENT_C", {...})
```

The Spine automatically detects and handles both types correctly.

### What about exactly-once delivery?

NecroStack with Redis provides **at-least-once delivery**. Exactly-once is extremely difficult to implement correctly and often not necessary.

**Best Practice:** Design your handlers to be **idempotent**—safe to execute multiple times with the same event. Use the event ID for deduplication:

```python
class IdempotentHandler(Organ):
    def __init__(self):
        self.processed_ids = set()
    
    def handle(self, event: Event):
        if event.id in self.processed_ids:
            return None  # Already processed
        
        # Process event
        self.processed_ids.add(event.id)
        return result_event
```

### How do I handle schema evolution?

**Best Practice:** Version your event types instead of changing them.

```python
# Old version
Event("ORDER_PLACED", {"order_id": "123", "amount": 99.99})

# New version (add fields)
Event("ORDER_PLACED_V2", {
    "order_id": "123", 
    "amount": 99.99,
    "currency": "USD",  # New field
    "tax": 8.50          # New field
})

# Handlers can support both during migration
class OrderHandler(Organ):
    listens_to = ["ORDER_PLACED", "ORDER_PLACED_V2"]
    
    def handle(self, event: Event):
        if event.event_type == "ORDER_PLACED":
            # Handle old version
            pass
        else:
            # Handle new version
            pass
```

### How do I test my Organs?

Organs are easy to test because they're just Python classes:

```python
def test_my_organ():
    organ = MyOrgan()
    input_event = Event("INPUT_TYPE", {"data": "test"})
    
    result = organ.handle(input_event)
    
    assert result.event_type == "OUTPUT_TYPE"
    assert result.payload["processed"] == True
```

For integration tests, use `InMemoryBackend`:

```python
async def test_pipeline():
    backend = InMemoryBackend()
    spine = Spine(organs=[Organ1(), Organ2()], backend=backend)
    
    await spine.run(Event("START", {}))
    
    # Assert on final state
```

We also recommend property-based testing with Hypothesis.

### What's the performance like?

**Benchmarks** (on 4-core, 8GB RAM):

| Backend | Throughput | Latency (p50) | Latency (p99) |
|---------|------------|---------------|---------------|
| InMemory | 10,000+ events/sec | <1ms | <5ms |
| Redis | 5,000+ events/sec | ~2ms | ~10ms |

**Factors affecting performance:**
- Handler complexity
- I/O operations
- Event payload size
- Number of Organs
- Redis network latency (if using Redis)

For most applications, this is more than sufficient. If you need more, scale horizontally with consumer groups.

---

## Usage Questions

### How do I start with NecroStack?

1. **Install:**
   ```bash
   pip install necrostack
   ```

2. **Create your first Organ:**
   ```python
   from necrostack.core import Event, Organ
   
   class MyOrgan(Organ):
       listens_to = ["MY_EVENT"]
       
       def handle(self, event: Event):
           print(f"Received: {event.payload}")
           return Event("DONE", {})
   ```

3. **Wire it up and run:**
   ```python
   from necrostack.core import Spine
   from necrostack.backends import InMemoryBackend
   
   spine = Spine(organs=[MyOrgan()], backend=InMemoryBackend())
   await spine.run(Event("MY_EVENT", {"hello": "world"}))
   ```

4. **Explore examples:**
   ```bash
   git clone https://github.com/MitudruDutta/necrostack
   cd necrostack/examples/notification_pipeline
   python main.py
   ```

### How do I handle errors?

NecroStack has built-in error handling:

**1. Configure failure modes:**
```python
from necrostack.core.spine import EnqueueFailureMode, HandlerFailureMode

spine = Spine(
    organs=[...],
    backend=backend,
    enqueue_failure_mode=EnqueueFailureMode.STORE,  # Failed enqueues → DLQ
    handler_failure_mode=HandlerFailureMode.LOG,     # Log errors and continue
    retry_attempts=3,                                # Retry 3 times
    retry_base_delay=0.1,                            # Exponential backoff
)
```

**2. Access the dead-letter queue:**
```python
# Failed events are in the DLQ
failed = spine.failed_event_store.get_all()
for event, error in failed:
    print(f"Event {event.id} failed: {error}")
```

### Can I use NecroStack with FastAPI/Django/Flask?

Absolutely! NecroStack is framework-agnostic.

**Example with FastAPI:**
```python
from fastapi import FastAPI
from necrostack.core import Event, Spine
from necrostack.backends import RedisBackend

app = FastAPI()
backend = RedisBackend(redis_url="redis://localhost")
spine = Spine(organs=[...], backend=backend)

@app.post("/orders")
async def create_order(order: Order):
    # Enqueue event for async processing
    await backend.enqueue(Event("ORDER_PLACED", order.dict()))
    return {"status": "queued"}

@app.on_event("startup")
async def start_processor():
    # Run spine in background
    asyncio.create_task(spine.run_forever())
```

### How do I deploy NecroStack to production?

**Option 1: Single Process (simple)**
```python
# main.py
import asyncio
from necrostack.core import Spine
from necrostack.backends import RedisBackend

async def main():
    backend = RedisBackend(redis_url="redis://production:6379")
    spine = Spine(organs=[...], backend=backend)
    await spine.run_forever()

if __name__ == "__main__":
    asyncio.run(main())
```

**Option 2: Multiple Processes (scale)**
```bash
# Each process joins the same consumer group
# Worker 1
python worker.py --consumer-name worker-1

# Worker 2
python worker.py --consumer-name worker-2

# Events are load-balanced across workers
```

**Option 3: Docker/Kubernetes**
```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install necrostack[redis]
CMD ["python", "worker.py"]
```

### How do I monitor NecroStack in production?

**1. Structured Logs:**
NecroStack outputs JSON logs. Send them to your log aggregator:

```python
import logging
import sys

# Configure logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(message)s'  # Just the JSON
)

# Logs go to stdout, pipe to Datadog/Splunk/ELK
```

**2. Metrics (Redis backend):**
```python
metrics = backend.metrics
print(f"Enqueued: {metrics.events_enqueued}")
print(f"Pulled: {metrics.events_pulled}")
print(f"Acked: {metrics.events_acked}")
print(f"Failed: {metrics.events_failed}")
```

**3. Health Checks:**
```python
health = await backend.health()
if health.healthy:
    print(f"Healthy! Latency: {health.latency_ms}ms")
```

**4. Custom Metrics:**
Add your own monitoring in handlers:

```python
class MonitoredOrgan(Organ):
    def handle(self, event: Event):
        start = time.time()
        result = self.process(event)
        duration = time.time() - start
        
        # Send to your metrics system
        metrics.histogram("organ.duration", duration)
        
        return result
```

---

## Advanced Questions

### Can I implement the Saga pattern?

Yes! The Saga pattern works well with NecroStack:

```python
# Forward flow
ORDER_PLACED → PAYMENT_PROCESSED → INVENTORY_RESERVED → ORDER_CONFIRMED

# Compensation flow (if any step fails)
PAYMENT_FAILED → REFUND_PAYMENT
INVENTORY_FAILED → RELEASE_INVENTORY → REFUND_PAYMENT
```

Each step is an Organ, and failures emit compensation events.

### Can I implement CQRS with NecroStack?

Yes! CQRS (Command Query Responsibility Segregation) is a natural fit:

```python
# Commands (write model)
class CreateOrder(Organ):
    listens_to = ["CREATE_ORDER_COMMAND"]
    def handle(self, event: Event):
        # Validate and store order
        return Event("ORDER_CREATED", {...})

# Events update read models
class UpdateOrderView(Organ):
    listens_to = ["ORDER_CREATED", "ORDER_UPDATED"]
    def handle(self, event: Event):
        # Update denormalized view
        update_read_database(event.payload)
```

### How do I implement circuit breakers?

Wrap external calls with a circuit breaker:

```python
from circuitbreaker import circuit

class ExternalAPIOrgan(Organ):
    @circuit(failure_threshold=5, recovery_timeout=60)
    async def call_external_api(self, data):
        async with httpx.AsyncClient() as client:
            return await client.post("https://api.example.com", json=data)
    
    async def handle(self, event: Event):
        try:
            result = await self.call_external_api(event.payload)
            return Event("API_SUCCESS", result)
        except CircuitBreakerError:
            return Event("API_UNAVAILABLE", {"retry_later": True})
```

### Can I use NecroStack for event sourcing?

Yes! Store all events as the source of truth:

```python
class EventSourcedAggregate(Organ):
    def __init__(self):
        self.event_store = []  # In practice, use a real database
    
    def handle(self, event: Event):
        # Store the event
        self.event_store.append(event)
        
        # Rebuild state from events
        state = self.replay_events(self.event_store)
        
        # Make decision based on state
        if state.can_process(event):
            return Event("PROCESSED", {...})
```

### How do I handle distributed tracing?

Currently, you need to implement this manually. OpenTelemetry integration is on the roadmap.

**Manual approach:**

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class TracedOrgan(Organ):
    def handle(self, event: Event):
        with tracer.start_as_current_span("organ.handle") as span:
            span.set_attribute("event.type", event.event_type)
            span.set_attribute("event.id", event.id)
            
            result = self.process(event)
            return result
```

---

## Troubleshooting

### My handlers aren't being called

**Check:**
1. Event type matches `listens_to` exactly (case-sensitive)
2. Organ is registered with Spine
3. Event is being enqueued
4. No exceptions in logs

**Debug:**
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Events are being processed multiple times

This is expected with Redis backend (at-least-once delivery). Make your handlers idempotent.

### Performance is slow

**Check:**
1. Are handlers doing blocking I/O? (Use async)
2. Is Redis on same network? (Check latency)
3. Too many Organs? (Optimize subscriptions)
4. Large payloads? (Keep events small)

**Profile:**
```python
import cProfile
cProfile.run('asyncio.run(spine.run(event))')
```

### Redis connection keeps failing

**Check:**
1. Redis is running: `redis-cli ping`
2. Connection URL is correct
3. Network connectivity
4. Redis max connections not exceeded

The Redis backend auto-reconnects, so transient failures are okay.

---

## Community & Support

### Where can I get help?

- **GitHub Issues**: Report bugs or ask questions
- **GitHub Discussions**: Share use cases and patterns
- **Documentation**: Read README.md and examples
- **Stack Overflow**: Tag with `necrostack` (we monitor it)

### How can I contribute?

We welcome contributions! Here's how:

1. **Star the repo** ⭐ to show support
2. **Open issues** for bugs or feature requests
3. **Submit PRs** for fixes or enhancements
4. **Share your use cases** in Discussions
5. **Improve docs** (typos, clarity, examples)

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### What's on the roadmap?

- PostgreSQL backend (NOTIFY/LISTEN)
- OpenTelemetry integration
- Web UI for monitoring
- gRPC transport
- Saga pattern helpers
- GraphQL subscription support
- Cloud deployment templates
- More examples and tutorials

Vote on features in GitHub Discussions!

### Is there a changelog?

See [CHANGELOG.md](CHANGELOG.md) or GitHub releases for version history.

---

## Philosophy & Design

### Why event-driven architecture?

Event-driven architecture provides:
- **Loose coupling**: Components don't know about each other
- **Scalability**: Easy to add new consumers
- **Resilience**: Failures are isolated
- **Auditability**: Complete event trail
- **Flexibility**: Change behavior without changing code

### What are the trade-offs?

**Pros:**
- ✅ Loose coupling
- ✅ Easy to extend
- ✅ Natural audit trail
- ✅ Fault isolation

**Cons:**
- ❌ More complex than direct calls
- ❌ Eventual consistency (not immediate)
- ❌ Harder to debug (distributed flow)
- ❌ Need to think about failure modes

NecroStack tries to minimize the cons with structured logging, type safety, and built-in error handling.

### Why Python?

Python is ideal for event-driven systems because:
- Native async/await support
- Excellent libraries (Pydantic, Redis, etc.)
- Fast development iteration
- Great for glue code and integration
- Strong ecosystem

For ultra-high performance (100k+ events/sec), consider Kafka or Go. But for most use cases, Python + NecroStack is perfect.

---

**Still have questions?** Open an issue on GitHub!
