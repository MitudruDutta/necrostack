"""Email delivery organ with simulated transient failures."""

import asyncio
import random
from datetime import UTC, datetime

from cachetools import TTLCache

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class EmailOrgan(Organ):
    """Sends emails via simulated SMTP.

    This is an ASYNC handler demonstrating:
    - Async I/O operations
    - Transient failure simulation
    - The Spine's RETRY mode will handle retries automatically

    Emits EMAIL_DELIVERED on success.
    Raises exception on failure (Spine handles retry).
    """

    listens_to = ["EMAIL_SEND_REQUESTED"]

    def __init__(self, max_attempts: int = 3, ttl: float = 3600.0) -> None:
        super().__init__()
        # TTL-backed cache to prevent unbounded memory growth.
        # Default TTL of 1 hour is intentionally long to survive Spine's retry backoff
        # (e.g., 3 retries with exponential backoff: 0.1 + 0.2 + 0.4 = 0.7s typical,
        # but we use 1 hour to handle edge cases and slow backends).
        self._attempt_counts: TTLCache[str, int] = TTLCache(maxsize=10000, ttl=ttl)
        self._max_attempts = max_attempts

    async def handle(self, event: Event) -> Event:
        payload = event.payload

        # Validate required fields
        required_fields = ["email", "subject", "user_id"]
        missing = [f for f in required_fields if f not in payload]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        email = payload["email"]
        subject = payload["subject"]

        # Track retry attempts per event
        self._attempt_counts[event.id] = self._attempt_counts.get(event.id, 0) + 1
        attempt = self._attempt_counts[event.id]

        # Simulate network latency
        await asyncio.sleep(0.05)

        # Simulate 15% transient failure rate on first attempt
        # Success rate increases with retries (0% failure on second attempt per formula)
        failure_chance = max(0.0, 0.3 - (attempt * 0.15))
        if random.random() < failure_chance:
            # Clean up on final failure
            if attempt >= self._max_attempts:
                self._attempt_counts.pop(event.id, None)
            raise ConnectionError(f"SMTP connection failed for {email} (attempt {attempt})")

        # Simulate sending email
        await asyncio.sleep(0.02)

        # Clean up attempt tracking to prevent memory leak
        self._attempt_counts.pop(event.id, None)

        return Event(
            event_type="EMAIL_DELIVERED",
            payload={
                "user_id": payload["user_id"],
                "email": email,
                "subject": subject,
                "attempts": attempt,
                "delivered_at": datetime.now(UTC).isoformat(),
            },
        )
