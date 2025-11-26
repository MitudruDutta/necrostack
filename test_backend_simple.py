#!/usr/bin/env python3
"""Simple test to verify backend works."""

import asyncio
from necrostack.backends.memory import InMemoryBackend
from necrostack.core.event import Event


async def main():
    backend = InMemoryBackend()
    
    # Create and enqueue events
    event1 = Event(event_type="test.first", payload={"order": 1})
    event2 = Event(event_type="test.second", payload={"order": 2})
    event3 = Event(event_type="test.third", payload={"order": 3})
    
    await backend.enqueue(event1)
    await backend.enqueue(event2)
    await backend.enqueue(event3)
    
    # Pull events and verify FIFO order
    pulled1 = await backend.pull(timeout=0.1)
    pulled2 = await backend.pull(timeout=0.1)
    pulled3 = await backend.pull(timeout=0.1)
    
    assert pulled1.id == event1.id, f"Expected {event1.id}, got {pulled1.id}"
    assert pulled2.id == event2.id, f"Expected {event2.id}, got {pulled2.id}"
    assert pulled3.id == event3.id, f"Expected {event3.id}, got {pulled3.id}"
    
    # Verify queue is empty
    empty = await backend.pull(timeout=0.1)
    assert empty is None, "Queue should be empty"
    
    await backend.close()
    
    print("✓ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
