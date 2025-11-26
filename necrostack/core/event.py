"""Event base class for NecroStack."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Base class for all events in NecroStack.
    
    Events are immutable, validated message objects with automatic
    ID and timestamp generation.
    """

    model_config = {"frozen": True}

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="String identifier used for routing")
    payload: dict[str, Any] = Field(default_factory=dict)

    def model_dump_jsonable(self) -> dict[str, Any]:
        """Return a JSON-serializable representation.
        
        Converts UUID to string and datetime to ISO format for JSON compatibility.
        """
        data = self.model_dump()
        data["id"] = str(self.id)
        data["timestamp"] = self.timestamp.isoformat()
        return data
