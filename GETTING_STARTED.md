# Getting Started with NecroStack

> Your first event-driven system in 10 minutes

## Prerequisites

- Python 3.11 or higher
- Basic understanding of async/await
- Familiarity with Python type hints

## Installation

```bash
# Core installation
pip install necrostack

# With Redis support (for production)
pip install necrostack[redis]

# For development (includes testing tools)
pip install necrostack[dev]
```

## Your First Event Pipeline (5 minutes)

Let's build a simple notification system that processes welcome messages.

### Step 1: Create Your Project

```bash
mkdir my-necrostack-app
cd my-necrostack-app
touch main.py
```

### Step 2: Define Your Events and Handlers

Open `main.py` and add:

```python
import asyncio
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import Spine
from necrostack.backends.inmemory import InMemoryBackend


# Step 1: Create a validation handler
class ValidateUser(Organ):
    """Validates user registration data"""
    listens_to = ["USER_REGISTERED"]
    
    def handle(self, event: Event) -> Event | None:
        user_data = event.payload
        
        # Simple validation
        if not user_data.get("email") or not user_data.get("name"):
            print(f"❌ Invalid user data: {user_data}")
            return None
        
        print(f"✅ Valid user: {user_data['name']}")
        return Event(
            event_type="USER_VALIDATED",
            payload=user_data
        )


# Step 2: Create a welcome message handler
class SendWelcomeEmail(Organ):
    """Sends welcome email to new users"""
    listens_to = ["USER_VALIDATED"]
    
    async def handle(self, event: Event) -> Event:
        user_data = event.payload
        
        # Simulate sending email (async I/O)
        await asyncio.sleep(0.1)
        
        print(f"📧 Sending welcome email to {user_data['email']}")
        
        return Event(
            event_type="WELCOME_EMAIL_SENT",
            payload={
                "email": user_data["email"],
                "sent_at": "2024-01-15T10:00:00Z"
            }
        )


# Step 3: Create a logging handler
class LogActivity(Organ):
    """Logs all user activities"""
    listens_to = ["WELCOME_EMAIL_SENT"]
    
    def handle(self, event: Event) -> None:
        print(f"📝 Logged activity: {event.event_type} for {event.payload['email']}")


# Step 4: Wire everything together
async def main():
    # Create the event processing pipeline
    spine = Spine(
        organs=[
            ValidateUser(),
            SendWelcomeEmail(),
            LogActivity()
        ],
        backend=InMemoryBackend()
    )
    
    # Create a user registration event
    registration = Event(
        event_type="USER_REGISTERED",
        payload={
            "name": "Alice",
            "email": "alice@example.com",
            "signup_source": "web"
        }
    )
    
    print("🚀 Starting event pipeline...\n")
    
    # Run the pipeline
    await spine.run(registration)
    
    print("\n✨ Pipeline complete!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 3: Run It!

```bash
python main.py
```

**Expected Output:**
```
🚀 Starting event pipeline...

✅ Valid user: Alice
📧 Sending welcome email to alice@example.com
📝 Logged activity: WELCOME_EMAIL_SENT for alice@example.com

✨ Pipeline complete!
```

**Congratulations!** 🎉 You just built your first event-driven system with NecroStack.

## Understanding What Happened

Let's break down the flow:

```
USER_REGISTERED
      ↓
ValidateUser
      ↓
USER_VALIDATED
      ↓
SendWelcomeEmail (async)
      ↓
WELCOME_EMAIL_SENT
      ↓
LogActivity
```

1. **Event Triggered**: `USER_REGISTERED` event starts the chain
2. **Validation**: `ValidateUser` checks the data and emits `USER_VALIDATED`
3. **Email Sent**: `SendWelcomeEmail` (async) sends email and emits `WELCOME_EMAIL_SENT`
4. **Activity Logged**: `LogActivity` records the activity
5. **Complete**: Pipeline finishes

## Next Steps: Add Error Handling (5 minutes)

Let's make our pipeline more robust.

### Step 1: Add Dead-Letter Queue

```python
from necrostack.core.spine import EnqueueFailureMode

# Update the Spine configuration
spine = Spine(
    organs=[ValidateUser(), SendWelcomeEmail(), LogActivity()],
    backend=InMemoryBackend(),
    enqueue_failure_mode=EnqueueFailureMode.STORE,  # Store failed events
    retry_attempts=3,                                # Retry 3 times
    retry_base_delay=0.1,                            # 100ms base delay
)
```

### Step 2: Add a Failing Scenario

```python
class SendWelcomeEmail(Organ):
    """Sends welcome email to new users"""
    listens_to = ["USER_VALIDATED"]
    
    def __init__(self):
        super().__init__()
        self.attempt_count = 0
    
    async def handle(self, event: Event) -> Event:
        user_data = event.payload
        
        # Simulate occasional failures
        self.attempt_count += 1
        if self.attempt_count == 1:
            raise Exception("SMTP server temporarily unavailable")
        
        await asyncio.sleep(0.1)
        print(f"📧 Sending welcome email to {user_data['email']}")
        
        return Event(
            event_type="WELCOME_EMAIL_SENT",
            payload={"email": user_data["email"]}
        )
```

### Step 3: Run and Watch Retry

```bash
python main.py
```

You'll see the retry happen automatically!

## Scaling to Production

When you're ready to move to production, just swap the backend:

```python
from necrostack.backends.redis_backend import RedisBackend

# Development
backend = InMemoryBackend()

# Production
backend = RedisBackend(
    redis_url="redis://localhost:6379",
    stream_key="myapp:events",
    consumer_group="workers"
)

# Everything else stays the same!
```

## Real-World Example: Multi-Channel Notifications

Let's build something more complex—a notification system that sends to multiple channels.

Create `notifications.py`:

```python
import asyncio
from necrostack.core.event import Event
from necrostack.core.organ import Organ
from necrostack.core.spine import Spine
from necrostack.backends.inmemory import InMemoryBackend


class ValidateNotification(Organ):
    """Validates notification requests"""
    listens_to = ["NOTIFICATION_REQUESTED"]
    
    def handle(self, event: Event) -> Event | None:
        data = event.payload
        
        if not data.get("user_id") or not data.get("message"):
            return None
        
        if not data.get("channels"):
            data["channels"] = ["email"]  # Default channel
        
        return Event("NOTIFICATION_VALIDATED", payload=data)


class RouteToChannels(Organ):
    """Routes notification to appropriate channels"""
    listens_to = ["NOTIFICATION_VALIDATED"]
    
    def handle(self, event: Event) -> list[Event]:
        data = event.payload
        events = []
        
        for channel in data["channels"]:
            events.append(Event(
                event_type=f"{channel.upper()}_SEND_REQUESTED",
                payload={
                    "user_id": data["user_id"],
                    "message": data["message"]
                }
            ))
        
        return events


class EmailSender(Organ):
    """Sends email notifications"""
    listens_to = ["EMAIL_SEND_REQUESTED"]
    
    async def handle(self, event: Event) -> Event:
        await asyncio.sleep(0.1)  # Simulate SMTP
        print(f"📧 Email sent to user {event.payload['user_id']}")
        return Event("EMAIL_DELIVERED", payload=event.payload)


class SmsSender(Organ):
    """Sends SMS notifications"""
    listens_to = ["SMS_SEND_REQUESTED"]
    
    async def handle(self, event: Event) -> Event:
        await asyncio.sleep(0.05)  # Simulate SMS gateway
        print(f"📱 SMS sent to user {event.payload['user_id']}")
        return Event("SMS_DELIVERED", payload=event.payload)


class PushSender(Organ):
    """Sends push notifications"""
    listens_to = ["PUSH_SEND_REQUESTED"]
    
    async def handle(self, event: Event) -> Event:
        await asyncio.sleep(0.05)  # Simulate FCM/APNs
        print(f"🔔 Push sent to user {event.payload['user_id']}")
        return Event("PUSH_DELIVERED", payload=event.payload)


class AuditDeliveries(Organ):
    """Audits all successful deliveries"""
    listens_to = ["EMAIL_DELIVERED", "SMS_DELIVERED", "PUSH_DELIVERED"]
    
    def handle(self, event: Event) -> None:
        channel = event.event_type.split("_")[0].lower()
        print(f"📝 Audit: {channel} delivered to user {event.payload['user_id']}")


async def main():
    spine = Spine(
        organs=[
            ValidateNotification(),
            RouteToChannels(),
            EmailSender(),
            SmsSender(),
            PushSender(),
            AuditDeliveries()
        ],
        backend=InMemoryBackend()
    )
    
    # Send multi-channel notification
    notification = Event(
        event_type="NOTIFICATION_REQUESTED",
        payload={
            "user_id": "user_123",
            "message": "Your order has shipped!",
            "channels": ["email", "sms", "push"]
        }
    )
    
    print("🚀 Sending multi-channel notification...\n")
    await spine.run(notification)
    print("\n✨ All channels delivered!")


if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python notifications.py
```

**Output:**
```
🚀 Sending multi-channel notification...

📧 Email sent to user user_123
📱 SMS sent to user user_123
🔔 Push sent to user user_123
📝 Audit: email delivered to user user_123
📝 Audit: sms delivered to user user_123
📝 Audit: push delivered to user user_123

✨ All channels delivered!
```

## Key Concepts to Remember

### 1. Events are Immutable
```python
event = Event("ORDER_PLACED", {"id": 123})
# event.payload["id"] = 456  # ❌ Can't modify
```

### 2. Handlers Can Return
- **Single Event**: `return Event(...)`
- **Multiple Events**: `return [Event(...), Event(...)]`
- **No Events**: `return None`

### 3. Both Sync and Async Work
```python
def handle(self, event):      # Sync - fast operations
async def handle(self, event): # Async - I/O operations
```

### 4. Type Safety is Built-In
```python
# Pydantic validates automatically
Event(event_type="", payload={})  # ❌ Raises ValidationError
Event(event_type="OK", payload={})  # ✅ Valid
```

## Common Patterns

### Pattern 1: Validate → Process → Audit
```python
COMMAND → Validate → VALIDATED → Process → COMPLETED → Audit
```

### Pattern 2: Fan-Out (One to Many)
```python
ORDER → Split → [ITEM_1, ITEM_2, ITEM_3]
```

### Pattern 3: Fan-In (Many to One)
```python
[ITEM_1_DONE, ITEM_2_DONE, ITEM_3_DONE] → Aggregate → ORDER_COMPLETE
```

### Pattern 4: Saga (Compensation)
```python
STEP_1 → STEP_2 → STEP_3_FAILED → COMPENSATE_2 → COMPENSATE_1
```

## Next Steps

1. **Read the Examples**: Check out `examples/` in the repo
   - `notification_pipeline/` - Production-ready notification system
   - `trading_orderbook/` - Real-time order matching
   
2. **Read the Docs**: See [README.md](README.md) for comprehensive documentation

3. **Join the Community**: 
   - Star the repo ⭐
   - Open issues for questions
   - Share your use case

4. **Build Something**: The best way to learn is by doing!

## Troubleshooting

### Events Not Being Processed?
- Check `listens_to` matches event type exactly (case-sensitive)
- Ensure Organ is registered with Spine
- Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`

### Need Help?
- Check [FAQ.md](FAQ.md)
- Open a GitHub issue
- Join discussions

## Resources

- **Quick Start**: [QUICKSTART.md](QUICKSTART.md) - Live demo scripts
- **Pitch Deck**: [PITCH.md](PITCH.md) - For presentations
- **Use Cases**: [USE_CASES.md](USE_CASES.md) - Real-world examples
- **Diagrams**: [DIAGRAMS.md](DIAGRAMS.md) - Visual architecture
- **FAQ**: [FAQ.md](FAQ.md) - Common questions

---

**Ready to build?** Start with the examples and experiment! 🚀
