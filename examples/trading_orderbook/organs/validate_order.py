"""Order validation organ."""

from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ

VALID_SYMBOLS = {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META"}
VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"LIMIT", "MARKET"}
MAX_QUANTITY = 10000
MAX_PRICE = 100000.0


class ValidateOrder(Organ):
    """Validates incoming orders before matching."""

    listens_to = ["ORDER_SUBMITTED"]

    def handle(self, event: Event) -> Event:
        p = event.payload
        errors = []

        trader_id = (p.get("trader_id") or "").strip()
        if not trader_id:
            errors.append("trader_id required")

        symbol = (p.get("symbol") or "").upper()
        if symbol not in VALID_SYMBOLS:
            errors.append(f"invalid symbol: {symbol}")

        side = (p.get("side") or "").upper()
        if side not in VALID_SIDES:
            errors.append(f"invalid side: {side}")

        order_type = p.get("order_type")
        if order_type is None:
            errors.append("order_type required")
            order_type = ""
        else:
            order_type = str(order_type).upper()
            if order_type not in VALID_ORDER_TYPES:
                errors.append(f"invalid order_type: {order_type}")

        quantity = p.get("quantity", 0)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            errors.append("quantity must be a positive integer")
        elif quantity > MAX_QUANTITY:
            errors.append(f"quantity exceeds max {MAX_QUANTITY}")

        price = p.get("price", 0)
        if order_type == "LIMIT":
            if not isinstance(price, (int, float)) or price <= 0:
                errors.append("LIMIT order requires positive price")
            elif price > MAX_PRICE:
                errors.append(f"price exceeds max {MAX_PRICE}")

        if errors:
            return Event(
                event_type="ORDER_REJECTED",
                payload={
                    "order_id": event.id,
                    "trader_id": trader_id or "unknown",
                    "reason": "; ".join(errors),
                    "rejected_at": datetime.now(UTC).isoformat(),
                },
            )

        return Event(
            event_type="ORDER_VALIDATED",
            payload={
                "order_id": event.id,
                "trader_id": trader_id,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "price": float(price) if order_type == "LIMIT" else None,
                "validated_at": datetime.now(UTC).isoformat(),
            },
        )
