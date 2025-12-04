"""Property-based tests for Event model."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from necrostack.core.event import MAX_PAYLOAD_SIZE, Event

# Strategies for generating valid event data
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
    serialized = original.model_dump()
    reconstructed = Event(**serialized)

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
    each Event SHALL have a unique, valid UUID v4 string as its id field.
    """
    events = [Event(event_type="TEST_EVENT", payload={}) for _ in range(count)]
    ids = [e.id for e in events]

    assert len(ids) == len(set(ids)), "Event IDs must be unique"

    for event_id in ids:
        assert isinstance(event_id, str)
        assert len(event_id) == 36
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

    errors = exc_info.value.errors()
    assert any("event_type" in str(e) for e in errors)


# Strategy for generating unknown field names
unknown_field_name = st.sampled_from(
    ["extra_field", "unknown", "foo", "bar", "data", "meta", "custom", "value"]
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
    kwargs = {"event_type": event_type, "payload": {}, unknown_field: unknown_value}

    with pytest.raises(ValidationError) as exc_info:
        Event(**kwargs)

    error_str = str(exc_info.value)
    assert "extra" in error_str.lower() or unknown_field in error_str


# **Feature: necrostack-framework, Property 5: UUID Validation**
# **Validates: Requirements 1.2**
class TestUUIDValidation:
    """Tests for UUID v4 validation."""

    def test_valid_uuid_accepted(self):
        """Valid UUID v4 strings SHALL be accepted."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        event = Event(id=valid_uuid, event_type="TEST", payload={})
        assert event.id == valid_uuid.lower()

    def test_uuid_normalized_to_lowercase(self):
        """UUID strings SHALL be normalized to lowercase."""
        upper_uuid = "550E8400-E29B-41D4-A716-446655440000"
        event = Event(id=upper_uuid, event_type="TEST", payload={})
        assert event.id == upper_uuid.lower()

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "not-a-uuid",
            "550e8400-e29b-41d4-a716",  # Too short
            "550e8400-e29b-41d4-a716-446655440000-extra",  # Too long
            "550e8400e29b41d4a716446655440000",  # No hyphens
            "gggggggg-gggg-4ggg-8ggg-gggggggggggg",  # Invalid hex
            "",
            "   ",
        ],
    )
    def test_invalid_uuid_rejected(self, invalid_id: str):
        """Invalid UUID strings SHALL be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Event(id=invalid_id, event_type="TEST", payload={})
        assert "id" in str(exc_info.value).lower() or "uuid" in str(exc_info.value).lower()


# **Feature: necrostack-framework, Property 6: Payload Size Limit**
# **Validates: Security requirement for bounded payloads**
class TestPayloadValidation:
    """Tests for payload validation."""

    def test_valid_payload_accepted(self):
        """Valid JSON-serializable payloads SHALL be accepted."""
        payload = {"key": "value", "number": 42, "nested": {"a": 1}}
        event = Event(event_type="TEST", payload=payload)
        assert event.payload == payload

    def test_empty_payload_accepted(self):
        """Empty payloads SHALL be accepted."""
        event = Event(event_type="TEST", payload={})
        assert event.payload == {}

    def test_oversized_payload_rejected(self):
        """Payloads exceeding MAX_PAYLOAD_SIZE SHALL be rejected."""
        # Create a payload that exceeds 1MB
        large_payload = {"data": "x" * (MAX_PAYLOAD_SIZE + 1000)}

        with pytest.raises(ValidationError) as exc_info:
            Event(event_type="TEST", payload=large_payload)

        assert "payload" in str(exc_info.value).lower()
        assert "size" in str(exc_info.value).lower() or "bytes" in str(exc_info.value).lower()

    def test_payload_at_limit_accepted(self):
        """Payloads at or effectively at MAX_PAYLOAD_SIZE SHALL be accepted.

        Note: The test constructs a payload slightly under MAX_PAYLOAD_SIZE
        (leaving ~100 bytes for JSON structure/serialization overhead like
        braces and quotes) to verify that payloads near the limit are accepted.
        """
        # Create payload just under the limit (accounting for JSON overhead)
        data_size = MAX_PAYLOAD_SIZE - 100  # Leave room for JSON structure
        payload = {"d": "x" * data_size}

        # Should not raise
        event = Event(event_type="TEST", payload=payload)
        assert "d" in event.payload


# **Feature: necrostack-framework, Property 7: Event Immutability**
# **Validates: Requirements 1.1 (frozen model)**
class TestEventImmutability:
    """Tests for event immutability."""

    def test_cannot_modify_event_type(self):
        """Event fields SHALL NOT be modifiable after creation."""
        event = Event(event_type="ORIGINAL", payload={})

        with pytest.raises(ValidationError):
            event.event_type = "MODIFIED"

    def test_cannot_modify_payload(self):
        """Event payload SHALL NOT be reassignable after creation."""
        event = Event(event_type="TEST", payload={"key": "value"})

        with pytest.raises(ValidationError):
            event.payload = {"new": "payload"}

    def test_cannot_modify_id(self):
        """Event id SHALL NOT be modifiable after creation."""
        event = Event(event_type="TEST", payload={})

        with pytest.raises(ValidationError):
            event.id = "new-id"
