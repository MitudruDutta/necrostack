"""Integration tests for RedisBackend.

These tests require a running Redis instance. They are skipped if Redis
is not available.
"""

import asyncio
import uuid

import pytest

from necrostack.core.event import Event

# Skip all tests if redis is not installed
try:
    from necrostack.backends.redis import RedisBackend
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisBackend = None  # type: ignore


pytestmark = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="Redis package not installed"
)


async def redis_is_running(url: str = "redis://localhost:6379") -> bool:
    """Check if Redis is running and accessible."""
    if not REDIS_AVAILABLE:
        return False
    try:
        import redis.asyncio as redis
        client = redis.from_url(url)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


@pytest.fixture
async def redis_backend():
    """Create a RedisBackend with a unique stream key for test isolation."""
    if not await redis_is_running():
        pytest.skip("Redis is not running")
    
    # Use unique stream key for each test to avoid interference
    stream_key = f"necrostack:test:{uuid.uuid4().hex}"
    backend = RedisBackend(stream_key=stream_key)
    
    yield backend
    
    # Cleanup: delete the test stream and close connection
    try:
        client = await backend._ensure_connected()
        await client.delete(stream_key)
    except Exception:
        pass
    await backend.close()


async def test_redis_backend_enqueue_pull_roundtrip(redis_backend: RedisBackend):
    """Test enqueue/pull round-trip with real Redis."""
    event = Event(
        event_type="test.roundtrip",
        payload={"message": "hello", "count": 42}
    )
    
    # Enqueue the event
    await redis_backend.enqueue(event)
    
    # Pull the event back
    pulled = await redis_backend.pull(timeout=1.0)
    
    assert pulled is not None
    assert pulled.id == event.id
    assert pulled.event_type == event.event_type
    assert pulled.payload == event.payload
    assert pulled.timestamp == event.timestamp


async def test_redis_backend_fifo_ordering(redis_backend: RedisBackend):
    """Test that events are returned in FIFO order."""
    events = [
        Event(event_type="test.order", payload={"seq": i})
        for i in range(5)
    ]
    
    # Enqueue all events
    for event in events:
        await redis_backend.enqueue(event)
    
    # Pull and verify order
    for i, original in enumerate(events):
        pulled = await redis_backend.pull(timeout=1.0)
        assert pulled is not None, f"Expected event {i} but got None"
        assert pulled.id == original.id
        assert pulled.payload["seq"] == i


async def test_redis_backend_timeout_on_empty_stream(redis_backend: RedisBackend):
    """Test timeout behavior on empty stream."""
    # Pull from empty stream with short timeout
    result = await redis_backend.pull(timeout=0.5)
    
    assert result is None


async def test_redis_backend_connection_handling(redis_backend: RedisBackend):
    """Test connection is established lazily and can be closed."""
    # Connection should not exist yet
    assert redis_backend._client is None
    
    # Enqueue triggers connection
    event = Event(event_type="test.connection", payload={})
    await redis_backend.enqueue(event)
    
    # Connection should now exist
    assert redis_backend._client is not None
    
    # Close should work
    await redis_backend.close()
    assert redis_backend._client is None


async def test_redis_backend_ack_is_noop(redis_backend: RedisBackend):
    """Test that ack is a no-op for MVP."""
    event = Event(event_type="test.ack", payload={})
    await redis_backend.enqueue(event)
    
    pulled = await redis_backend.pull(timeout=1.0)
    assert pulled is not None
    
    # ack should not raise any errors
    await redis_backend.ack(pulled)


async def test_redis_backend_multiple_events(redis_backend: RedisBackend):
    """Test handling multiple events with different payloads."""
    events = [
        Event(event_type="user.created", payload={"user_id": "u1", "name": "Alice"}),
        Event(event_type="order.placed", payload={"order_id": "o1", "amount": 99.99}),
        Event(event_type="payment.processed", payload={"payment_id": "p1", "status": "success"}),
    ]
    
    for event in events:
        await redis_backend.enqueue(event)
    
    for original in events:
        pulled = await redis_backend.pull(timeout=1.0)
        assert pulled is not None
        assert pulled.id == original.id
        assert pulled.event_type == original.event_type
        assert pulled.payload == original.payload
