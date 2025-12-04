"""Event model for NecroStack."""

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# UUID v4 regex pattern for validation
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Maximum payload size (1MB)
MAX_PAYLOAD_SIZE = 1_000_000


class Event(BaseModel):
    """Immutable, validated event message.

    Events are the fundamental unit of communication in NecroStack. They are:
    - Immutable (frozen after creation)
    - Validated (all fields checked on construction)
    - Serializable (JSON-compatible via model_dump())

    Attributes:
        id: UUID v4 string, auto-generated if not provided.
        timestamp: UTC datetime, auto-generated if not provided.
        event_type: Non-empty string identifier for routing.
        payload: JSON-serializable dictionary (max 1MB when serialized).
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid",
        "frozen": True,
    }

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Ensure id is a valid UUID v4 string."""
        if not _UUID_PATTERN.match(v):
            raise ValueError(f"id must be a valid UUID v4 string, got: {v!r}")
        return v.lower()  # Normalize to lowercase

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Ensure event_type is non-empty after whitespace stripping."""
        v = v.strip()
        if not v:
            raise ValueError("event_type must not be empty")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Ensure payload is strictly JSON-serializable and within size limits.

        Raises TypeError/ValueError for non-JSON-serializable types (no default=str
        fallback) to enforce strict JSON compatibility.
        """
        try:
            serialized = json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"payload must be JSON-serializable: {e}") from e

        # Measure actual byte length for UTF-8 encoded payload
        byte_length = len(serialized.encode("utf-8"))
        if byte_length > MAX_PAYLOAD_SIZE:
            raise ValueError(
                f"payload exceeds maximum size of {MAX_PAYLOAD_SIZE} bytes "
                f"(got {byte_length} bytes)"
            )
        return v
