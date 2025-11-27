"""Pytest configuration and Hypothesis profiles."""

import pytest
from hypothesis import settings

# Register Hypothesis profiles
settings.register_profile("ci", max_examples=100)
settings.register_profile("dev", max_examples=20)

# Load dev profile by default, CI can override via --hypothesis-profile=ci
settings.load_profile("dev")


@pytest.fixture
def anyio_backend():
    """Use asyncio as the async backend for pytest-asyncio."""
    return "asyncio"
