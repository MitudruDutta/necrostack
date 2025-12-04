"""SMS delivery organ with permanent failure simulation."""

import time
from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ

# Phone numbers that will permanently fail (invalid/blocked)
BLOCKED_NUMBERS = {"+1555000000", "+1555000001"}


class SmsOrgan(Organ):
    """Sends SMS via simulated gateway.

    This is a SYNC handler demonstrating:
    - Synchronous processing
    - Permanent failure detection (blocked numbers)
    - Events that should go to DLQ after retry exhaustion

    Emits SMS_DELIVERED on success.
    Raises exception for blocked numbers (will exhaust retries → DLQ).
    """

    listens_to = ["SMS_SEND_REQUESTED"]

    def handle(self, event: Event) -> Event:
        payload = event.payload

        # Validate required fields
        required_fields = ["phone", "message", "user_id"]
        missing = [f for f in required_fields if f not in payload]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        phone = payload["phone"]
        message = payload["message"]

        # Simulate API latency
        time.sleep(0.03)

        # Check for blocked/invalid numbers - these will NEVER succeed
        # After retry exhaustion, they go to DLQ
        if phone in BLOCKED_NUMBERS:
            raise ValueError("SMS delivery permanently failed: recipient is blocked")

        # Simulate successful delivery
        return Event(
            event_type="SMS_DELIVERED",
            payload={
                "user_id": payload["user_id"],
                "phone": phone,
                "message_length": len(message),
                "delivered_at": datetime.now(UTC).isoformat(),
            },
        )
