"""Redis Streams backend for NecroStack."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from necrostack.core.event import Event

try:
    import redis.asyncio as redis
except ImportError as e:
    raise ImportError(
        "Redis backend requires the 'redis' package. "
        "Install it with: pip install necrostack[redis]"
    ) from e


class RedisBackend:
    """Redis Streams backend using XADD/XREAD.
    
    This backend provides durable event storage using Redis Streams.
    MVP implementation uses simple consumer (XREAD) without consumer groups.
    
    Args:
        url: Redis connection URL (default: redis://localhost:6379)
        stream_key: Name of the Redis stream (default: necrostack:events)
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        stream_key: str = "necrostack:events",
    ) -> None:
        """Initialize the Redis backend.
        
        Args:
            url: Redis connection URL
            stream_key: Name of the Redis stream to use
        """
        self._url = url
        self._stream_key = stream_key
        self._client: redis.Redis | None = None
        self._last_id = "0"  # Track last read ID for XREAD
        self._log = logging.getLogger("necrostack.backends.redis")

    async def _ensure_connected(self) -> redis.Redis:
        """Ensure Redis connection is established.
        
        Returns:
            Connected Redis client
        """
        if self._client is None:
            self._client = redis.from_url(self._url)
            self._log.debug("Connected to Redis at %s", self._url)
        return self._client

    async def enqueue(self, event: Event) -> None:
        """Add an event to the Redis stream using XADD.
        
        Args:
            event: The event to enqueue
        """
        client = await self._ensure_connected()
        event_data = event.model_dump_jsonable()
        await client.xadd(
            self._stream_key,
            {"event": json.dumps(event_data)},
        )
        self._log.debug("Enqueued event %s to stream %s", event.id, self._stream_key)

    async def pull(self, timeout: float | None = None) -> Event | None:
        """Retrieve the next event from the Redis stream using XREAD.
        
        Args:
            timeout: Maximum time to wait for an event in seconds.
                    None means wait indefinitely (blocking).
        
        Returns:
            The next event, or None if timeout is reached with no event available.
        """
        client = await self._ensure_connected()
        
        # Convert timeout to milliseconds for Redis (0 = block indefinitely)
        block_ms: int | None = None
        if timeout is not None:
            block_ms = int(timeout * 1000)
        else:
            block_ms = 0  # Block indefinitely
        
        result = await client.xread(
            {self._stream_key: self._last_id},
            count=1,
            block=block_ms,
        )
        
        if not result:
            return None
        
        # Result format: [[stream_name, [(message_id, {field: value})]]]
        stream_data = result[0]
        messages = stream_data[1]
        
        if not messages:
            return None
        
        message_id, fields = messages[0]
        self._last_id = message_id  # Update last read ID
        
        # Deserialize the event
        event_json = fields.get(b"event") or fields.get("event")
        if event_json is None:
            self._log.warning("Message %s has no event field", message_id)
            return None
        
        if isinstance(event_json, bytes):
            event_json = event_json.decode("utf-8")
        
        event_data = json.loads(event_json)
        return self._deserialize_event(event_data)

    def _deserialize_event(self, data: dict[str, Any]) -> Event:
        """Deserialize event data from JSON.
        
        Args:
            data: Dictionary containing event fields
            
        Returns:
            Reconstructed Event instance
        """
        # Convert string fields back to proper types
        if isinstance(data.get("id"), str):
            data["id"] = UUID(data["id"])
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        
        return Event(**data)

    async def ack(self, event: Event) -> None:
        """Acknowledge successful processing of an event.
        
        This is a no-op for MVP. Full consumer group support would use XACK.
        
        Args:
            event: The event to acknowledge
        """
        # No-op for MVP - full implementation would use XACK with consumer groups
        pass

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._log.debug("Closed Redis connection")
