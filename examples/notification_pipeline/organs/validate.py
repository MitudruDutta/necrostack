"""Validation organ for notification requests."""

from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ

VALID_CHANNELS = {"email", "sms", "push"}
VALID_PRIORITIES = {"low", "normal", "high", "critical"}


class ValidateOrgan(Organ):
    """Validates incoming notification requests.

    Checks:
    - user_id is present and non-empty
    - channels is a non-empty list of valid channels
    - message is present and non-empty
    - priority is valid (defaults to 'normal' if missing)

    Emits:
    - NOTIFICATION_VALIDATED on success
    - NOTIFICATION_FAILED on validation failure
    """

    listens_to = ["NOTIFICATION_REQUESTED"]

    def handle(self, event: Event) -> Event:
        payload = event.payload
        errors = []

        # Validate user_id
        user_id = (payload.get("user_id") or "").strip()
        if not user_id:
            errors.append("user_id is required")

        # Validate channels
        channels = payload.get("channels", [])
        if not channels:
            errors.append("at least one channel is required")
        else:
            invalid_channels = set(channels) - VALID_CHANNELS
            if invalid_channels:
                errors.append(f"invalid channels: {invalid_channels}")

        # Validate message
        message = (payload.get("message") or "").strip()
        if not message:
            errors.append("message is required")

        # Validate priority (optional, default to 'normal')
        priority = payload.get("priority", "normal")
        if priority not in VALID_PRIORITIES:
            errors.append(f"invalid priority: {priority}")

        if errors:
            return Event(
                event_type="NOTIFICATION_FAILED",
                payload={
                    "user_id": user_id or "unknown",
                    "reason": "; ".join(errors),
                    "original_event_id": event.id,
                    "failed_at": datetime.now(UTC).isoformat(),
                },
            )

        return Event(
            event_type="NOTIFICATION_VALIDATED",
            payload={
                "user_id": user_id,
                "channels": channels,
                "message": message,
                "priority": priority,
                "validated_at": datetime.now(UTC).isoformat(),
            },
        )
