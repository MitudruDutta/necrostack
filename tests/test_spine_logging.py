"""Smoke tests for structured logging output shape in Spine.

Supports: Structured logging as defined in Design Document.
"""

import json
import logging
import pytest

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import Spine


class LogCapture(logging.Handler):
    """Custom handler to capture log records for testing."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def clear(self) -> None:
        self.records.clear()


class AsyncLoggingOrgan(Organ):
    """Async organ for testing structured logging during async dispatch."""

    listens_to = ["TEST_EVENT"]

    def __init__(self, spine_to_stop: Spine | None = None, name: str | None = None):
        super().__init__(name=name)
        self._spine_to_stop = spine_to_stop

    async def handle(self, event: Event) -> None:
        """Async handler that stops the spine after processing."""
        if self._spine_to_stop:
            self._spine_to_stop.stop()
        return None


class AsyncEmittingOrgan(Organ):
    """Async organ that emits a new event to test emitted logging."""

    listens_to = ["START_EVENT"]

    async def handle(self, event: Event) -> Event:
        """Async handler that emits a follow-up event."""
        return Event(event_type="FOLLOW_UP_EVENT", payload={"source": str(event.id)})


class StoppingOrgan(Organ):
    """Organ that stops the spine after handling."""

    listens_to = ["FOLLOW_UP_EVENT"]

    def __init__(self, spine_to_stop: Spine | None = None, name: str | None = None):
        super().__init__(name=name)
        self._spine_to_stop = spine_to_stop

    async def handle(self, event: Event) -> None:
        """Stop the spine after processing."""
        if self._spine_to_stop:
            self._spine_to_stop.stop()
        return None


@pytest.fixture
def log_capture():
    """Fixture to capture logs from necrostack.spine logger."""
    logger = logging.getLogger("necrostack.spine")
    handler = LogCapture()
    handler.setLevel(logging.DEBUG)
    
    # Store original handlers and level
    original_handlers = logger.handlers.copy()
    original_level = logger.level
    
    # Add our capture handler
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    yield handler
    
    # Restore original state
    logger.removeHandler(handler)
    logger.handlers = original_handlers
    logger.level = original_level


@pytest.mark.asyncio
async def test_structured_logging_contains_required_fields(log_capture):
    """Verify logs contain required fields (event_id, event_type, organ) for dispatch.
    
    This smoke test ensures:
    - Dispatching an event through Spine with an async handler produces structured logs
    - Logs contain the required fields: event_id, event_type, organ
    - Logger does not crash Spine during async await behavior
    """
    # Create backend
    backend = InMemoryBackend()
    
    # Create Spine first (we'll set the organ's spine reference after)
    organ = AsyncLoggingOrgan()
    spine = Spine(organs=[organ], backend=backend, max_steps=100)
    
    # Set the spine reference so organ can stop it
    organ._spine_to_stop = spine
    
    # Create test event
    test_event = Event(event_type="TEST_EVENT", payload={"test": "data"})
    
    # Run the spine with the start event
    await spine.run(start_event=test_event)
    
    # Find the dispatch log record
    dispatch_records = [
        r for r in log_capture.records 
        if "Dispatching" in r.getMessage()
    ]
    
    # Verify we got at least one dispatch log
    assert len(dispatch_records) >= 1, "Expected at least one dispatch log record"
    
    # Check the first dispatch record has required fields
    record = dispatch_records[0]
    
    # Verify required fields are present in the log record's extra data
    assert hasattr(record, "event_id"), "Log record missing 'event_id' field"
    assert hasattr(record, "event_type"), "Log record missing 'event_type' field"
    assert hasattr(record, "organ"), "Log record missing 'organ' field"
    
    # Verify field values are correct
    assert record.event_id == str(test_event.id), "event_id should match the dispatched event"
    assert record.event_type == "TEST_EVENT", "event_type should be TEST_EVENT"
    assert record.organ == "AsyncLoggingOrgan", "organ should be AsyncLoggingOrgan"


@pytest.mark.asyncio
async def test_structured_logging_json_format(log_capture):
    """Verify that the JSON formatter produces valid JSON with required fields.
    
    This test captures the formatted output and verifies it's valid JSON
    containing the required structured logging fields.
    """
    backend = InMemoryBackend()
    organ = AsyncLoggingOrgan()
    spine = Spine(organs=[organ], backend=backend, max_steps=100)
    organ._spine_to_stop = spine
    
    test_event = Event(event_type="TEST_EVENT", payload={"key": "value"})
    
    await spine.run(start_event=test_event)
    
    # Find dispatch records
    dispatch_records = [
        r for r in log_capture.records 
        if "Dispatching" in r.getMessage()
    ]
    
    assert len(dispatch_records) >= 1, "Expected at least one dispatch log"
    
    # Get the handler's formatter and format the record
    from necrostack.core.logging import JSONFormatter
    formatter = JSONFormatter()
    formatted = formatter.format(dispatch_records[0])
    
    # Verify it's valid JSON
    log_data = json.loads(formatted)
    
    # Verify required fields are in the JSON output
    assert "event_id" in log_data, "JSON log missing 'event_id'"
    assert "event_type" in log_data, "JSON log missing 'event_type'"
    assert "organ" in log_data, "JSON log missing 'organ'"
    assert "timestamp" in log_data, "JSON log missing 'timestamp'"
    assert "level" in log_data, "JSON log missing 'level'"
    
    # Verify values
    assert log_data["event_id"] == str(test_event.id)
    assert log_data["event_type"] == "TEST_EVENT"
    assert log_data["organ"] == "AsyncLoggingOrgan"
    assert log_data["level"] == "INFO"


@pytest.mark.asyncio
async def test_async_handler_does_not_crash_spine_logging(log_capture):
    """Verify logger does not crash Spine during async await behavior.
    
    This test ensures that logging works correctly when async handlers
    are being awaited, and that the Spine completes successfully.
    """
    backend = InMemoryBackend()
    
    # Create organs - emitting organ and stopping organ
    emitting_organ = AsyncEmittingOrgan()
    stopping_organ = StoppingOrgan()
    
    # Create spine with two organs - one emits, one receives and stops
    spine = Spine(
        organs=[emitting_organ, stopping_organ], 
        backend=backend, 
        max_steps=100
    )
    
    # Set the spine reference so stopping organ can stop it
    stopping_organ._spine_to_stop = spine
    
    start_event = Event(event_type="START_EVENT", payload={})
    
    # This should complete without crashing
    await spine.run(start_event=start_event)
    
    # Verify we got logs for both dispatches
    dispatch_records = [
        r for r in log_capture.records 
        if "Dispatching" in r.getMessage()
    ]
    
    # Should have at least 2 dispatch logs (START_EVENT and FOLLOW_UP_EVENT)
    assert len(dispatch_records) >= 2, (
        f"Expected at least 2 dispatch logs, got {len(dispatch_records)}"
    )
    
    # Verify both event types were logged
    event_types_logged = {r.event_type for r in dispatch_records}
    assert "START_EVENT" in event_types_logged, "START_EVENT should be logged"
    assert "FOLLOW_UP_EVENT" in event_types_logged, "FOLLOW_UP_EVENT should be logged"
    
    # Verify all records have required fields
    for record in dispatch_records:
        assert hasattr(record, "event_id"), f"Record missing event_id: {record}"
        assert hasattr(record, "event_type"), f"Record missing event_type: {record}"
        assert hasattr(record, "organ"), f"Record missing organ: {record}"
