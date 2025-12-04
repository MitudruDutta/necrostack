#!/usr/bin/env python3
"""
Notification Pipeline - NecroStack Demo Application

Run modes:
  python main.py                        # Demo with sample notifications
  python main.py --file notifications.json  # Load from JSON/CSV
  python main.py --interactive          # Interactive CLI mode
  python main.py --stress --count 100   # Stress test
"""

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

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

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

VALID_PRIORITIES = {"low", "normal", "high", "critical"}


class AutoStopBackend(InMemoryBackend):
    """Backend that stops spine when queue empties after processing."""

    def __init__(self, spine_holder: list, idle_timeout: float = 0.3):
        super().__init__()
        self._spine_holder = spine_holder
        self._has_processed = False
        self._last_event_time = 0.0
        self._idle_timeout = idle_timeout

    async def pull(self, timeout: float = 1.0) -> Event | None:
        event = await super().pull(timeout)
        if event is not None:
            self._has_processed = True
            self._last_event_time = time.monotonic()
        elif self._has_processed:
            if time.monotonic() - self._last_event_time > self._idle_timeout:
                if self._spine_holder[0]:
                    self._spine_holder[0].stop()
        return event


def create_sample_notifications() -> list[dict]:
    """Create sample notification requests."""
    order_id = random.randint(10000, 99999)
    ts = datetime.now().strftime("%H:%M:%S")

    return [
        {"user_id": "user_001", "channels": ["email", "sms", "push"], "message": f"Order #{order_id} shipped! [{ts}]", "priority": "high"},
        {"user_id": "user_002", "channels": ["email"], "message": f"Weekly digest: {random.randint(1,20)} updates", "priority": "low"},
        {"user_id": "user_003", "channels": ["sms", "push"], "message": f"Security alert at {ts}", "priority": "critical"},
        {"user_id": "user_001", "channels": ["email"], "message": "", "priority": "normal"},
        {"user_id": "user_002", "channels": ["telegram"], "message": "Test", "priority": "normal"},
    ]


def create_stress_notifications(count: int) -> list[dict]:
    """Generate random notifications for stress testing."""
    users = ["user_001", "user_002", "user_003"] + [f"user_{i:03d}" for i in range(4, 20)]
    channels_options = [["email"], ["sms"], ["push"], ["email", "sms"], ["email", "push"], ["sms", "push"], ["email", "sms", "push"]]
    priorities = ["low", "normal", "high", "critical"]
    messages = ["Order update", "Security alert", "Weekly digest", "Payment received", "Shipping update", "Account notice"]

    return [
        {
            "user_id": random.choice(users),
            "channels": random.choice(channels_options),
            "message": f"{random.choice(messages)} #{random.randint(1000,9999)}",
            "priority": random.choice(priorities),
        }
        for _ in range(count)
    ]


def load_from_file(filepath: str) -> list[dict]:
    """Load notifications from JSON or CSV file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    if path.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("notifications", [])
    elif path.suffix == ".csv":
        import csv
        notifications = []
        with open(path) as f:
            for i, row in enumerate(csv.DictReader(f), start=2):
                user_id = row.get("user_id", "").strip()
                if not user_id:
                    print(f"Warning: Skipping row {i}: missing user_id")
                    continue
                message = row.get("message", "").strip()
                if not message:
                    print(f"Warning: Skipping row {i}: missing message")
                    continue
                channels_str = row.get("channels", "").strip()
                if not channels_str:
                    print(f"Warning: Skipping row {i}: missing channels")
                    continue
                channels = [c.strip() for c in channels_str.split("|") if c.strip()]
                if not channels:
                    print(f"Warning: Skipping row {i}: no valid channels")
                    continue
                priority = row.get("priority", "").strip().lower()
                if priority not in VALID_PRIORITIES:
                    priority = "normal"
                notifications.append({
                    "user_id": user_id,
                    "channels": channels,
                    "message": message,
                    "priority": priority,
                })
        return notifications
    else:
        raise ValueError(f"Unsupported format: {path.suffix}")


def parse_notification_string(s: str) -> dict | None:
    """Parse: user_001 email,sms 'Your message here' high
    
    Requires quoted messages for multi-word content.
    """
    s = s.strip()
    if not s:
        return None

    # Split first two tokens: user_id and channels
    parts = s.split(maxsplit=2)
    if len(parts) < 3:
        return None

    user_id, channels_str, rest = parts

    # Check for quoted message
    if "'" not in rest:
        # Unquoted: support trailing priority via rsplit
        rest_parts = rest.rsplit(maxsplit=1)
        if len(rest_parts) == 1:
            message = rest_parts[0].strip()
            priority = "normal"
        elif rest_parts[1].lower() in VALID_PRIORITIES:
            message = rest_parts[0].strip()
            priority = rest_parts[1].lower()
        else:
            message = rest.strip()
            priority = "normal"
        if not message:
            return None
    else:
        # Find opening quote
        first_quote = rest.find("'")
        if first_quote == -1:
            return None

        # Scan for closing quote (handle doubled quotes as escape)
        i = first_quote + 1
        message_chars = []
        while i < len(rest):
            if rest[i] == "'":
                if i + 1 < len(rest) and rest[i + 1] == "'":
                    # Escaped quote
                    message_chars.append("'")
                    i += 2
                else:
                    # Closing quote
                    break
            else:
                message_chars.append(rest[i])
                i += 1
        else:
            # No closing quote found
            return None

        message = "".join(message_chars)
        remainder = rest[i + 1:].strip()
        priority = remainder.lower() if remainder.lower() in VALID_PRIORITIES else "normal"

    channels = [c.strip() for c in channels_str.split(",") if c.strip()]
    if not channels:
        return None

    return {
        "user_id": user_id,
        "channels": channels,
        "message": message,
        "priority": priority,
    }


async def run_pipeline(notifications: list[dict], verbose: bool = True):
    """Run the notification pipeline."""
    failed_store = InMemoryFailedEventStore()
    audit_organ = AuditOrgan()
    spine_holder: list = [None]
    backend = AutoStopBackend(spine_holder)

    spine = Spine(
        organs=[ValidateOrgan(), RouterOrgan(), EmailOrgan(), SmsOrgan(), PushOrgan(), audit_organ],
        backend=backend,
        max_steps=5000,
        enqueue_failure_mode=EnqueueFailureMode.STORE,
        handler_failure_mode=HandlerFailureMode.STORE,
        failed_event_store=failed_store,
    )
    spine_holder[0] = spine

    if verbose:
        print("=" * 60)
        print("NOTIFICATION PIPELINE")
        print("=" * 60)
        print(f"\nProcessing {len(notifications)} notifications...\n")

    for n in notifications:
        event = Event(event_type="NOTIFICATION_REQUESTED", payload=n)
        await backend.enqueue(event)
        if verbose and len(notifications) <= 20:
            user_id = n.get("user_id", "?")
            channels = n.get("channels", [])
            message = str(n.get("message", ""))[:40] if n.get("message") else ""
            print(f"  → {user_id}: {channels} - {message}...")

    if verbose:
        print("\nProcessing...\n")

    start = time.monotonic()
    stats = await spine.run()
    elapsed = time.monotonic() - start

    if verbose:
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"  Events processed: {stats.events_processed}")
        print(f"  Events emitted: {stats.events_emitted}")
        print(f"  Time: {elapsed:.2f}s ({stats.events_processed/elapsed:.1f} events/sec)")

        if stats.handler_errors:
            print(f"  Handler errors: {dict(stats.handler_errors)}")

        failed = failed_store.get_failed_events()
        if failed:
            print(f"\n  DLQ: {len(failed)} failed events")
            for event, error in failed[:3]:
                print(f"    - {event.event_type}: {str(error)[:50]}")

        if audit_organ.audit_log:
            print(f"\n  Deliveries: {len(audit_organ.audit_log)}")

    return stats, audit_organ, failed_store


async def run_interactive():
    """Interactive notification entry mode."""
    print("=" * 60)
    print("INTERACTIVE NOTIFICATION MODE")
    print("=" * 60)
    print("Format: user_id channels 'message' priority")
    print("Example: user_001 email,sms 'Hello world' high")
    print("Commands: send, stats, quit")
    print("=" * 60)

    pending: list[dict] = []

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("quit", "exit"):
            break
        elif cmd == "send":
            if pending:
                await run_pipeline(pending)
                pending.clear()
            else:
                print("  No notifications queued. Add some first.")
        elif cmd == "stats":
            print(f"  Queued: {len(pending)}")
        else:
            notif = parse_notification_string(user_input)
            if notif:
                pending.append(notif)
                print(f"  ✓ Queued: {notif['user_id']} → {notif['channels']}")
            else:
                print("  ✗ Invalid format")


def main():
    parser = argparse.ArgumentParser(description="Notification Pipeline Demo")
    parser.add_argument("--file", "-f", type=str, help="Load from JSON/CSV file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--stress", action="store_true", help="Stress test mode")
    parser.add_argument("--count", type=int, default=100, help="Number of notifications for stress test")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(run_interactive())
    elif args.file:
        print(f"📂 Loading from: {args.file}\n")
        notifications = load_from_file(args.file)
        asyncio.run(run_pipeline(notifications, verbose=not args.quiet))
    elif args.stress:
        print(f"🚀 STRESS TEST: {args.count} notifications\n")
        notifications = create_stress_notifications(args.count)
        asyncio.run(run_pipeline(notifications, verbose=not args.quiet))
    else:
        notifications = create_sample_notifications()
        asyncio.run(run_pipeline(notifications, verbose=not args.quiet))


if __name__ == "__main__":
    main()
