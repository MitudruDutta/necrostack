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
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

from necrostack.core.event import Event

logger = logging.getLogger("necrostack.redis_backend")


def _sanitize_redis_url(url: str) -> str:
    """Sanitize a Redis URL by masking the password component.

    Args:
        url: Redis connection URL that may contain credentials.

    Returns:
        URL with password replaced by '****' or host:port if parsing fails.
    """
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Replace password with masked value
            netloc = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            sanitized = urlunparse(
                (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )
            return sanitized
        elif parsed.hostname:
            # No password, return host:port
            port = parsed.port or 6379
            return f"{parsed.hostname}:{port}"
        else:
            return "<invalid-url>"
    except Exception:
        return "<unparseable-url>"


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
            logger.debug(f"Connected to Redis at {_sanitize_redis_url(self.redis_url)}")

        # Test connection and reconnect if needed
        try:
            await self._redis.ping()
        except Exception:
            logger.warning("Redis connection lost, reconnecting...")
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info(f"Reconnected to Redis at {_sanitize_redis_url(self.redis_url)}")

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

        # Deserialize event from JSON
        try:
            event_dict = json.loads(raw_data["event"])
            # Parse ISO timestamp back to datetime
            event_dict["timestamp"] = datetime.fromisoformat(event_dict["timestamp"])
            event = Event(**event_dict)
            self._last_id = message_id
            logger.debug(f"Pulled event {event.id} from stream {self.stream_key}")
            return event
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to deserialize event from Redis: {e}")
            # Note: message_id not advanced - will retry same message
            # Consider implementing a skip mechanism or DLQ to avoid infinite loops
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

    async def get_client(self) -> Any:
        """Get the Redis client (public accessor).

        Returns:
            Connected Redis client instance.

        Raises:
            ImportError: If redis package is not installed.
        """
        return await self._get_client()

    async def delete_stream(self, stream_key: str | None = None) -> None:
        """Delete a Redis stream.

        Args:
            stream_key: The stream key to delete. Defaults to this backend's stream_key.

        Raises:
            Exception: If deletion fails (logged and re-raised).
        """
        key = stream_key or self.stream_key
        try:
            redis = await self._get_client()
            await redis.delete(key)
            logger.debug(f"Deleted stream {key}")
        except Exception as e:
            logger.error(f"Failed to delete stream {key}: {e}")
            raise

    async def close(self) -> None:
        """Close the Redis connection.

        Should be called when the backend is no longer needed.
        """
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.debug("Closed Redis connection")
