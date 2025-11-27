"""Spine dispatcher for NecroStack."""

import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Sequence

from necrostack.backends.base import Backend
from necrostack.core.event import Event
from necrostack.core.organ import Organ


class Spine:
    """Central event dispatcher for NecroStack.
    
    The Spine routes events to registered Organs based on event type,
    manages the event processing loop, and handles handler invocation.
    
    Usage:
        spine = Spine(organs=[MyOrgan()], backend=InMemoryBackend())
        await spine.emit(Event(event_type="my.event"))
        await spine.run()
    """

    def __init__(
        self,
        organs: list[Organ],
        backend: Backend,
        max_steps: int | None = None,
    ) -> None:
        """Initialize the Spine dispatcher.
        
        Args:
            organs: List of Organ instances to register
            backend: Backend instance for event queue
            max_steps: Maximum number of event processing steps (default: 10_000)
            
        Raises:
            TypeError: If an Organ has an invalid handler signature
        """
        self.organs = organs
        self.backend = backend
        self.max_steps = max_steps if max_steps is not None else 10_000
        self._running = False
        self._stop_requested = False
        self.log = logging.getLogger("necrostack.spine")
        
        # Build routing table and validate organs
        self._routing_table: dict[str, list[Organ]] = defaultdict(list)
        for organ in organs:
            self._validate_organ(organ)
            for event_type in organ.listens_to:
                self._routing_table[event_type].append(organ)

    def _validate_organ(self, organ: Organ) -> None:
        """Validate that an Organ has a correct handler signature.
        
        Args:
            organ: The Organ to validate
            
        Raises:
            TypeError: If the handler signature is invalid
        """
        handler = organ.handle
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())
        
        # Filter out 'self' parameter for bound methods
        if params and params[0].name == "self":
            params = params[1:]
        
        # Handler must accept exactly one parameter (the event)
        required_params = [
            p for p in params
            if p.default is inspect.Parameter.empty
            and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]
        
        if len(required_params) != 1:
            raise TypeError(
                f"Organ {organ.__class__.__name__}.handle() must accept exactly one "
                f"required parameter (event), but has {len(required_params)} required parameters"
            )

    def get_organs_for_event(self, event_type: str) -> list[Organ]:
        """Get all organs that listen to a specific event type.
        
        Args:
            event_type: The event type to look up
            
        Returns:
            List of Organs that listen to this event type, in registration order
        """
        return self._routing_table.get(event_type, [])

    async def emit(self, event: Event) -> None:
        """Emit an event to the backend queue.
        
        Args:
            event: The event to emit
        """
        await self.backend.enqueue(event)

    async def _invoke_handler(
        self, organ: Organ, event: Event
    ) -> Event | Sequence[Event] | None:
        """Invoke an organ's handler, supporting both sync and async handlers.
        
        Args:
            organ: The organ whose handler to invoke
            event: The event to pass to the handler
            
        Returns:
            The handler's return value (Event, Sequence[Event], or None)
        """
        handler = organ.handle
        if inspect.iscoroutinefunction(handler):
            result = await handler(event)
        else:
            result = handler(event)
        return result

    async def _process_handler_result(
        self, result: Event | Sequence[Event] | None
    ) -> None:
        """Process the result of a handler invocation.
        
        Args:
            result: The handler's return value
        """
        if result is None:
            return
        
        if isinstance(result, Event):
            await self.backend.enqueue(result)
        elif isinstance(result, Sequence):
            for event in result:
                if isinstance(event, Event):
                    await self.backend.enqueue(event)

    async def _dispatch_event(self, event: Event) -> None:
        """Dispatch an event to all matching organs.
        
        Args:
            event: The event to dispatch
        """
        organs = self.get_organs_for_event(event.event_type)
        for organ in organs:
            try:
                result = await self._invoke_handler(organ, event)
                await self._process_handler_result(result)
            except Exception as e:
                self.log.error(
                    f"Handler {organ.__class__.__name__}.handle() raised exception "
                    f"for event {event.id} ({event.event_type}): {e}"
                )
                # Continue processing - don't let one handler failure stop others

    async def run(self) -> int:
        """Run the main event processing loop.
        
        Continuously pulls events from the backend and dispatches them
        to matching organs until stopped or max_steps is reached.
        
        Returns:
            Number of events processed
        """
        self._running = True
        self._stop_requested = False
        steps = 0
        
        while self._running and steps < self.max_steps:
            if self._stop_requested:
                break
            
            # Pull with a short timeout to allow checking stop flag
            event = await self.backend.pull(timeout=0.1)
            
            if event is None:
                # No event available, check if we should continue
                continue
            
            await self._dispatch_event(event)
            await self.backend.ack(event)
            steps += 1
        
        self._running = False
        return steps

    def stop(self) -> None:
        """Request graceful stop of the processing loop.
        
        The loop will finish processing the current event before stopping.
        """
        self._stop_requested = True

    async def run_until_empty(self, timeout: float = 1.0) -> int:
        """Run until the queue is empty or max_steps is reached.
        
        This is useful for testing - it processes all available events
        and returns when the queue is empty.
        
        Args:
            timeout: Timeout for each pull operation
            
        Returns:
            Number of events processed
        """
        self._running = True
        self._stop_requested = False
        steps = 0
        
        while self._running and steps < self.max_steps:
            if self._stop_requested:
                break
            
            event = await self.backend.pull(timeout=timeout)
            
            if event is None:
                # Queue is empty
                break
            
            await self._dispatch_event(event)
            await self.backend.ack(event)
            steps += 1
        
        self._running = False
        return steps
