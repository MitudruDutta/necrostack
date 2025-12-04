"""Trade settlement organ with simulated clearing house."""

import asyncio
import random
from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ

# Traders that will have settlement failures (insufficient funds, etc.)
PROBLEMATIC_TRADERS = {"trader_bad_1", "trader_bad_2"}


class SettlementOrgan(Organ):
    """Settles executed trades via simulated clearing house.

    Async handler demonstrating:
    - External API latency simulation
    - Transient failures (network issues) - will retry
    - Permanent failures (insufficient funds) - goes to DLQ
    """

    listens_to = ["TRADE_EXECUTED"]

    def __init__(self):
        super().__init__()
        self.settled_count = 0
        self.failed_count = 0

    async def handle(self, event: Event) -> Event:
        p = event.payload
        trade_id = p["trade_id"]
        buyer_id = p["buyer_id"]
        seller_id = p["seller_id"]
        quantity = p["quantity"]
        price = p["price"]
        total_value = quantity * price

        # Simulate clearing house latency (50-150ms)
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Check for problematic traders (permanent failure)
        if buyer_id in PROBLEMATIC_TRADERS:
            self.failed_count += 1
            raise ValueError(f"Settlement failed: {buyer_id} has insufficient funds")
        if seller_id in PROBLEMATIC_TRADERS:
            self.failed_count += 1
            raise ValueError(f"Settlement failed: {seller_id} has restricted account")

        # Simulate 5% transient failure rate (network issues)
        if random.random() < 0.05:
            raise ConnectionError(f"Clearing house timeout for trade {trade_id}")

        self.settled_count += 1

        return Event(
            event_type="SETTLEMENT_COMPLETE",
            payload={
                "trade_id": trade_id,
                "symbol": p["symbol"],
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "quantity": quantity,
                "price": price,
                "total_value": total_value,
                "settlement_fee": round(total_value * 0.0001, 2),  # 1bp fee
                "settled_at": datetime.now(UTC).isoformat(),
            },
        )
