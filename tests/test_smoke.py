"""Smoke test to verify testing infrastructure works."""

from hypothesis import given
from tests.conftest import valid_event_types, valid_payloads


def test_infrastructure_works():
    """Verify pytest is working."""
    assert True


@given(event_type=valid_event_types())
def test_event_type_strategy(event_type: str):
    """Verify Hypothesis event type strategy generates valid strings."""
    assert isinstance(event_type, str)
    assert "." in event_type


@given(payload=valid_payloads())
def test_payload_strategy(payload: dict):
    """Verify Hypothesis payload strategy generates valid dicts."""
    assert isinstance(payload, dict)
