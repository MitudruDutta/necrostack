"""Risk management organ for position monitoring."""

import logging
from collections import defaultdict
from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ

logger = logging.getLogger(__name__)

MAX_POSITION_VALUE = 1_000_000
MAX_DAILY_VOLUME = 50_000


class RiskManager(Organ):
    """Monitors positions and triggers alerts on limit breaches."""

    listens_to = ["SETTLEMENT_COMPLETE", "ORDER_FILLED", "ORDER_PARTIAL_FILL"]

    def __init__(self):
        super().__init__()
        self.positions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.daily_volume: dict[str, int] = defaultdict(int)
        self.volume_reset_date: str = datetime.now(UTC).date().isoformat()
        self.alerts: list[dict] = []

    def _check_daily_reset(self) -> None:
        """Reset daily volume if date changed."""
        today = datetime.now(UTC).date().isoformat()
        if today != self.volume_reset_date:
            self.daily_volume.clear()
            self.volume_reset_date = today

    def handle(self, event: Event) -> Event | None:
        self._check_daily_reset()
        p = event.payload
        alerts = []

        if event.event_type == "SETTLEMENT_COMPLETE":
            buyer = p.get("buyer_id")
            seller = p.get("seller_id")
            symbol = p.get("symbol")
            qty = p.get("quantity")
            price = p.get("price")

            # Validate required fields
            if buyer is None or seller is None or symbol is None:
                missing = [k for k, v in [("buyer_id", buyer), ("seller_id", seller), ("symbol", symbol)] if v is None]
                logger.warning("Skipping SETTLEMENT_COMPLETE with missing fields: %s", missing)
                return None
            if not isinstance(qty, (int, float)) or qty <= 0:
                logger.warning("Skipping SETTLEMENT_COMPLETE with invalid quantity: %s", qty)
                return None
            if not isinstance(price, (int, float)) or price <= 0:
                logger.warning("Skipping SETTLEMENT_COMPLETE with invalid price: %s", price)
                return None

            self.positions[buyer][symbol] += qty
            self.positions[seller][symbol] -= qty
            self.daily_volume[buyer] += qty
            self.daily_volume[seller] += qty

            # Check position limits for buyer
            buyer_value = abs(self.positions[buyer][symbol] * price)
            if buyer_value > MAX_POSITION_VALUE:
                alerts.append({
                    "type": "POSITION_LIMIT",
                    "trader_id": buyer,
                    "symbol": symbol,
                    "position_value": buyer_value,
                    "limit": MAX_POSITION_VALUE,
                })

            # Check position limits for seller
            seller_value = abs(self.positions[seller][symbol] * price)
            if seller_value > MAX_POSITION_VALUE:
                alerts.append({
                    "type": "POSITION_LIMIT",
                    "trader_id": seller,
                    "symbol": symbol,
                    "position_value": seller_value,
                    "limit": MAX_POSITION_VALUE,
                })

            # Check daily volume limits for buyer
            if self.daily_volume[buyer] > MAX_DAILY_VOLUME:
                alerts.append({
                    "type": "VOLUME_LIMIT",
                    "trader_id": buyer,
                    "daily_volume": self.daily_volume[buyer],
                    "limit": MAX_DAILY_VOLUME,
                })

            # Check daily volume limits for seller
            if self.daily_volume[seller] > MAX_DAILY_VOLUME:
                alerts.append({
                    "type": "VOLUME_LIMIT",
                    "trader_id": seller,
                    "daily_volume": self.daily_volume[seller],
                    "limit": MAX_DAILY_VOLUME,
                })

        elif event.event_type in ("ORDER_FILLED", "ORDER_PARTIAL_FILL"):
            trader = p.get("trader_id", "")
            qty = p.get("quantity") if p.get("quantity") is not None else p.get("filled_quantity", 0)
            self.daily_volume[trader] += qty

            if self.daily_volume[trader] > MAX_DAILY_VOLUME:
                alerts.append({
                    "type": "VOLUME_LIMIT",
                    "trader_id": trader,
                    "daily_volume": self.daily_volume[trader],
                    "limit": MAX_DAILY_VOLUME,
                })

        if alerts:
            self.alerts.extend(alerts)
            return Event(
                event_type="RISK_ALERT",
                payload={
                    "alerts": alerts,
                    "triggered_by": event.event_type,
                    "triggered_at": datetime.now(UTC).isoformat(),
                },
            )
        return None

    def get_position(self, trader_id: str, symbol: str) -> int:
        return self.positions[trader_id][symbol]

    def reset(self) -> None:
        self.positions.clear()
        self.daily_volume.clear()
        self.alerts.clear()
