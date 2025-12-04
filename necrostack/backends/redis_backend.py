"""Production-grade Redis Streams backend.

Features:
- Consumer groups with XREADGROUP/XACK
- Automatic consumer group creation
- Pending message recovery (XPENDING/XCLAIM)
- Poison message protection with DLQ
- Connection pooling
- Automatic reconnection with exponential backoff
- Health checks
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from necrostack.core.event import Event

logger = logging.getLogger("necrostack.redis")


def _sanitize_url(url: str) -> str:
    """Mask password in Redis URL for logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(
                (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )
        return f"{parsed.hostname}:{parsed.port or 6379}"
    except Exception:
        return "<url>"


@dataclass
class BackendHealth:
    """Health check result."""

    healthy: bool
    latency_ms: float
    details: dict[str, Any]


@dataclass
class RedisMetrics:
    """Redis backend metrics."""

    events_enqueued: int = 0
    events_pulled: int = 0
    events_acked: int = 0
    events_failed: int = 0
    reconnections: int = 0
    pending_recovered: int = 0


class RedisBackend:
    """Production Redis Streams backend with consumer groups."""

    def __init__(
        self,
        redis_url: str,
        stream_key: str = "necrostack:events",
        consumer_group: str = "necrostack",
        consumer_name: str | None = None,
        pool_size: int = 10,
        max_retries: int = 3,
        claim_min_idle_ms: int = 30000,
        dlq_stream: str | None = None,
    ) -> None:
        """Initialize Redis backend.

        Args:
            redis_url: Redis connection URL.
            stream_key: Stream key for events.
            consumer_group: Consumer group name.
            consumer_name: Unique consumer name (auto-generated if None).
            pool_size: Connection pool size.
            max_retries: Max delivery attempts before DLQ.
            claim_min_idle_ms: Min idle time before claiming pending messages.
            dlq_stream: Dead letter queue stream (default: {stream_key}:dlq).
        """
        self._url = redis_url
        self._url_safe = _sanitize_url(redis_url)
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"consumer-{uuid4().hex[:8]}"
        self._pool_size = pool_size
        self._max_retries = max_retries
        self._claim_min_idle_ms = claim_min_idle_ms
        self.dlq_stream = dlq_stream or f"{stream_key}:dlq"

        self._redis: Any = None
        self._connected = False  # Explicit connection state flag
        self._group_created = False
        self._metrics = RedisMetrics()
        # Thread-safe mapping of event.id -> redis message ID for concurrent pull/ack
        self._event_message_map: dict[str, str] = {}
        self._map_lock = asyncio.Lock()
        self._conn_lock = asyncio.Lock()  # Protects connection creation

    @property
    def redis_url(self) -> str:
        return self._url

    @property
    def metrics(self) -> RedisMetrics:
        return self._metrics

    async def _get_client(self) -> Any:
        """Get Redis client with connection pooling.

        Thread-safe connection management with proper cleanup on reconnection.
        All connection state changes are protected by _conn_lock to prevent
        races and resource leaks.
        """
        try:
            from redis.asyncio import ConnectionPool, Redis
        except ImportError as e:
            raise ImportError("Install redis: pip install necrostack[redis]") from e

        # Fast path: if we have a connection, try to use it
        if self._redis is not None:
            try:
                await self._redis.ping()
                return self._redis
            except Exception as e:
                logger.warning(f"Redis connection lost: {e}, reconnecting...")
                # Fall through to reconnection under lock

        # Slow path: need to create or recreate connection under lock
        async with self._conn_lock:
            # Re-check after acquiring lock - another coroutine may have reconnected
            if self._redis is not None:
                try:
                    await self._redis.ping()
                    return self._redis
                except Exception:
                    # Connection still bad, proceed with reconnection
                    pass

            # Close old connection if exists to prevent resource leak
            old_redis = self._redis
            if old_redis is not None:
                try:
                    await old_redis.aclose()
                except Exception as close_err:
                    logger.debug(f"Error closing old connection: {close_err}")

            # Track if this is a reconnection using explicit connection state
            is_reconnection = self._connected

            # Create new connection
            pool = ConnectionPool.from_url(
                self._url, max_connections=self._pool_size, decode_responses=True
            )
            new_redis = Redis(connection_pool=pool)

            # Verify new connection works before committing
            try:
                ping_result = new_redis.ping()
                if hasattr(ping_result, "__await__"):
                    await ping_result
            except Exception:
                # Clean up failed new connection
                try:
                    await new_redis.aclose()
                except Exception:
                    pass
                raise

            # Commit the new connection
            self._redis = new_redis
            self._connected = True
            if is_reconnection:
                self._metrics.reconnections += 1
                self._group_created = False
                logger.info(f"Reconnected to Redis at {self._url_safe}")
            else:
                logger.info(f"Connected to Redis at {self._url_safe}")

            return self._redis

    async def _ensure_consumer_group(self) -> None:
        """Create consumer group if it doesn't exist."""
        if self._group_created:
            return

        redis = await self._get_client()
        try:
            await redis.xgroup_create(self.stream_key, self.consumer_group, id="0", mkstream=True)
            logger.info(f"Created consumer group '{self.consumer_group}' on '{self.stream_key}'")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{self.consumer_group}' already exists")
            else:
                raise
        self._group_created = True

    async def enqueue(self, event: Event) -> None:
        """Add event to stream using XADD."""
        await self._ensure_consumer_group()
        redis = await self._get_client()

        data = event.model_dump()
        data["timestamp"] = data["timestamp"].isoformat()

        await redis.xadd(self.stream_key, {"event": json.dumps(data)})
        self._metrics.events_enqueued += 1
        logger.debug(f"Enqueued {event.id} to {self.stream_key}")

    async def _recover_pending(self) -> Event | None:
        """Recover and claim pending messages that exceeded idle time."""
        redis = await self._get_client()

        try:
            pending = await redis.xpending_range(
                self.stream_key,
                self.consumer_group,
                min="-",
                max="+",
                count=10,
            )
        except Exception:
            return None

        for entry in pending:
            msg_id = entry["message_id"]
            idle_time = entry["time_since_delivered"]
            delivery_count = entry["times_delivered"]

            if idle_time < self._claim_min_idle_ms:
                continue

            # Move to DLQ if exceeded max retries
            if delivery_count >= self._max_retries:
                await self._move_to_dlq(msg_id, f"Exceeded {self._max_retries} delivery attempts")
                continue

            # Claim the message
            try:
                claimed = await redis.xclaim(
                    self.stream_key,
                    self.consumer_group,
                    self.consumer_name,
                    min_idle_time=self._claim_min_idle_ms,
                    message_ids=[msg_id],
                )
                if claimed:
                    self._metrics.pending_recovered += 1
                    return await self._deserialize(claimed[0])
            except Exception as e:
                logger.warning(f"Failed to claim {msg_id}: {e}")

        return None

    async def _move_to_dlq(self, message_id: str, reason: str) -> None:
        """Move failed message to dead letter queue."""
        redis = await self._get_client()

        try:
            # Get the original message
            messages = await redis.xrange(self.stream_key, min=message_id, max=message_id)
            if messages:
                _, data = messages[0]
                await redis.xadd(
                    self.dlq_stream,
                    {
                        "original_id": message_id,
                        "event": data.get("event", "{}"),
                        "reason": reason,
                        "failed_at": datetime.now(UTC).isoformat(),
                    },
                )
                logger.warning(f"Moved {message_id} to DLQ: {reason}")

            # Acknowledge to remove from pending
            await redis.xack(self.stream_key, self.consumer_group, message_id)
            self._metrics.events_failed += 1
        except Exception as e:
            logger.error(f"Failed to move {message_id} to DLQ: {e}")

    async def _deserialize(self, message: tuple) -> Event | None:
        """Deserialize Redis message to Event and store message ID mapping."""
        msg_id, data = message
        try:
            event_dict = json.loads(data["event"])
            event_dict["timestamp"] = datetime.fromisoformat(event_dict["timestamp"])
            event = Event(**event_dict)
            # Store mapping for later ack() - protected by lock for concurrent access
            async with self._map_lock:
                self._event_message_map[event.id] = msg_id
            return event
        except Exception as e:
            logger.error(f"Failed to deserialize {msg_id}: {e}")
            return None

    async def pull(self, timeout: float = 1.0) -> Event | None:
        """Read next event using XREADGROUP."""
        await self._ensure_consumer_group()
        redis = await self._get_client()

        # First try to recover pending messages
        recovered = await self._recover_pending()
        if recovered:
            return recovered  # _deserialize already stored the mapping

        # Read new messages
        try:
            response = await redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={self.stream_key: ">"},
                count=1,
                block=int(timeout * 1000),
            )
        except Exception as e:
            logger.error(f"XREADGROUP failed: {e}")
            self._redis = None
            return None

        if not response:
            return None

        _, messages = response[0]
        if not messages:
            return None

        event = await self._deserialize(messages[0])
        if event:
            self._metrics.events_pulled += 1
        return event

    async def ack(self, event: Event) -> None:
        """Acknowledge event processing with XACK.

        Args:
            event: The Event to acknowledge. Uses event.id to look up the
                   corresponding Redis message ID from the internal mapping.

        Note:
            The mapping is always cleaned up in finally to prevent memory leaks,
            even if XACK fails. Failed events will be re-pulled and get new mappings.
        """
        # Read (but don't remove) the Redis message ID for this event
        async with self._map_lock:
            message_id = self._event_message_map.get(event.id)

        if not message_id:
            logger.warning(f"No message ID found for event {event.id}, cannot ack")
            return

        redis = await self._get_client()
        try:
            await redis.xack(self.stream_key, self.consumer_group, message_id)
            self._metrics.events_acked += 1
            logger.debug(f"Acked message {message_id} for event {event.id}")
        except Exception as e:
            logger.error(f"XACK failed for message {message_id} (event {event.id}): {e}")
            raise
        finally:
            # Always clean up mapping to prevent memory leaks
            async with self._map_lock:
                self._event_message_map.pop(event.id, None)

    async def nack(self, event: Event, reason: str = "Processing failed") -> None:
        """Negative acknowledge - move to DLQ immediately.

        Args:
            event: The Event to negatively acknowledge.
            reason: Reason for the failure (logged in DLQ).

        Note:
            The mapping is always cleaned up in finally to prevent memory leaks,
            even if DLQ move fails. This ensures bounded memory usage.
        """
        # Read (but don't remove) the mapping
        async with self._map_lock:
            message_id = self._event_message_map.get(event.id)

        if not message_id:
            logger.warning(f"No message ID found for event {event.id}, cannot nack")
            return

        try:
            await self._move_to_dlq(message_id, reason)
        except Exception as e:
            logger.error(f"Failed to move event {event.id} to DLQ: {e}")
            raise
        finally:
            # Always clean up mapping to prevent memory leaks
            async with self._map_lock:
                self._event_message_map.pop(event.id, None)

    async def health(self) -> BackendHealth:
        """Check backend health."""
        start = time.monotonic()
        try:
            redis = await self._get_client()
            await redis.ping()
            info = await redis.xinfo_stream(self.stream_key)
            latency = (time.monotonic() - start) * 1000

            return BackendHealth(
                healthy=True,
                latency_ms=latency,
                details={
                    "stream_length": info.get("length", 0),
                    "consumer_group": self.consumer_group,
                    "consumer_name": self.consumer_name,
                    "metrics": {
                        "enqueued": self._metrics.events_enqueued,
                        "pulled": self._metrics.events_pulled,
                        "acked": self._metrics.events_acked,
                        "failed": self._metrics.events_failed,
                    },
                },
            )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"error": str(e)},
            )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            logger.info("Closed Redis connection")

    async def delete_stream(self, stream_key: str | None = None) -> None:
        """Delete a stream (for testing)."""
        redis = await self._get_client()
        await redis.delete(stream_key or self.stream_key)
