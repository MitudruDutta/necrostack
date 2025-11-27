"""Redis Streams backend for durable event queuing (MVP-lite).

This backend uses Redis Streams for persistent event storage with
automatic reconnection on connection failures.

MVP Limitations:
- No consumer group support (uses simple XREAD)
- ack() is a no-op (no message acknowledgment)
- No dead-letter queue
- No retry/backoff logic for failed handlers
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from necrostack.core.event import Event

logger = logging.getLogger("necrostack.redis_backend")


class RedisBackend:
    """Redis Streams backend for persistent event storage.

    Uses Redis Streams (XADD/XREAD) for durable FIFO event queuing.
    Automatically reconnects if the connection drops.

    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379")
        stream_key: Redis stream key name (default: "necrostack:events")
    """

    def __init__(self, redis_url: str, stream_key: str = "necrostack:events") -> None:
        """Initialize the Redis backend.

        Args:
            redis_url: Redis connection URL.
            stream_key: Redis stream key for storing events.
        """
        self.redis_url = redis_url
        self.stream_key = stream_key
        self._redis: Any = None  # Redis client, lazily initialized
        self._last_id = "0"  # Track last read message ID for XREAD

    async def _get_client(self) -> Any:
        """Get or create the Redis client with auto-reconnect.

        Returns:
            Connected Redis client instance.

        Raises:
            ImportError: If redis package is not installed.
        """
        try:
            from redis.asyncio import Redis
        except ImportError as e:
            raise ImportError(
                "redis package is required for RedisBackend. "
                "Install it with: pip install necrostack[redis]"
            ) from e

        if self._redis is None:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
            logger.debug(f"Connected to Redis at {self.redis_url}")

        # Test connection and reconnect if needed
        try:
            await self._redis.ping()
        except Exception as e:
            logger.warning(f"Redis connection lost, reconnecting: {e}")
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Reconnected to Redis")

        return self._redis

    async def enqueue(self, event: Event) -> None:
        """Store an event in the Redis stream using XADD.

        Serializes the event to JSON and adds it to the stream.

        Args:
            event: The Event to enqueue.
        """
        redis = await self._get_client()

        # Serialize event - handle datetime specially for JSON
        event_data = event.model_dump()
        event_data["timestamp"] = event_data["timestamp"].isoformat()

        await redis.xadd(self.stream_key, {"event": json.dumps(event_data)})
        logger.debug(f"Enqueued event {event.id} to stream {self.stream_key}")

    async def pull(self, timeout: float = 1.0) -> Event | None:
        """Retrieve the next event from the Redis stream using XREAD.

        Blocks up to timeout seconds waiting for an event.

        Args:
            timeout: Maximum seconds to wait for an event.

        Returns:
            The next Event, or None if timeout expires with no event.
        """
        redis = await self._get_client()

        # XREAD with blocking timeout (in milliseconds)
        block_ms = int(timeout * 1000)
        try:
            response = await redis.xread(
                streams={self.stream_key: self._last_id},
                count=1,
                block=block_ms,
            )
        except Exception as e:
            logger.error(f"Error reading from Redis stream: {e}")
            # Try to reconnect on next call
            self._redis = None
            return None

        if not response:
            return None

        # Parse response: [[stream_key, [(message_id, {field: value})]]]
        _, messages = response[0]
        message_id, raw_data = messages[0]
        self._last_id = message_id

        # Deserialize event from JSON
        try:
            event_dict = json.loads(raw_data["event"])
            # Parse ISO timestamp back to datetime
            event_dict["timestamp"] = datetime.fromisoformat(event_dict["timestamp"])
            event = Event(**event_dict)
            logger.debug(f"Pulled event {event.id} from stream {self.stream_key}")
            return event
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to deserialize event from Redis: {e}")
            return None

    async def ack(self, event: Event) -> None:
        """Acknowledge event processing (no-op in MVP).

        In MVP, this is a no-op. Phase 2 will add consumer group
        support with proper XACK acknowledgment.

        Args:
            event: The Event to acknowledge.
        """
        # No-op in MVP - Phase 2 will implement consumer groups
        pass

    async def close(self) -> None:
        """Close the Redis connection.

        Should be called when the backend is no longer needed.
        """
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.debug("Closed Redis connection")
