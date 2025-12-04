"""Tests for RedisBackend.

These tests require a running Redis instance. Start one with:
    docker-compose up -d

Tests will be skipped if Redis is not available.
"""

import asyncio

import pytest

from necrostack.backends.redis_backend import RedisBackend
from necrostack.core.event import Event


def redis_available() -> bool:
    """Check if Redis is available at localhost:6379."""
    try:
        import redis

        client = redis.Redis(host="localhost", port=6379)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not redis_available(),
    reason="Redis not available at localhost:6379. Start with: docker-compose up -d",
)

REDIS_URL = "redis://localhost:6379"


@pytest.fixture
async def redis_backend():
    """Create a RedisBackend with unique stream key for test isolation."""
    import uuid

    stream_key = f"necrostack:test:{uuid.uuid4().hex[:8]}"
    dlq_stream = f"{stream_key}:dlq"
    backend = RedisBackend(
        redis_url=REDIS_URL,
        stream_key=stream_key,
        consumer_group=f"test-group-{uuid.uuid4().hex[:8]}",
        consumer_name=f"test-consumer-{uuid.uuid4().hex[:8]}",
        max_retries=3,
        claim_min_idle_ms=100,  # Fast for testing
    )
    yield backend
    # Cleanup
    try:
        await backend.delete_stream(stream_key)
        await backend.delete_stream(dlq_stream)
    except Exception:
        pass
    await backend.close()


# =============================================================================
# Basic Operations
# =============================================================================


@pytest.mark.asyncio
async def test_enqueue_and_pull(redis_backend):
    """Test basic enqueue and pull operations."""
    event = Event(event_type="TEST_EVENT", payload={"key": "value"})

    await redis_backend.enqueue(event)
    pulled = await redis_backend.pull(timeout=2.0)

    assert pulled is not None
    assert pulled.id == event.id
    assert pulled.event_type == event.event_type
    assert pulled.payload == event.payload


@pytest.mark.asyncio
async def test_fifo_ordering(redis_backend):
    """Test that events are pulled in FIFO order."""
    events = [
        Event(event_type="EVENT_1", payload={"order": 1}),
        Event(event_type="EVENT_2", payload={"order": 2}),
        Event(event_type="EVENT_3", payload={"order": 3}),
    ]

    for event in events:
        await redis_backend.enqueue(event)

    for expected in events:
        pulled = await redis_backend.pull(timeout=2.0)
        assert pulled is not None
        assert pulled.id == expected.id
        await redis_backend.ack(pulled)


@pytest.mark.asyncio
async def test_pull_timeout_on_empty(redis_backend):
    """Test that pull returns None on timeout when stream is empty."""
    result = await redis_backend.pull(timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_event_serialization_round_trip(redis_backend):
    """Test that event data survives serialization through Redis."""
    event = Event(
        event_type="COMPLEX_EVENT",
        payload={
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "nested": {"a": 1, "b": [1, 2, 3]},
            "list": ["x", "y", "z"],
        },
    )

    await redis_backend.enqueue(event)
    pulled = await redis_backend.pull(timeout=2.0)

    assert pulled is not None
    assert pulled.id == event.id
    assert pulled.payload == event.payload
    assert abs((pulled.timestamp - event.timestamp).total_seconds()) < 1


# =============================================================================
# Consumer Groups & Acknowledgment
# =============================================================================


@pytest.mark.asyncio
async def test_ack_removes_from_pending(redis_backend):
    """Test that ack removes message from pending list."""
    event = Event(event_type="TEST_EVENT", payload={"test": "ack"})
    await redis_backend.enqueue(event)

    pulled = await redis_backend.pull(timeout=2.0)
    assert pulled is not None

    await redis_backend.ack(pulled)
    assert redis_backend.metrics.events_acked >= 1


@pytest.mark.asyncio
async def test_unacked_message_stays_pending(redis_backend):
    """Test that unacked messages remain in pending list."""
    from redis.asyncio import Redis

    event = Event(event_type="TEST_EVENT", payload={"test": "pending"})
    await redis_backend.enqueue(event)

    pulled = await redis_backend.pull(timeout=2.0)
    assert pulled is not None
    # Don't ack

    # Check pending list directly with proper cleanup
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        pending = await redis.xpending(redis_backend.stream_key, redis_backend.consumer_group)
        assert pending["pending"] >= 1
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_consumer_group_created_automatically(redis_backend):
    """Test that consumer group is created on first operation."""
    from redis.asyncio import Redis

    event = Event(event_type="TEST_EVENT", payload={})
    await redis_backend.enqueue(event)

    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        groups = await redis.xinfo_groups(redis_backend.stream_key)
        group_names = [g["name"] for g in groups]
        assert redis_backend.consumer_group in group_names
    finally:
        await redis.aclose()


# =============================================================================
# Pending Message Recovery (XCLAIM)
# =============================================================================


@pytest.mark.asyncio
async def test_pending_message_recovery():
    """Test that pending messages are recovered via XCLAIM."""
    import uuid

    stream_key = f"necrostack:test:{uuid.uuid4().hex[:8]}"
    group = f"test-group-{uuid.uuid4().hex[:8]}"

    # Consumer 1 pulls but doesn't ack
    backend1 = RedisBackend(
        redis_url=REDIS_URL,
        stream_key=stream_key,
        consumer_group=group,
        consumer_name="consumer-1",
        claim_min_idle_ms=50,
    )

    event = Event(event_type="RECOVER_TEST", payload={"test": "xclaim"})
    await backend1.enqueue(event)
    pulled1 = await backend1.pull(timeout=2.0)
    assert pulled1 is not None
    # Don't ack - simulate crash

    # Wait for idle time
    await asyncio.sleep(0.1)

    # Consumer 2 should recover the message
    backend2 = RedisBackend(
        redis_url=REDIS_URL,
        stream_key=stream_key,
        consumer_group=group,
        consumer_name="consumer-2",
        claim_min_idle_ms=50,
    )

    pulled2 = await backend2.pull(timeout=2.0)
    assert pulled2 is not None
    assert pulled2.id == event.id
    assert backend2.metrics.pending_recovered >= 1

    await backend2.ack(pulled2)

    # Cleanup
    await backend1.delete_stream(stream_key)
    await backend1.close()
    await backend2.close()


# =============================================================================
# Dead Letter Queue
# =============================================================================


@pytest.mark.asyncio
async def test_nack_moves_to_dlq(redis_backend):
    """Test that nack moves message to DLQ."""
    from redis.asyncio import Redis

    event = Event(event_type="DLQ_TEST", payload={"test": "nack"})
    await redis_backend.enqueue(event)

    pulled = await redis_backend.pull(timeout=2.0)
    assert pulled is not None

    await redis_backend.nack(pulled, reason="Test failure")

    # Check DLQ with proper cleanup
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        dlq_messages = await redis.xrange(redis_backend.dlq_stream)
        assert len(dlq_messages) >= 1
        _, data = dlq_messages[-1]
        assert data["reason"] == "Test failure"
        assert "failed_at" in data
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_poison_message_moved_to_dlq_after_max_retries():
    """Test that messages exceeding max_retries go to DLQ."""
    import uuid

    from redis.asyncio import Redis

    stream_key = f"necrostack:test:{uuid.uuid4().hex[:8]}"
    dlq_stream = f"{stream_key}:dlq"
    group = f"test-group-{uuid.uuid4().hex[:8]}"

    backend = RedisBackend(
        redis_url=REDIS_URL,
        stream_key=stream_key,
        consumer_group=group,
        max_retries=2,
        claim_min_idle_ms=50,
    )

    event = Event(event_type="POISON_TEST", payload={"poison": True})
    await backend.enqueue(event)

    # Pull multiple times without acking to simulate retries
    for i in range(3):
        pulled = await backend.pull(timeout=2.0)
        if pulled:
            # Don't ack - let it become pending
            await asyncio.sleep(0.1)

    # Next pull should trigger DLQ move
    await backend.pull(timeout=0.5)

    # Check DLQ with proper cleanup
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        dlq_messages = await redis.xrange(dlq_stream)
        assert len(dlq_messages) >= 1
    finally:
        await redis.aclose()

    # Cleanup
    await backend.delete_stream(stream_key)
    await backend.delete_stream(dlq_stream)
    await backend.close()


# =============================================================================
# Health & Metrics
# =============================================================================


@pytest.mark.asyncio
async def test_health_check_healthy(redis_backend):
    """Test health check returns healthy status."""
    # Ensure stream exists
    event = Event(event_type="HEALTH_TEST", payload={})
    await redis_backend.enqueue(event)

    health = await redis_backend.health()

    assert health.healthy is True
    assert health.latency_ms > 0
    assert "stream_length" in health.details
    assert health.details["consumer_group"] == redis_backend.consumer_group


@pytest.mark.asyncio
async def test_metrics_tracking(redis_backend):
    """Test that metrics are tracked correctly."""
    event = Event(event_type="METRICS_TEST", payload={})

    await redis_backend.enqueue(event)
    assert redis_backend.metrics.events_enqueued >= 1

    pulled = await redis_backend.pull(timeout=2.0)
    assert pulled is not None
    assert redis_backend.metrics.events_pulled >= 1

    await redis_backend.ack(pulled)
    assert redis_backend.metrics.events_acked >= 1


# =============================================================================
# Reconnection
# =============================================================================


@pytest.mark.asyncio
async def test_reconnection_on_connection_loss(redis_backend):
    """Test that backend reconnects after connection loss."""
    event = Event(event_type="RECONNECT_TEST", payload={})
    await redis_backend.enqueue(event)

    # Force connection reset
    if redis_backend._redis:
        await redis_backend._redis.aclose()
        redis_backend._redis = None

    # Should reconnect automatically
    pulled = await redis_backend.pull(timeout=2.0)
    assert pulled is not None
    assert redis_backend.metrics.reconnections >= 1


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_ack_without_pull_is_noop(redis_backend):
    """Test that ack without prior pull does nothing."""
    event = Event(event_type="TEST", payload={})
    # Should not raise
    await redis_backend.ack(event)


@pytest.mark.asyncio
async def test_multiple_consumers_same_group():
    """Test that multiple consumers in same group share work."""
    import uuid

    stream_key = f"necrostack:test:{uuid.uuid4().hex[:8]}"
    group = f"test-group-{uuid.uuid4().hex[:8]}"

    backend1 = RedisBackend(
        redis_url=REDIS_URL,
        stream_key=stream_key,
        consumer_group=group,
        consumer_name="consumer-1",
    )
    backend2 = RedisBackend(
        redis_url=REDIS_URL,
        stream_key=stream_key,
        consumer_group=group,
        consumer_name="consumer-2",
    )

    # Enqueue 4 events
    for i in range(4):
        await backend1.enqueue(Event(event_type=f"EVENT_{i}", payload={"i": i}))

    # Both consumers pull
    pulled1 = await backend1.pull(timeout=1.0)
    pulled2 = await backend2.pull(timeout=1.0)

    assert pulled1 is not None
    assert pulled2 is not None
    assert pulled1.id != pulled2.id  # Different events

    await backend1.ack(pulled1)
    await backend2.ack(pulled2)

    # Cleanup
    await backend1.delete_stream(stream_key)
    await backend1.close()
    await backend2.close()


@pytest.mark.asyncio
async def test_close_clears_connection(redis_backend):
    """Test that close() clears the internal connection."""
    event = Event(event_type="CLOSE_TEST", payload={})
    await redis_backend.enqueue(event)

    await redis_backend.close()
    assert redis_backend._redis is None


# =============================================================================
# Spine + Redis Integration
# =============================================================================


@pytest.mark.asyncio
async def test_spine_with_redis_backend():
    """Test full Spine + RedisBackend integration."""
    import uuid

    from necrostack.core.organ import Organ
    from necrostack.core.spine import Spine

    stream_key = f"necrostack:test:{uuid.uuid4().hex[:8]}"
    spine_ref: list[Spine | None] = [None]

    class CounterOrgan(Organ):
        listens_to = ["COUNT"]
        processed = []

        def handle(self, event: Event) -> Event | None:
            CounterOrgan.processed.append(event.payload["n"])
            if event.payload["n"] < 3:
                return Event(event_type="COUNT", payload={"n": event.payload["n"] + 1})
            # Stop spine when done
            if spine_ref[0]:
                spine_ref[0].stop()
            return None

    CounterOrgan.processed = []

    backend = RedisBackend(redis_url=REDIS_URL, stream_key=stream_key)
    spine = Spine(organs=[CounterOrgan()], backend=backend, max_steps=10)
    spine_ref[0] = spine

    stats = await spine.run(Event(event_type="COUNT", payload={"n": 1}))

    assert CounterOrgan.processed == [1, 2, 3]
    assert stats.events_processed == 3
    assert backend.metrics.events_acked == 3

    await backend.delete_stream(stream_key)
    await backend.close()
