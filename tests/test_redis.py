"""Tests for RedisBackend.

These tests require a running Redis instance. Start one with:
    docker-compose up -d

Tests will be skipped if Redis is not available.
"""

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


# Skip all tests in this module if Redis is not available
pytestmark = pytest.mark.skipif(
    not redis_available(),
    reason="Redis not available at localhost:6379. Start with: docker-compose up -d",
)

REDIS_URL = "redis://localhost:6379"


@pytest.fixture
async def redis_backend():
    """Create a RedisBackend with a unique stream key for test isolation."""
    import logging
    import uuid

    from redis.exceptions import RedisError

    stream_key = f"necrostack:test:{uuid.uuid4().hex[:8]}"
    backend = RedisBackend(redis_url=REDIS_URL, stream_key=stream_key)
    yield backend
    # Cleanup: delete the test stream using public API
    try:
        await backend.delete_stream(stream_key)
    except RedisError as e:
        logging.getLogger(__name__).warning(f"Failed to cleanup test stream {stream_key}: {e}")
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Unexpected error cleaning up test stream {stream_key}: {e}"
        )
    await backend.close()


@pytest.mark.asyncio
async def test_redis_enqueue_and_pull(redis_backend):
    """Test basic enqueue and pull operations."""
    event = Event(event_type="TEST_EVENT", payload={"key": "value"})

    await redis_backend.enqueue(event)
    pulled = await redis_backend.pull(timeout=2.0)

    assert pulled is not None
    assert pulled.id == event.id
    assert pulled.event_type == event.event_type
    assert pulled.payload == event.payload


@pytest.mark.asyncio
async def test_redis_fifo_ordering(redis_backend):
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


@pytest.mark.asyncio
async def test_redis_pull_timeout_on_empty(redis_backend):
    """Test that pull returns None on timeout when stream is empty."""
    result = await redis_backend.pull(timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_redis_ack_is_noop(redis_backend):
    """Test that ack is a no-op (doesn't raise)."""
    event = Event(event_type="TEST_EVENT")
    # Should not raise
    await redis_backend.ack(event)


@pytest.mark.asyncio
async def test_redis_event_serialization_round_trip(redis_backend):
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
    assert pulled.event_type == event.event_type
    assert pulled.payload == event.payload
    # Timestamp should be preserved (within reasonable precision)
    assert abs((pulled.timestamp - event.timestamp).total_seconds()) < 1
