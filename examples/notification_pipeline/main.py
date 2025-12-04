#!/usr/bin/env python3
"""
Notification Pipeline - NecroStack Demo Application

This demonstrates a production-style notification system using NecroStack's
real, implemented features:

- Event immutability and validation
- Multiple Organs in a pipeline
- Sync and async handlers
- Multi-event emission (fan-out)
- DLQ capture via InMemoryFailedEventStore
- Structured JSON logging

Run with: python main.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from organs.audit import AuditOrgan
from organs.email_sender import EmailOrgan
from organs.push_sender import PushOrgan
from organs.router import RouterOrgan
from organs.sms_sender import SmsOrgan
from organs.validate import ValidateOrgan

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.spine import (
    EnqueueFailureMode,
    HandlerFailureMode,
    InMemoryFailedEventStore,
    Spine,
)

# Configure logging to see structured output
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stderr,
)


class AutoStopBackend(InMemoryBackend):
    """Backend that stops the spine when queue is empty after processing starts.

    NOTE: This auto-stop mechanism has a potential race condition. If events are
    currently being processed by organs and are about to emit new events back to
    the queue, the backend might observe a temporarily empty queue and stop the
    spine prematurely. This is acceptable for demo purposes where we control the
    event flow, but production systems should use explicit stop signals or wait
    for a quiescence period before stopping.
    """

    def __init__(self, spine_holder: list):
        super().__init__()
        self._spine_holder = spine_holder
        self._has_processed = False

    async def pull(self, timeout: float = 1.0) -> Event | None:
        event = await super().pull(timeout)
        if event is not None:
            self._has_processed = True
        elif self._has_processed and self._spine_holder[0]:
            # Queue empty after processing - stop
            self._spine_holder[0].stop()
        return event


def create_test_notifications() -> list[Event]:
    """Create test notification requests with dynamic values."""
    import random
    from datetime import datetime

    # Generate dynamic values
    order_id = random.randint(10000, 99999)
    update_count = random.randint(1, 20)
    timestamp = datetime.now().strftime("%H:%M:%S")

    return [
        # Valid notification - all channels
        Event(
            event_type="NOTIFICATION_REQUESTED",
            payload={
                "user_id": "user_001",
                "channels": ["email", "sms", "push"],
                "message": f"Your order #{order_id} has shipped! [{timestamp}]",
                "priority": "high",
            },
        ),
        # Valid notification - email only
        Event(
            event_type="NOTIFICATION_REQUESTED",
            payload={
                "user_id": "user_002",
                "channels": ["email"],
                "message": f"Weekly digest: {update_count} new updates",
                "priority": "low",
            },
        ),
        # Valid notification - will fail SMS (blocked number)
        Event(
            event_type="NOTIFICATION_REQUESTED",
            payload={
                "user_id": "user_003",
                "channels": ["sms", "push"],
                "message": f"Security alert: New login detected at {timestamp}",
                "priority": "critical",
            },
        ),
        # Invalid notification - missing message
        Event(
            event_type="NOTIFICATION_REQUESTED",
            payload={
                "user_id": "user_001",
                "channels": ["email"],
                "message": "",  # Invalid: empty
                "priority": "normal",
            },
        ),
        # Invalid notification - bad channel
        Event(
            event_type="NOTIFICATION_REQUESTED",
            payload={
                "user_id": "user_002",
                "channels": ["telegram"],  # Invalid channel
                "message": "Test message",
                "priority": "normal",
            },
        ),
    ]


async def run_pipeline():
    """Run the notification pipeline."""
    print("=" * 70)
    print("NECROSTACK NOTIFICATION PIPELINE DEMO")
    print("=" * 70)
    print()

    # Create DLQ store
    failed_store = InMemoryFailedEventStore()

    # Create organ instances
    audit_organ = AuditOrgan()

    # Spine holder for auto-stop backend
    spine_holder: list = [None]
    backend = AutoStopBackend(spine_holder)

    # Create Spine with all organs
    spine = Spine(
        organs=[
            ValidateOrgan(),
            RouterOrgan(),
            EmailOrgan(),
            SmsOrgan(),
            PushOrgan(),
            audit_organ,
        ],
        backend=backend,
        max_steps=500,
        enqueue_failure_mode=EnqueueFailureMode.STORE,
        handler_failure_mode=HandlerFailureMode.STORE,  # Handler failures go to DLQ
        failed_event_store=failed_store,
    )
    spine_holder[0] = spine

    # Get test notifications
    notifications = create_test_notifications()

    print(f"Processing {len(notifications)} notification requests...")
    print()

    for notification in notifications:
        print(
            f"Enqueuing: {notification.payload.get('user_id')} - "
            f"{notification.payload.get('channels')}"
        )

    # Enqueue all notifications first
    for notification in notifications:
        await backend.enqueue(notification)

    print()
    print("Starting event processing...")
    print()

    # Run the spine - it will auto-stop when queue is empty
    stats = await spine.run()

    print()
    print("=" * 70)
    print("PROCESSING COMPLETE")
    print("=" * 70)
    print(f"Events processed: {stats.events_processed}")
    print(f"Events emitted: {stats.events_emitted}")
    if stats.handler_errors:
        print(f"Handler errors: {dict(stats.handler_errors)}")
    print()

    # Report DLQ contents
    print("=" * 70)
    print("DEAD LETTER QUEUE (Failed Events)")
    print("=" * 70)

    failed_events = failed_store.get_failed_events()
    if failed_events:
        for event, error in failed_events:
            print(f"  Event: {event.event_type}")
            print(f"  Payload: {event.payload}")
            print(f"  Error: {error}")
            print()
    else:
        print("  (empty - all events processed successfully)")

    print()

    # Report audit log
    print("=" * 70)
    print("AUDIT LOG (Successful Deliveries)")
    print("=" * 70)

    if audit_organ.audit_log:
        for record in audit_organ.audit_log:
            print(f"  User: {record['user_id']}, Channel: {record['channel']}")
    else:
        print("  (no deliveries recorded)")

    print()
    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
