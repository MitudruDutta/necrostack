"""Property-based tests for Event model."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from necrostack.core.event import Event

# Strategies for generating valid event data - use from_regex for non-whitespace strings
valid_event_type = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]*", fullmatch=True)
valid_payload = st.fixed_dictionaries(
    {},
    optional={
        "key1": st.none() | st.booleans() | st.integers(),
        "key2": st.text(max_size=20),
        "count": st.integers(min_value=0, max_value=1000),
    },
)


# **Feature: necrostack-framework, Property 1: Event Serialization Round-Trip**
# **Validates: Requirements 1.6, 1.7**
@given(event_type=valid_event_type, payload=valid_payload)
@settings(max_examples=100)
def test_event_serialization_round_trip(event_type: str, payload: dict):
    """For any valid Event, serializing via model_dump() and reconstructing
    via Event(**data) SHALL produce an equivalent Event with identical field values.
    """
    original = Event(event_type=event_type, payload=payload)

    # Serialize to dict
    serialized = original.model_dump()

    # Reconstruct from dict
    reconstructed = Event(**serialized)

    # Verify all fields are identical
    assert reconstructed.id == original.id
    assert reconstructed.timestamp == original.timestamp
    assert reconstructed.event_type == original.event_type
    assert reconstructed.payload == original.payload
    assert reconstructed == original


# **Feature: necrostack-framework, Property 2: Event ID Uniqueness**
# **Validates: Requirements 1.2**
@given(count=st.integers(min_value=2, max_value=20))
@settings(max_examples=100)
def test_event_id_uniqueness(count: int):
    """For any collection of Events created without explicit IDs,
    each Event SHALL have a unique, valid UUID string as its id field.
    """
    # Create events without explicit IDs
    events = [Event(event_type="TEST_EVENT", payload={}) for _ in range(count)]

    # Collect all IDs
    ids = [e.id for e in events]

    # All IDs should be unique
    assert len(ids) == len(set(ids)), "Event IDs must be unique"

    # All IDs should be valid UUID strings (36 chars with hyphens)
    for event_id in ids:
        assert isinstance(event_id, str)
        assert len(event_id) == 36
        # UUID format: 8-4-4-4-12
        parts = event_id.split("-")
        assert len(parts) == 5
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


# **Feature: necrostack-framework, Property 3: Empty Event Type Rejection**
# **Validates: Requirements 1.4**
@given(whitespace=st.sampled_from(["", " ", "  ", "\t", "\n", "\r", "   \t\n", "\t\t\t"]))
@settings(max_examples=100)
def test_empty_event_type_rejection(whitespace: str):
    """For any string that is empty or consists only of whitespace characters,
    attempting to create an Event with that string as event_type SHALL raise
    a validation error.
    """
    with pytest.raises(ValidationError) as exc_info:
        Event(event_type=whitespace, payload={})

    # Verify the error is about event_type
    errors = exc_info.value.errors()
    assert any("event_type" in str(e) for e in errors)


# Strategy for generating unknown field names (avoiding known Event fields)
unknown_field_name = st.sampled_from(
    [
        "extra_field",
        "unknown",
        "foo",
        "bar",
        "data",
        "meta",
        "custom",
        "value",
        "info",
        "status",
        "result",
    ]
)


# **Feature: necrostack-framework, Property 4: Unknown Field Rejection**
# **Validates: Requirements 1.5**
@given(
    event_type=valid_event_type,
    unknown_field=unknown_field_name,
    unknown_value=st.text(max_size=20) | st.integers() | st.booleans(),
)
@settings(max_examples=100)
def test_unknown_field_rejection(event_type: str, unknown_field: str, unknown_value):
    """For any Event creation attempt that includes fields not defined in the
    Event schema, the creation SHALL raise a validation error.
    """
    # Build kwargs with an unknown field
    kwargs = {
        "event_type": event_type,
        "payload": {},
        unknown_field: unknown_value,
    }

    with pytest.raises(ValidationError) as exc_info:
        Event(**kwargs)

    # Verify the error mentions extra fields are forbidden
    error_str = str(exc_info.value)
    assert "extra" in error_str.lower() or unknown_field in error_str
