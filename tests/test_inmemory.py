"""Tests for InMemoryBackend."""

import asyncio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from necrostack.core.event import Event
from necrostack.backends.inmemory import InMemoryBackend


# Strategy for generating valid event types
valid_event_type = st.from_regex(r"[A-Z][A-Z0-9_]{0,20}", fullmatch=True)

# Strategy for generating simple payloads
simple_payload = st.fixed_dictionaries({}, optional={
    "index": st.integers(min_value=0, max_value=1000),
    "data": st.text(max_size=20),
})


# **Feature: necrostack-framework, Property 11: Backend FIFO Ordering**
# **Validates: Requirements 5.2**
@given(event_count=st.integers(min_value=1, max_value=50))
@settings(max_examples=100)
def test_backend_fifo_ordering(event_count: int):
    """For any sequence of Events enqueued to InMemoryBackend,
    pulling events SHALL return them in the same order they were enqueued (FIFO).
    """
    import asyncio
    
    async def run_fifo_test():
        backend = InMemoryBackend()
        
        # Create events with sequential indices to track order
        events = [
            Event(event_type="TEST_EVENT", payload={"index": i})
            for i in range(event_count)
        ]
        
        # Enqueue all events
        for event in events:
            await backend.enqueue(event)
        
        # Pull all events and verify FIFO order
        pulled_events = []
        for _ in range(event_count):
            pulled = await backend.pull(timeout=0.01)
            assert pulled is not None, "Expected event but got None"
            pulled_events.append(pulled)
        
        # Verify order matches enqueue order
        for i, (original, pulled) in enumerate(zip(events, pulled_events)):
            assert pulled.id == original.id, f"Event {i} ID mismatch"
            assert pulled.payload["index"] == i, f"Event {i} order mismatch"
        
        # Verify queue is now empty
        empty_pull = await backend.pull(timeout=0.01)
        assert empty_pull is None, "Queue should be empty after pulling all events"
    
    asyncio.run(run_fifo_test())


# **Feature: necrostack-framework, Property 12: Backend Pull Timeout**
# **Validates: Requirements 5.3**
@given(timeout_seconds=st.floats(min_value=0.01, max_value=0.1))
@settings(max_examples=100)
def test_backend_pull_timeout(timeout_seconds: float):
    """For any empty InMemoryBackend, calling pull(timeout=T) SHALL return None
    after approximately T seconds without blocking indefinitely.
    """
    import asyncio
    import time
    
    async def run_timeout_test():
        backend = InMemoryBackend()
        
        # Measure time for pull on empty queue
        start_time = time.monotonic()
        result = await backend.pull(timeout=timeout_seconds)
        elapsed_time = time.monotonic() - start_time
        
        # Result should be None (empty queue)
        assert result is None, "Pull on empty queue should return None"
        
        # Elapsed time should be approximately the timeout (with tolerance)
        # Allow 50% tolerance for timing variations
        min_expected = timeout_seconds * 0.5
        max_expected = timeout_seconds * 2.0
        
        assert elapsed_time >= min_expected, (
            f"Pull returned too quickly: {elapsed_time:.3f}s < {min_expected:.3f}s"
        )
        assert elapsed_time <= max_expected, (
            f"Pull blocked too long: {elapsed_time:.3f}s > {max_expected:.3f}s"
        )
    
    asyncio.run(run_timeout_test())


@pytest.mark.asyncio
async def test_enqueue_and_pull_fifo_order():
    """Test that events are pulled in FIFO order."""
    backend = InMemoryBackend()
    
    event1 = Event(event_type="TEST_EVENT", payload={"data": 1})
    event2 = Event(event_type="TEST_EVENT", payload={"data": 2})
    
    await backend.enqueue(event1)
    await backend.enqueue(event2)
    
    pulled1 = await backend.pull(timeout=0.01)
    pulled2 = await backend.pull(timeout=0.01)
    
    assert pulled1 is not None
    assert pulled2 is not None
    assert pulled1.payload["data"] == 1
    assert pulled2.payload["data"] == 2

    # Edge case: pulling from empty queue should return None
    pulled3 = await backend.pull(timeout=0.01)
    assert pulled3 is None


@pytest.mark.asyncio
async def test_pull_timeout_returns_none():
    """Test that pull returns None on timeout with empty queue."""
    backend = InMemoryBackend()
    
    result = await backend.pull(timeout=0.01)
    
    assert result is None


@pytest.mark.asyncio
async def test_ack_is_noop():
    """Test that ack completes without error (no-op)."""
    backend = InMemoryBackend()
    event = Event(event_type="TEST_EVENT", payload={})
    
    # Should not raise
    result = await backend.ack(event)
    assert result is None


@pytest.mark.asyncio
async def test_ack_after_pull():
    """Test that ack completes without error after enqueue and pull."""
    backend = InMemoryBackend()
    event = Event(event_type="TEST_EVENT", payload={"key": "value"})

    await backend.enqueue(event)
    pulled = await backend.pull(timeout=0.01)

    assert pulled is not None
    result = await backend.ack(pulled)
    assert result is None
