"""Push notification delivery organ."""

import asyncio
from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class PushOrgan(Organ):
    """Sends push notifications via simulated FCM/APNs.

    This is an ASYNC handler demonstrating:
    - Async I/O for external API calls
    - Reliable delivery (no simulated failures)
    - Payload transformation for push format

    Emits PUSH_DELIVERED on success.
    """

    listens_to = ["PUSH_SEND_REQUESTED"]

    async def handle(self, event: Event) -> Event:
        payload = event.payload

        # Validate required fields
        required_keys = ["device_token", "title", "body", "user_id", "priority"]
        missing = [k for k in required_keys if k not in payload]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        device_token = payload["device_token"]
        title = payload["title"]
        body = payload["body"]

        # Simulate FCM/APNs API call latency
        await asyncio.sleep(0.04)

        # Simulate push notification payload construction
        push_payload = {
            "to": device_token,
            "notification": {
                "title": title,
                "body": body,
            },
            "data": {
                "user_id": payload["user_id"],
                "priority": payload["priority"],
            },
        }

        # Simulate successful delivery
        return Event(
            event_type="PUSH_DELIVERED",
            payload={
                "user_id": payload["user_id"],
                "device_token": device_token,
                "push_payload_size": len(str(push_payload)),
                "delivered_at": datetime.now(UTC).isoformat(),
            },
        )
