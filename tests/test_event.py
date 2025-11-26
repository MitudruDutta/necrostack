"""Property-based tests for Event model."""

from datetime import datetime
from uuid import UUID

import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from necrostack.core.event import Event
from tests.conftest import valid_event_data, valid_event_types, valid_payloads


# **Feature: necrostack-framework, Property 1: Event Serialization Round-Trip**
# **Validates: Requirements 1.4, 1.5**
@settings(max_examples=100)
@given(data=valid_event_data())
def test_event_serialization_round_trip(data: dict):
    """For any valid Event, serializing to JSON and deserializing should
    produce an equivalent Event (same id, timestamp, event_type, payload).
    """
    # Create original event
    original = Event(**data)
    
    # Serialize to JSON-compatible dict
    serialized = original.model_dump_jsonable()
    
    # Verify serialized format is JSON-compatible (strings for UUID/datetime)
    assert isinstance(serialized["id"], str)
    assert isinstance(serialized["timestamp"], str)
    
    # Deserialize back to Event
    restored = Event(
        id=UUID(serialized["id"]),
        timestamp=datetime.fromisoformat(serialized["timestamp"]),
        event_type=serialized["event_type"],
        payload=serialized["payload"],
    )
    
    # Verify equivalence
    assert restored.id == original.id
    assert restored.timestamp == original.timestamp
    assert restored.event_type == original.event_type
    assert restored.payload == original.payload


# **Feature: necrostack-framework, Property 2: Event Immutability and Auto-Fields**
# **Validates: Requirements 1.3**
@settings(max_examples=100)
@given(data=valid_event_data())
def test_event_immutability_and_auto_fields(data: dict):
    """For any valid Event created with user-provided payload data,
    the Event should have a non-None UUID id, non-None timestamp,
    and attempting to modify any field should raise an error.
    """
    event = Event(**data)
    
    # Verify auto-generated fields are present and valid
    assert event.id is not None
    assert isinstance(event.id, UUID)
    assert event.timestamp is not None
    assert isinstance(event.timestamp, datetime)
    
    # Verify immutability - attempting to modify should raise ValidationError
    with pytest.raises(ValidationError):
        event.event_type = "modified.type"
    
    with pytest.raises(ValidationError):
        event.payload = {"modified": True}
    
    with pytest.raises(ValidationError):
        event.id = UUID("00000000-0000-0000-0000-000000000000")
    
    with pytest.raises(ValidationError):
        event.timestamp = datetime.now()


# **Feature: necrostack-framework, Property 3: Invalid Event Rejection**
# **Validates: Requirements 1.2**
@settings(max_examples=100)
@given(payload=valid_payloads())
def test_invalid_event_rejection_missing_event_type(payload: dict):
    """For any Event instantiation with missing required field (event_type),
    a Pydantic ValidationError should be raised.
    """
    with pytest.raises(ValidationError) as exc_info:
        Event(payload=payload)  # Missing required event_type
    
    # Verify the error mentions the missing field
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("event_type",) for e in errors)


def test_invalid_event_rejection_wrong_type():
    """Event instantiation with wrong type for event_type should raise ValidationError."""
    with pytest.raises(ValidationError):
        Event(event_type=123)  # Should be string, not int


def test_invalid_event_rejection_wrong_payload_type():
    """Event instantiation with wrong type for payload should raise ValidationError."""
    with pytest.raises(ValidationError):
        Event(event_type="test.event", payload="not a dict")
