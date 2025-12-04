"""Router organ that fans out to delivery channels."""

from necrostack.core.event import Event
from necrostack.core.organ import Organ

# Simulated user database
USER_CONTACTS = {
    "user_001": {
        "email": "alice@example.com",
        "phone": "+1555123001",
        "device_token": "fcm_token_alice_xyz",
    },
    "user_002": {
        "email": "bob@example.com",
        "phone": "+1555123002",
        "device_token": "fcm_token_bob_abc",
    },
    "user_003": {
        "email": "charlie@example.com",
        "phone": "+1555000000",  # This number will simulate permanent failure
        "device_token": "fcm_token_charlie_def",
    },
}


class RouterOrgan(Organ):
    """Routes validated notifications to appropriate delivery channels.

    Looks up user contact info and emits channel-specific events.
    Emits one event per requested channel.
    """

    listens_to = ["NOTIFICATION_VALIDATED"]

    def handle(self, event: Event) -> list[Event]:
        payload = event.payload

        # Validate required fields
        required_keys = {"user_id", "channels", "message", "priority"}
        missing = required_keys - payload.keys()
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")

        user_id = payload["user_id"]
        channels = payload["channels"]
        message = payload["message"] if isinstance(payload["message"], str) else ""
        priority = payload["priority"]
        priority_str = (str(priority) if priority is not None else "UNKNOWN").upper()

        # Look up user contacts
        contacts = USER_CONTACTS.get(user_id, {})
        events = []

        for channel in channels:
            if channel == "email" and contacts.get("email"):
                events.append(
                    Event(
                        event_type="EMAIL_SEND_REQUESTED",
                        payload={
                            "user_id": user_id,
                            "email": contacts["email"],
                            "subject": f"[{priority_str}] Notification",
                            "body": message,
                            "priority": priority,
                        },
                    )
                )

            elif channel == "sms" and contacts.get("phone"):
                events.append(
                    Event(
                        event_type="SMS_SEND_REQUESTED",
                        payload={
                            "user_id": user_id,
                            "phone": contacts["phone"],
                            "message": message[:160],  # SMS length limit
                            "priority": priority,
                        },
                    )
                )

            elif channel == "push" and contacts.get("device_token"):
                events.append(
                    Event(
                        event_type="PUSH_SEND_REQUESTED",
                        payload={
                            "user_id": user_id,
                            "device_token": contacts["device_token"],
                            "title": "New Notification",
                            "body": message[:256],  # Push body limit
                            "priority": priority,
                        },
                    )
                )

        return events
