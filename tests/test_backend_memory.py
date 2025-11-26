"""Property-based tests for InMemoryBackend."""

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from necrostack.backends.memory import InMemoryBackend
from necrostack.core.event import Event
from tests.conftest import valid_event_data


def test_backend_imports():
    """Verify backend can be imported."""
    backend = InMemoryBackend()
    assert backend is not None


@st.composite
def event_sequences(draw: st.DrawFn) -> list[Event]:
    """Generate sequences of Events for testing."""
    event_data_list = draw(st.lists(
        valid_event_data(),
        min_size=1,
        max_size=20
    ))
    return [Event(**data) for data in event_data_list]


# **Feature: necrostack-framework, Property 9: Backend FIFO Ordering**
# **Validates: Requirements 4.2**
@settings(max_examples=100)
@given(events=event_sequences())
async def test_backend_fifo_ordering(events: list[Event]):
    """For any sequence of Events enqueued to the in-memory backend,
    dequeuing should return them in the same order they were enqueued (FIFO).
    """
    backend = InMemoryBackend()
    
    # Enqueue all events
    for event in events:
        await backend.enqueue(event)
    
    # Pull all events and verify FIFO order
    pulled_events = []
    for _ in range(len(events)):
        pulled = await backend.pull(timeout=0.1)
        assert pulled is not None, "Expected event but got None"
        pulled_events.append(pulled)
    
    # Verify the order matches
    assert len(pulled_events) == len(events)
    for original, pulled in zip(events, pulled_events):
        assert pulled.id == original.id
        assert pulled.event_type == original.event_type
        assert pulled.payload == original.payload
    
    # Verify queue is now empty
    empty_pull = await backend.pull(timeout=0.1)
    assert empty_pull is None, "Queue should be empty after pulling all events"
    
    await backend.close()


async def test_backend_timeout_on_empty_queue():
    """Backend should return None when timeout is reached on empty queue."""
    backend = InMemoryBackend()
    
    # Pull from empty queue with timeout
    result = await backend.pull(timeout=0.1)
    assert result is None
    
    await backend.close()


async def test_backend_close_clears_queue():
    """Backend close should clear all pending events."""
    backend = InMemoryBackend()
    
    # Enqueue some events
    event1 = Event(event_type="test.event1", payload={"data": 1})
    event2 = Event(event_type="test.event2", payload={"data": 2})
    
    await backend.enqueue(event1)
    await backend.enqueue(event2)
    
    # Close the backend
    await backend.close()
    
    # Queue should be empty now
    result = await backend.pull(timeout=0.1)
    assert result is None


async def test_backend_ack_is_noop():
    """Backend ack should be a no-op for in-memory backend."""
    backend = InMemoryBackend()
    
    event = Event(event_type="test.event", payload={"data": 1})
    await backend.enqueue(event)
    
    pulled = await backend.pull(timeout=0.1)
    assert pulled is not None
    
    # ack should not raise any errors
    await backend.ack(pulled)
    
    await backend.close()
