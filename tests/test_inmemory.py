"""Tests for InMemoryBackend."""

import asyncio
import pytest

from necrostack.core.event import Event
from necrostack.backends.inmemory import InMemoryBackend


@pytest.mark.asyncio
async def test_enqueue_and_pull_fifo_order():
    """Test that events are pulled in FIFO order."""
    backend = InMemoryBackend()
    
    event1 = Event(event_type="TEST_EVENT", payload={"data": 1})
    event2 = Event(event_type="TEST_EVENT", payload={"data": 2})
    
    await backend.enqueue(event1)
    await backend.enqueue(event2)
    
    pulled1 = await backend.pull(timeout=0.1)
    pulled2 = await backend.pull(timeout=0.1)
    
    assert pulled1 is not None
    assert pulled2 is not None
    assert pulled1.payload["data"] == 1
    assert pulled2.payload["data"] == 2


@pytest.mark.asyncio
async def test_pull_timeout_returns_none():
    """Test that pull returns None on timeout with empty queue."""
    backend = InMemoryBackend()
    
    result = await backend.pull(timeout=0.1)
    
    assert result is None


@pytest.mark.asyncio
async def test_ack_is_noop():
    """Test that ack completes without error (no-op)."""
    backend = InMemoryBackend()
    event = Event(event_type="TEST_EVENT", payload={})
    
    # Should not raise
    result = await backend.ack(event)
    assert result is None
