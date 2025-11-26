"""Shared fixtures and Hypothesis strategies for NecroStack tests."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from hypothesis import strategies as st


# --- Hypothesis Strategies for Event Generation ---

def valid_uuids():
    """Generate valid UUIDs."""
    return st.builds(lambda: uuid4())


def valid_timestamps():
    """Generate valid datetime timestamps."""
    return st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
    )


@st.composite
def valid_event_types(draw: st.DrawFn) -> str:
    """Generate valid event type strings."""
    prefix = draw(st.sampled_from(["user", "order", "payment", "system", "notification"]))
    action = draw(st.sampled_from(["created", "updated", "deleted", "processed", "failed"]))
    return f"{prefix}.{action}"


@st.composite
def simple_json_values(draw: st.DrawFn) -> Any:
    """Generate simple JSON-compatible values."""
    return draw(st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-1_000_000, max_value=1_000_000),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
        st.text(min_size=0, max_size=100, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            blacklist_characters="\x00"
        )),
    ))


@st.composite
def valid_payloads(draw: st.DrawFn) -> dict[str, Any]:
    """Generate valid payload dictionaries."""
    keys = draw(st.lists(
        st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        min_size=0,
        max_size=5,
        unique=True
    ))
    values = draw(st.lists(simple_json_values(), min_size=len(keys), max_size=len(keys)))
    return dict(zip(keys, values))


@st.composite
def valid_event_data(draw: st.DrawFn) -> dict[str, Any]:
    """Generate valid data for Event instantiation."""
    return {
        "event_type": draw(valid_event_types()),
        "payload": draw(valid_payloads()),
    }


# --- Pytest Fixtures ---

@pytest.fixture
def sample_event_type() -> str:
    """Provide a sample event type for testing."""
    return "test.event"


@pytest.fixture
def sample_payload() -> dict[str, Any]:
    """Provide a sample payload for testing."""
    return {"key": "value", "count": 42}
