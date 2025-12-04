"""Audit organ for tracking delivery completions."""

from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ


class AuditOrgan(Organ):
    """Records delivery completions for audit trail.

    Listens to all delivery completion events and logs them.
    This demonstrates an organ that listens to multiple event types.

    Emits DELIVERY_COMPLETED for each successful delivery.
    """

    listens_to = ["EMAIL_DELIVERED", "SMS_DELIVERED", "PUSH_DELIVERED"]

    def __init__(self) -> None:
        super().__init__()
        # Instance-level state - not shared across instances
        self.audit_log: list[dict] = []

    def handle(self, event: Event) -> Event:
        payload = event.payload
        user_id = payload.get("user_id")
        if user_id is None:
            raise ValueError("Missing required field: user_id")

        # Determine channel from event type
        channel_map = {
            "EMAIL_DELIVERED": "email",
            "SMS_DELIVERED": "sms",
            "PUSH_DELIVERED": "push",
        }
        channel = channel_map.get(event.event_type, "unknown")

        # Build audit record
        audit_record = {
            "user_id": user_id,
            "channel": channel,
            "event_id": event.id,
            "delivered_at": payload.get("delivered_at"),
            "recorded_at": datetime.now(UTC).isoformat(),
        }

        # Store in instance state
        self.audit_log.append(audit_record)

        return Event(
            event_type="DELIVERY_COMPLETED",
            payload={
                "user_id": user_id,
                "channel": channel,
                "status": "delivered",
                "audit_id": f"audit_{event.id[:8]}",
            },
        )
