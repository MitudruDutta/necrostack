"""Event model for NecroStack."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Event(BaseModel):
    """Immutable, validated event message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid",
        "frozen": True,
    }

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Ensure event_type is non-empty, not whitespace-only, and strip whitespace."""
        v = v.strip()
        if not v:
            raise ValueError("event_type must not be empty")
        return v
