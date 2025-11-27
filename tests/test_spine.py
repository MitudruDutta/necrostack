"""Property-based tests for Spine dispatcher.

Tests cover:
- Property 6: Organ listens_to Validation
- Property 7: Event Routing Correctness
- Property 8: Handler Return Enqueueing
- Property 9: Organ Invocation Order
- Property 10: Max Steps Enforcement
- Property 13: Sync and Async Handler Support
- Architecture invariant: Spine never stores events internally
"""

import asyncio
from collections import deque

import pytest

from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import Spine


class StoppingBackend:
    """Backend that stops spine after processing events."""

    def __init__(self, spine_ref, max_events=10):
        self._queue = None
        self._events_returned = 0
        self._max_events = max_events
        self._spine_ref = spine_ref

    def _get_queue(self):
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    async def enqueue(self, event):
        await self._get_queue().put(event)

    async def pull(self, timeout=1.0):
        if self._events_returned >= self._max_events:
            if self._spine_ref[0]:
                self._spine_ref[0].stop()
            return None
        try:
            event = await asyncio.wait_for(self._get_queue().get(), timeout=0.01)
            self._events_returned += 1
            return event
        except TimeoutError:
            if self._spine_ref[0]:
                self._spine_ref[0].stop()
            return None

    async def ack(self, event):
        pass


# =============================================================================
# Property 6: Organ listens_to Validation
# **Feature: necrostack-framework, Property 6: Organ listens_to Validation**
# **Validates: Requirements 2.3**
# =============================================================================


class TestOrganListensToValidation:
    """Property 6: Organ listens_to Validation tests."""

    @pytest.mark.parametrize("invalid_value", [123, 45.6, True, False, None, [1, 2], {"a": 1}])
    def test_rejects_non_string_in_listens_to(self, invalid_value):
        """Spine SHALL reject organs with non-string listens_to elements."""

        def handle(self, event):
            return None

        organ_class = type(
            "TestOrgan",
            (Organ,),
            {
                "listens_to": ["VALID", invalid_value],
                "handle": handle,
            },
        )
        organ = organ_class()

        spine_ref = [None]
        backend = StoppingBackend(spine_ref)

        with pytest.raises(TypeError) as exc_info:
            Spine(organs=[organ], backend=backend)

        assert "listens_to" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_listens_to", ["not_a_list", 123, None, {"key": "value"}])
    def test_rejects_non_list_listens_to(self, invalid_listens_to):
        """Spine SHALL reject organs where listens_to is not a list."""

        def handle(self, event):
            return None

        organ_class = type(
            "TestOrgan",
            (Organ,),
            {
                "listens_to": invalid_listens_to,
                "handle": handle,
            },
        )
        organ = organ_class()

        spine_ref = [None]
        backend = StoppingBackend(spine_ref)

        with pytest.raises(TypeError) as exc_info:
            Spine(organs=[organ], backend=backend)

        assert "listens_to" in str(exc_info.value)

    @pytest.mark.parametrize(
        "valid_listens_to", [[], ["EVENT_A"], ["EVENT_A", "EVENT_B"], ["A", "B", "C", "D", "E"]]
    )
    def test_accepts_valid_string_lists(self, valid_listens_to):
        """Spine SHALL accept organs with valid string listens_to."""

        def handle(self, event):
            return None

        organ_class = type(
            "TestOrgan",
            (Organ,),
            {
                "listens_to": valid_listens_to,
                "handle": handle,
            },
        )
        organ = organ_class()

        spine_ref = [None]
        backend = StoppingBackend(spine_ref)

        spine = Spine(organs=[organ], backend=backend)
        assert organ in spine.organs


# =============================================================================
# Property 7: Event Routing Correctness
# **Feature: necrostack-framework, Property 7: Event Routing Correctness**
# **Validates: Requirements 3.3**
# =============================================================================


class TestEventRoutingCorrectness:
    """Property 7: Event Routing Correctness tests."""

    @pytest.mark.asyncio
    async def test_routes_to_matching_organs_only(self):
        """Spine SHALL invoke handle() only on organs whose listens_to contains event_type."""
        invocations = []
        spine_ref = [None]

        def make_organ(name, listens_to):
            def handle(self, event):
                invocations.append(name)
                return None

            return type(name, (Organ,), {"listens_to": listens_to, "handle": handle})()

        organs = [
            make_organ("OrganA", ["EVENT_X"]),
            make_organ("OrganB", ["EVENT_Y"]),
            make_organ("OrganC", ["EVENT_X", "EVENT_Y"]),
        ]

        backend = StoppingBackend(spine_ref, max_events=5)
        spine = Spine(organs=organs, backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="EVENT_X", payload={}))

        assert invocations == ["OrganA", "OrganC"]

    @pytest.mark.asyncio
    async def test_no_match_invokes_no_organs(self):
        """Spine SHALL not invoke any organ if no listens_to matches."""
        invocations = []
        spine_ref = [None]

        def make_organ(name, listens_to):
            def handle(self, event):
                invocations.append(name)
                return None

            return type(name, (Organ,), {"listens_to": listens_to, "handle": handle})()

        organs = [
            make_organ("OrganA", ["EVENT_A"]),
            make_organ("OrganB", ["EVENT_B"]),
        ]

        backend = StoppingBackend(spine_ref, max_events=5)
        spine = Spine(organs=organs, backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="EVENT_Z", payload={}))

        assert invocations == []


# =============================================================================
# Property 8: Handler Return Enqueueing
# **Feature: necrostack-framework, Property 8: Handler Return Enqueueing**
# **Validates: Requirements 3.5**
# =============================================================================


class TestHandlerReturnEnqueueing:
    """Property 8: Handler Return Enqueueing tests."""

    @pytest.mark.asyncio
    async def test_single_event_return_enqueued(self):
        """Spine SHALL enqueue single Event returned by handler."""
        received = []
        spine_ref = [None]

        def emitter_handle(self, event):
            return Event(event_type="EMITTED", payload={"src": str(event.id)})

        def receiver_handle(self, event):
            received.append(event)
            return None

        emitter_cls = type("Emitter", (Organ,), {"listens_to": ["START"], "handle": emitter_handle})
        receiver_cls = type(
            "Receiver", (Organ,), {"listens_to": ["EMITTED"], "handle": receiver_handle}
        )

        backend = StoppingBackend(spine_ref, max_events=10)
        spine = Spine(organs=[emitter_cls(), receiver_cls()], backend=backend, max_steps=10)
        spine_ref[0] = spine

        start = Event(event_type="START", payload={})
        await spine.run(start_event=start)

        assert len(received) == 1
        assert received[0].event_type == "EMITTED"
        assert received[0].payload["src"] == str(start.id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("num_events", [1, 2, 3, 5])
    async def test_list_of_events_all_enqueued(self, num_events):
        """Spine SHALL enqueue ALL Events in list returned by handler."""
        received = []
        spine_ref = [None]

        def emitter_handle(self, event):
            return [Event(event_type="EMITTED", payload={"i": i}) for i in range(num_events)]

        def receiver_handle(self, event):
            received.append(event)
            return None

        emitter_cls = type("Emitter", (Organ,), {"listens_to": ["START"], "handle": emitter_handle})
        receiver_cls = type(
            "Receiver", (Organ,), {"listens_to": ["EMITTED"], "handle": receiver_handle}
        )

        backend = StoppingBackend(spine_ref, max_events=20)
        spine = Spine(organs=[emitter_cls(), receiver_cls()], backend=backend, max_steps=20)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="START", payload={}))

        assert len(received) == num_events
        assert [e.payload["i"] for e in received] == list(range(num_events))

    @pytest.mark.asyncio
    async def test_none_return_enqueues_nothing(self):
        """Spine SHALL NOT enqueue anything when handler returns None."""
        received = []
        spine_ref = [None]

        def none_handle(self, event):
            return None

        def receiver_handle(self, event):
            received.append(event)
            return None

        none_organ_cls = type(
            "NoneOrgan", (Organ,), {"listens_to": ["START"], "handle": none_handle}
        )
        receiver_cls = type(
            "Receiver", (Organ,), {"listens_to": ["NEVER"], "handle": receiver_handle}
        )

        backend = StoppingBackend(spine_ref, max_events=10)
        spine = Spine(organs=[none_organ_cls(), receiver_cls()], backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="START", payload={}))

        assert received == []


# =============================================================================
# Property 9: Organ Invocation Order
# **Feature: necrostack-framework, Property 9: Organ Invocation Order**
# **Validates: Requirements 3.6**
# =============================================================================


class TestOrganInvocationOrder:
    """Property 9: Organ Invocation Order tests."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "order",
        [
            ["A", "B", "C"],
            ["C", "B", "A"],
            ["B", "A", "C"],
            ["A", "B", "C", "D", "E"],
        ],
    )
    async def test_invocation_matches_registration_order(self, order):
        """Spine SHALL invoke organs in registration order."""
        invocations = []
        spine_ref = [None]

        organs = []
        for name in order:

            def make_handle(n):
                def handle(self, event):
                    invocations.append(n)
                    return None

                return handle

            organ_class = type(
                f"Organ{name}",
                (Organ,),
                {
                    "listens_to": ["TEST"],
                    "handle": make_handle(name),
                },
            )
            organs.append(organ_class())

        backend = StoppingBackend(spine_ref, max_events=10)
        spine = Spine(organs=organs, backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="TEST", payload={}))

        assert invocations == order


# =============================================================================
# Property 10: Max Steps Enforcement
# **Feature: necrostack-framework, Property 10: Max Steps Enforcement**
# **Validates: Requirements 3.7**
# =============================================================================


class TestMaxStepsEnforcement:
    """Property 10: Max Steps Enforcement tests."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("max_steps", [1, 2, 5, 10])
    async def test_raises_runtime_error_when_exceeded(self, max_steps):
        """Spine SHALL raise RuntimeError when max_steps exceeded."""
        spine_ref = [None]

        def infinite_handle(self, event):
            return Event(event_type="LOOP", payload={})

        infinite_organ_cls = type(
            "InfiniteOrgan",
            (Organ,),
            {
                "listens_to": ["LOOP", "START"],
                "handle": infinite_handle,
            },
        )

        backend = StoppingBackend(spine_ref, max_events=1000)
        spine = Spine(organs=[infinite_organ_cls()], backend=backend, max_steps=max_steps)
        spine_ref[0] = spine

        with pytest.raises(RuntimeError) as exc_info:
            await spine.run(start_event=Event(event_type="START", payload={}))

        assert "Max steps exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_error_when_under_limit(self):
        """Spine SHALL NOT raise RuntimeError when under max_steps."""
        processed = [0]
        spine_ref = [None]

        def chain_handle(self, event):
            processed[0] += 1
            if processed[0] >= 3:
                return None
            return Event(event_type="CHAIN", payload={})

        chain_organ_cls = type(
            "ChainOrgan",
            (Organ,),
            {
                "listens_to": ["START", "CHAIN"],
                "handle": chain_handle,
            },
        )

        backend = StoppingBackend(spine_ref, max_events=50)
        spine = Spine(organs=[chain_organ_cls()], backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="START", payload={}))

        assert processed[0] == 3


# =============================================================================
# Property 13: Sync and Async Handler Support
# **Feature: necrostack-framework, Property 13: Sync and Async Handler Support**
# **Validates: Requirements 3.4**
# =============================================================================


class TestSyncAsyncHandlerSupport:
    """Property 13: Sync and Async Handler Support tests."""

    @pytest.mark.asyncio
    async def test_mixed_sync_async_handlers(self):
        """Spine SHALL correctly invoke both sync and async handlers."""
        invocations = []
        spine_ref = [None]

        def sync_handle(self, event):
            invocations.append(("sync", self.name))
            return None

        async def async_handle(self, event):
            invocations.append(("async", self.name))
            return None

        sync_organ_cls = type(
            "SyncOrgan", (Organ,), {"listens_to": ["TEST"], "handle": sync_handle}
        )
        async_organ_cls = type(
            "AsyncOrgan", (Organ,), {"listens_to": ["TEST"], "handle": async_handle}
        )

        backend = StoppingBackend(spine_ref, max_events=10)
        spine = Spine(organs=[sync_organ_cls(), async_organ_cls()], backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="TEST", payload={}))

        assert invocations == [("sync", "SyncOrgan"), ("async", "AsyncOrgan")]

    @pytest.mark.asyncio
    async def test_async_handler_can_emit(self):
        """Async handlers SHALL be able to return Events."""
        received = []
        spine_ref = [None]

        async def async_emit(self, event):
            return Event(event_type="ASYNC_OUT", payload={})

        def receiver(self, event):
            received.append(event)
            return None

        async_emitter_cls = type(
            "AsyncEmitter", (Organ,), {"listens_to": ["START"], "handle": async_emit}
        )
        receiver_cls = type("Receiver", (Organ,), {"listens_to": ["ASYNC_OUT"], "handle": receiver})

        backend = StoppingBackend(spine_ref, max_events=10)
        spine = Spine(organs=[async_emitter_cls(), receiver_cls()], backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="START", payload={}))

        assert len(received) == 1
        assert received[0].event_type == "ASYNC_OUT"

    @pytest.mark.asyncio
    async def test_sync_handler_can_emit(self):
        """Sync handlers SHALL be able to return Events."""
        received = []
        spine_ref = [None]

        def sync_emit(self, event):
            return Event(event_type="SYNC_OUT", payload={})

        def receiver(self, event):
            received.append(event)
            return None

        sync_emitter_cls = type(
            "SyncEmitter", (Organ,), {"listens_to": ["START"], "handle": sync_emit}
        )
        receiver_cls = type("Receiver", (Organ,), {"listens_to": ["SYNC_OUT"], "handle": receiver})

        backend = StoppingBackend(spine_ref, max_events=10)
        spine = Spine(organs=[sync_emitter_cls(), receiver_cls()], backend=backend, max_steps=10)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="START", payload={}))

        assert len(received) == 1
        assert received[0].event_type == "SYNC_OUT"


# =============================================================================
# Architecture Invariant: Spine Never Stores Events Internally
# **Supports: Architecture invariant from Design Document**
# =============================================================================


class TestSpineNoInternalQueue:
    """Architecture invariant: Spine never stores events internally."""

    def test_spine_has_no_queue_attributes(self):
        """Spine SHALL NOT have internal queue/buffer attributes."""
        spine_ref = [None]

        def handle(self, event):
            return None

        test_organ_cls = type("TestOrgan", (Organ,), {"listens_to": ["TEST"], "handle": handle})

        backend = StoppingBackend(spine_ref)
        spine = Spine(organs=[test_organ_cls()], backend=backend)

        suspicious = {"queue", "events", "buffer", "pending", "_queue", "_events", "_buffer"}

        for attr in dir(spine):
            if attr.startswith("__"):
                continue
            val = getattr(spine, attr, None)
            if isinstance(val, (list, deque, asyncio.Queue)):
                if attr == "organs":
                    continue
                if attr.lower() in suspicious:
                    pytest.fail(f"Spine has suspicious queue attribute: {attr}")

    @pytest.mark.asyncio
    async def test_spine_delegates_to_backend(self):
        """Spine SHALL delegate all queue operations to backend."""
        enqueue_calls = []
        pull_calls = []
        spine_ref = [None]

        class TrackingBackend:
            def __init__(self):
                self._queue = None
                self._pulls = 0

            def _get_queue(self):
                if self._queue is None:
                    self._queue = asyncio.Queue()
                return self._queue

            async def enqueue(self, event):
                enqueue_calls.append(event)
                await self._get_queue().put(event)

            async def pull(self, timeout=1.0):
                pull_calls.append(timeout)
                self._pulls += 1
                if self._pulls > 2:
                    if spine_ref[0]:
                        spine_ref[0].stop()
                    return None
                try:
                    return await asyncio.wait_for(self._get_queue().get(), timeout=0.01)
                except TimeoutError:
                    if spine_ref[0]:
                        spine_ref[0].stop()
                    return None

            async def ack(self, event):
                pass

        def handle(self, event):
            return Event(event_type="OUT", payload={})

        test_organ_cls = type("TestOrgan", (Organ,), {"listens_to": ["START"], "handle": handle})

        backend = TrackingBackend()
        spine = Spine(organs=[test_organ_cls()], backend=backend, max_steps=100)
        spine_ref[0] = spine

        await spine.run(start_event=Event(event_type="START", payload={}))

        assert len(enqueue_calls) >= 1
        assert enqueue_calls[0].event_type == "START"
        assert len(pull_calls) >= 1
