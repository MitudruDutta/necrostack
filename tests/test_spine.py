"""Property-based tests for Spine dispatcher."""

import asyncio
from typing import Sequence

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from necrostack.backends.memory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import Spine
from tests.conftest import valid_event_types


# --- Test Organs for property tests ---

class ValidOrgan(Organ):
    """A valid organ with correct signature."""
    listens_to = ["test.event"]
    
    def handle(self, event: Event) -> None:
        return None


class AsyncValidOrgan(Organ):
    """A valid async organ with correct signature."""
    listens_to = ["test.event"]
    
    async def handle(self, event: Event) -> None:
        return None


class NoParamOrgan(Organ):
    """Invalid organ - handle() takes no parameters."""
    listens_to = ["test.event"]
    
    def handle(self) -> None:
        return None


class TwoParamOrgan(Organ):
    """Invalid organ - handle() takes two required parameters."""
    listens_to = ["test.event"]
    
    def handle(self, event: Event, extra: str) -> None:
        return None


class OptionalParamOrgan(Organ):
    """Valid organ - handle() has one required and one optional parameter."""
    listens_to = ["test.event"]
    
    def handle(self, event: Event, extra: str = "default") -> None:
        return None


# **Feature: necrostack-framework, Property 10: Invalid Organ Signature Detection**
# **Validates: Requirements 7.2**
def test_invalid_organ_signature_no_params():
    """Organ with handle() taking no parameters should raise TypeError at registration."""
    backend = InMemoryBackend()
    
    with pytest.raises(TypeError) as exc_info:
        Spine(organs=[NoParamOrgan()], backend=backend)
    
    assert "must accept exactly one required parameter" in str(exc_info.value)
    assert "NoParamOrgan" in str(exc_info.value)


def test_invalid_organ_signature_two_params():
    """Organ with handle() taking two required parameters should raise TypeError."""
    backend = InMemoryBackend()
    
    with pytest.raises(TypeError) as exc_info:
        Spine(organs=[TwoParamOrgan()], backend=backend)
    
    assert "must accept exactly one required parameter" in str(exc_info.value)
    assert "TwoParamOrgan" in str(exc_info.value)


def test_valid_organ_signature_with_optional_params():
    """Organ with handle() having one required and optional params should be valid."""
    backend = InMemoryBackend()
    
    # Should not raise
    spine = Spine(organs=[OptionalParamOrgan()], backend=backend)
    assert len(spine.organs) == 1


def test_valid_organ_signature_sync():
    """Valid sync organ should be accepted."""
    backend = InMemoryBackend()
    
    # Should not raise
    spine = Spine(organs=[ValidOrgan()], backend=backend)
    assert len(spine.organs) == 1


def test_valid_organ_signature_async():
    """Valid async organ should be accepted."""
    backend = InMemoryBackend()
    
    # Should not raise
    spine = Spine(organs=[AsyncValidOrgan()], backend=backend)
    assert len(spine.organs) == 1


# **Feature: necrostack-framework, Property 10: Invalid Organ Signature Detection**
# **Validates: Requirements 7.2**
@settings(max_examples=100)
@given(event_types=st.lists(valid_event_types(), min_size=1, max_size=5))
def test_invalid_organ_signature_detection_property(event_types: list[str]):
    """For any Organ subclass where handle() has incorrect signature,
    registration with Spine should raise a descriptive error.
    """
    # Create an invalid organ dynamically with the given event types
    class DynamicInvalidOrgan(Organ):
        listens_to = event_types
        
        def handle(self) -> None:  # Invalid: no event parameter
            return None
    
    backend = InMemoryBackend()
    
    with pytest.raises(TypeError) as exc_info:
        Spine(organs=[DynamicInvalidOrgan()], backend=backend)
    
    error_msg = str(exc_info.value)
    assert "must accept exactly one required parameter" in error_msg
    assert "DynamicInvalidOrgan" in error_msg


# --- Helper for tracking organ invocations ---

class TrackingOrgan(Organ):
    """Organ that tracks which events it received."""
    
    def __init__(self, name: str, event_types: list[str]):
        self.name = name
        self.listens_to = event_types
        self.received_events: list[Event] = []
    
    def handle(self, event: Event) -> None:
        self.received_events.append(event)
        return None


# **Feature: necrostack-framework, Property 4: Event Routing Correctness**
# **Validates: Requirements 2.2, 2.3, 3.3**
@settings(max_examples=100)
@given(
    event_type=valid_event_types(),
    organ_configs=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            st.lists(valid_event_types(), min_size=1, max_size=3)
        ),
        min_size=1,
        max_size=5
    )
)
@pytest.mark.asyncio
async def test_event_routing_correctness_property(
    event_type: str,
    organ_configs: list[tuple[str, list[str]]]
):
    """For any Event with a given event_type and any set of Organs,
    the Spine should invoke the handle() method of exactly those Organs
    whose listens_to list contains that event_type.
    """
    # Create tracking organs with the given configurations
    organs = [
        TrackingOrgan(name=f"organ_{name}", event_types=types)
        for name, types in organ_configs
    ]
    
    backend = InMemoryBackend()
    spine = Spine(organs=organs, backend=backend)
    
    # Create and dispatch an event
    event = Event(event_type=event_type, payload={"test": True})
    await spine._dispatch_event(event)
    
    # Verify routing: only organs whose listens_to contains event_type should receive it
    for organ in organs:
        should_receive = event_type in organ.listens_to
        did_receive = len(organ.received_events) > 0
        
        assert should_receive == did_receive, (
            f"Organ {organ.name} with listens_to={organ.listens_to} "
            f"{'should' if should_receive else 'should not'} have received "
            f"event_type={event_type}, but did_receive={did_receive}"
        )
        
        # If received, verify it's the correct event
        if did_receive:
            assert organ.received_events[0].id == event.id
            assert organ.received_events[0].event_type == event_type


# --- Organs for handler return value testing ---

class SingleEventReturnOrgan(Organ):
    """Organ that returns a single Event."""
    listens_to = ["test.single"]
    
    def __init__(self, return_event_type: str):
        self.return_event_type = return_event_type
    
    def handle(self, event: Event) -> Event:
        return Event(event_type=self.return_event_type, payload={"source": str(event.id)})


class MultiEventReturnOrgan(Organ):
    """Organ that returns multiple Events."""
    listens_to = ["test.multi"]
    
    def __init__(self, return_event_types: list[str]):
        self.return_event_types = return_event_types
    
    def handle(self, event: Event) -> Sequence[Event]:
        return [
            Event(event_type=et, payload={"source": str(event.id), "index": i})
            for i, et in enumerate(self.return_event_types)
        ]


class NoneReturnOrgan(Organ):
    """Organ that returns None (terminal)."""
    listens_to = ["test.none"]
    
    def handle(self, event: Event) -> None:
        return None


# **Feature: necrostack-framework, Property 5: Handler Return Value Processing**
# **Validates: Requirements 2.6, 2.7**
@settings(max_examples=100)
@given(
    return_type=st.sampled_from(["single", "multi", "none"]),
    return_event_types=st.lists(valid_event_types(), min_size=1, max_size=3)
)
@pytest.mark.asyncio
async def test_handler_return_value_processing_property(
    return_type: str,
    return_event_types: list[str]
):
    """For any Organ handler invocation, if the handler returns Event(s),
    those Events should be enqueued to the backend; if the handler returns None,
    no Events should be enqueued.
    """
    backend = InMemoryBackend()
    
    # Create organ based on return type
    if return_type == "single":
        organ = SingleEventReturnOrgan(return_event_type=return_event_types[0])
        expected_count = 1
    elif return_type == "multi":
        organ = MultiEventReturnOrgan(return_event_types=return_event_types)
        expected_count = len(return_event_types)
    else:  # none
        organ = NoneReturnOrgan()
        expected_count = 0
    
    spine = Spine(organs=[organ], backend=backend)
    
    # Create input event
    input_event = Event(event_type=organ.listens_to[0], payload={"test": True})
    
    # Invoke handler and process result
    result = await spine._invoke_handler(organ, input_event)
    await spine._process_handler_result(result)
    
    # Count events in backend
    enqueued_events = []
    while True:
        event = await backend.pull(timeout=0.01)
        if event is None:
            break
        enqueued_events.append(event)
    
    # Verify correct number of events enqueued
    assert len(enqueued_events) == expected_count, (
        f"Expected {expected_count} events enqueued for return_type={return_type}, "
        f"but got {len(enqueued_events)}"
    )
    
    # Verify event types if events were returned
    if return_type == "single":
        assert enqueued_events[0].event_type == return_event_types[0]
    elif return_type == "multi":
        for i, event in enumerate(enqueued_events):
            assert event.event_type == return_event_types[i]


# --- Organ for invocation order testing ---

class OrderTrackingOrgan(Organ):
    """Organ that records its invocation order to a shared list."""
    
    def __init__(self, name: str, event_types: list[str], invocation_log: list[str]):
        self.name = name
        self.listens_to = event_types
        self.invocation_log = invocation_log
    
    def handle(self, event: Event) -> None:
        self.invocation_log.append(self.name)
        return None


# **Feature: necrostack-framework, Property 6: Organ Invocation Order**
# **Validates: Requirements 3.4**
@settings(max_examples=100)
@given(
    event_type=valid_event_types(),
    organ_count=st.integers(min_value=2, max_value=6)
)
@pytest.mark.asyncio
async def test_organ_invocation_order_property(event_type: str, organ_count: int):
    """For any Event that matches multiple Organs, the Spine should invoke
    their handlers in the exact order the Organs were provided to the Spine
    constructor (deterministic ordering).
    """
    invocation_log: list[str] = []
    
    # Create organs that all listen to the same event type
    organ_names = [f"organ_{i}" for i in range(organ_count)]
    organs = [
        OrderTrackingOrgan(name=name, event_types=[event_type], invocation_log=invocation_log)
        for name in organ_names
    ]
    
    backend = InMemoryBackend()
    spine = Spine(organs=organs, backend=backend)
    
    # Dispatch an event
    event = Event(event_type=event_type, payload={"test": True})
    await spine._dispatch_event(event)
    
    # Verify invocation order matches registration order
    assert invocation_log == organ_names, (
        f"Expected invocation order {organ_names}, but got {invocation_log}"
    )


# --- Organs for error resilience testing ---

class FailingOrgan(Organ):
    """Organ that raises an exception."""
    
    def __init__(self, event_types: list[str]):
        self.listens_to = event_types
    
    def handle(self, event: Event) -> None:
        raise ValueError("Intentional failure for testing")


class CountingOrgan(Organ):
    """Organ that counts successful invocations."""
    
    def __init__(self, event_types: list[str]):
        self.listens_to = event_types
        self.count = 0
    
    def handle(self, event: Event) -> None:
        self.count += 1
        return None


# **Feature: necrostack-framework, Property 7: Error Resilience**
# **Validates: Requirements 3.5**
@settings(max_examples=100)
@given(
    event_count=st.integers(min_value=2, max_value=10),
    fail_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=1, max_size=5, unique=True)
)
@pytest.mark.asyncio
async def test_error_resilience_property(event_count: int, fail_indices: list[int]):
    """For any sequence of Events where some handlers raise exceptions,
    the Spine should continue processing subsequent Events.
    """
    # Normalize fail_indices to be within event_count range
    fail_indices = [i % event_count for i in fail_indices]
    fail_indices_set = set(fail_indices)
    
    event_type = "test.resilience"
    
    # Create organs: one that fails, one that counts
    failing_organ = FailingOrgan(event_types=[event_type])
    counting_organ = CountingOrgan(event_types=[event_type])
    
    backend = InMemoryBackend()
    spine = Spine(organs=[failing_organ, counting_organ], backend=backend)
    
    # Emit events
    for i in range(event_count):
        await spine.emit(Event(event_type=event_type, payload={"index": i}))
    
    # Run - should process all events despite failures
    import logging
    logging.getLogger("necrostack.spine").setLevel(logging.CRITICAL)
    
    steps = await spine.run_until_empty(timeout=0.1)
    
    # All events should be processed
    assert steps == event_count, (
        f"Expected {event_count} steps, got {steps}. "
        f"Errors should not stop processing."
    )
    
    # Counting organ should have been called for all events
    # (it comes after failing organ, so it should still be called)
    assert counting_organ.count == event_count, (
        f"Expected counting_organ to be called {event_count} times, "
        f"but was called {counting_organ.count} times. "
        f"Errors in one organ should not prevent other organs from being called."
    )


# --- Organ for max-steps testing ---

class InfiniteChainOrgan(Organ):
    """Organ that always emits another event, creating an infinite chain."""
    listens_to = ["test.chain"]
    
    def handle(self, event: Event) -> Event:
        # Always emit another event to create infinite loop potential
        return Event(event_type="test.chain", payload={"depth": event.payload.get("depth", 0) + 1})


# **Feature: necrostack-framework, Property 8: Max-Steps Termination**
# **Validates: Requirements 3.7**
@settings(max_examples=100)
@given(
    max_steps=st.integers(min_value=1, max_value=50),
    initial_events=st.integers(min_value=1, max_value=10)
)
@pytest.mark.asyncio
async def test_max_steps_termination_property(max_steps: int, initial_events: int):
    """For any Spine configured with max_steps=N, the processing loop should
    terminate after at most N event processing iterations, regardless of how
    many events are in the queue.
    """
    backend = InMemoryBackend()
    organ = InfiniteChainOrgan()
    spine = Spine(organs=[organ], backend=backend, max_steps=max_steps)
    
    # Emit initial events that will chain infinitely
    for i in range(initial_events):
        await spine.emit(Event(event_type="test.chain", payload={"depth": 0}))
    
    # Run - should terminate at max_steps
    steps = await spine.run_until_empty(timeout=0.1)
    
    # Should have processed exactly max_steps events
    assert steps == max_steps, (
        f"Expected exactly {max_steps} steps (max_steps), but got {steps}. "
        f"The loop should terminate at max_steps regardless of queue size."
    )


# Additional test: verify max_steps works with run() method too
@settings(max_examples=50)
@given(max_steps=st.integers(min_value=1, max_value=20))
@pytest.mark.asyncio
async def test_max_steps_with_run_method(max_steps: int):
    """Verify max_steps also works with the run() method."""
    backend = InMemoryBackend()
    organ = InfiniteChainOrgan()
    spine = Spine(organs=[organ], backend=backend, max_steps=max_steps)
    
    # Emit initial event
    await spine.emit(Event(event_type="test.chain", payload={"depth": 0}))
    
    # Use run() with a stop after a short delay to avoid infinite wait
    async def stop_after_delay():
        await asyncio.sleep(0.5)
        spine.stop()
    
    stop_task = asyncio.create_task(stop_after_delay())
    steps = await spine.run()
    stop_task.cancel()
    try:
        await stop_task
    except asyncio.CancelledError:
        pass
    
    # Should have processed at most max_steps events
    assert steps <= max_steps, (
        f"Expected at most {max_steps} steps, but got {steps}. "
        f"The loop should respect max_steps limit."
    )
