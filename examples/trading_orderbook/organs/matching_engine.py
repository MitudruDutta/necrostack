"""Order matching engine with live order book."""

import heapq
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

from necrostack.core.event import Event
from necrostack.core.organ import Organ


@dataclass(order=True)
class OrderEntry:
    """Order book entry with priority ordering."""

    priority: float
    timestamp: float
    order_id: str = field(compare=False)
    trader_id: str = field(compare=False)
    symbol: str = field(compare=False)
    side: str = field(compare=False)
    quantity: int = field(compare=False)
    price: float = field(compare=False)


class OrderBook:
    """Price-time priority order book for a single symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: list[OrderEntry] = []
        self.asks: list[OrderEntry] = []
        self._orders: dict[str, OrderEntry] = {}

    def add_order(self, order: OrderEntry) -> None:
        if order.side == "BUY":
            entry = OrderEntry(
                priority=-order.price,
                timestamp=order.timestamp,
                order_id=order.order_id,
                trader_id=order.trader_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
            )
            heapq.heappush(self.bids, entry)
            self._orders[order.order_id] = entry
        else:
            heapq.heappush(self.asks, order)
            self._orders[order.order_id] = order

    def best_bid(self) -> OrderEntry | None:
        self._clean_heap(self.bids)
        return self.bids[0] if self.bids else None

    def best_ask(self) -> OrderEntry | None:
        self._clean_heap(self.asks)
        return self.asks[0] if self.asks else None

    def _clean_heap(self, heap: list) -> None:
        while heap and heap[0].order_id not in self._orders:
            heapq.heappop(heap)

    def remove_order(self, order_id: str) -> OrderEntry | None:
        return self._orders.pop(order_id, None)


class MatchingEngine(Organ):
    """Matches orders using price-time priority."""

    listens_to = ["ORDER_VALIDATED"]
    books: ClassVar[dict[str, OrderBook]] = {}

    def __init__(self):
        super().__init__()
        self.trade_count = 0

    def _get_book(self, symbol: str) -> OrderBook:
        if symbol not in MatchingEngine.books:
            MatchingEngine.books[symbol] = OrderBook(symbol)
        return MatchingEngine.books[symbol]

    def handle(self, event: Event) -> list[Event]:
        p = event.payload
        order_id = p.get("order_id", "")
        symbol = p.get("symbol", "")
        side = p.get("side", "")
        order_type = p.get("order_type", "")
        quantity = p.get("quantity", 0)
        price = p.get("price") or 0
        trader_id = p.get("trader_id", "")

        # Input validation
        if quantity <= 0:
            return [
                Event(
                    event_type="ORDER_REJECTED",
                    payload={
                        "order_id": order_id,
                        "trader_id": trader_id,
                        "reason": "Invalid quantity",
                        "rejected_at": datetime.now(UTC).isoformat(),
                    },
                )
            ]
        if order_type == "LIMIT" and price <= 0:
            return [
                Event(
                    event_type="ORDER_REJECTED",
                    payload={
                        "order_id": order_id,
                        "trader_id": trader_id,
                        "reason": "Invalid price",
                        "rejected_at": datetime.now(UTC).isoformat(),
                    },
                )
            ]
        if order_type not in ("LIMIT", "MARKET"):
            return [
                Event(
                    event_type="ORDER_REJECTED",
                    payload={
                        "order_id": order_id,
                        "trader_id": trader_id,
                        "reason": "Invalid order type",
                        "rejected_at": datetime.now(UTC).isoformat(),
                    },
                )
            ]
        if side not in ("BUY", "SELL"):
            return [
                Event(
                    event_type="ORDER_REJECTED",
                    payload={
                        "order_id": order_id,
                        "trader_id": trader_id,
                        "reason": "Invalid side",
                        "rejected_at": datetime.now(UTC).isoformat(),
                    },
                )
            ]

        book = self._get_book(symbol)
        events: list[Event] = []
        remaining_qty = quantity
        fills: list[dict] = []

        if side == "BUY":
            while remaining_qty > 0:
                best = book.best_ask()
                if not best:
                    break
                if order_type == "LIMIT" and best.price > price:
                    break

                fill_qty = min(remaining_qty, best.quantity)
                fill_price = best.price
                trade_id = f"T{uuid4()}"

                fills.append(
                    {
                        "trade_id": trade_id,
                        "quantity": fill_qty,
                        "price": fill_price,
                        "counterparty_id": best.trader_id,
                        "counterparty_order": best.order_id,
                    }
                )

                events.append(
                    Event(
                        event_type="TRADE_EXECUTED",
                        payload={
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "price": fill_price,
                            "quantity": fill_qty,
                            "buyer_id": trader_id,
                            "buyer_order": order_id,
                            "seller_id": best.trader_id,
                            "seller_order": best.order_id,
                            "executed_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )

                remaining_qty -= fill_qty
                best.quantity -= fill_qty
                if best.quantity <= 0:
                    book.remove_order(best.order_id)
                self.trade_count += 1
        else:
            while remaining_qty > 0:
                best = book.best_bid()
                if not best:
                    break
                actual_price = -best.priority
                if order_type == "LIMIT" and actual_price < price:
                    break

                fill_qty = min(remaining_qty, best.quantity)
                trade_id = f"T{uuid4()}"

                fills.append(
                    {
                        "trade_id": trade_id,
                        "quantity": fill_qty,
                        "price": actual_price,
                        "counterparty_id": best.trader_id,
                        "counterparty_order": best.order_id,
                    }
                )

                events.append(
                    Event(
                        event_type="TRADE_EXECUTED",
                        payload={
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "price": actual_price,
                            "quantity": fill_qty,
                            "buyer_id": best.trader_id,
                            "buyer_order": best.order_id,
                            "seller_id": trader_id,
                            "seller_order": order_id,
                            "executed_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )

                remaining_qty -= fill_qty
                best.quantity -= fill_qty
                if best.quantity <= 0:
                    book.remove_order(best.order_id)
                self.trade_count += 1

        filled_qty = quantity - remaining_qty

        if filled_qty == quantity:
            events.append(
                Event(
                    event_type="ORDER_FILLED",
                    payload={
                        "order_id": order_id,
                        "trader_id": trader_id,
                        "symbol": symbol,
                        "side": side,
                        "quantity": quantity,
                        "fills": fills,
                        "avg_price": sum(f["price"] * f["quantity"] for f in fills) / quantity,
                        "filled_at": datetime.now(UTC).isoformat(),
                    },
                )
            )
        elif filled_qty > 0:
            events.append(
                Event(
                    event_type="ORDER_PARTIAL_FILL",
                    payload={
                        "order_id": order_id,
                        "trader_id": trader_id,
                        "symbol": symbol,
                        "side": side,
                        "original_quantity": quantity,
                        "filled_quantity": filled_qty,
                        "remaining_quantity": remaining_qty,
                        "fills": fills,
                        "filled_at": datetime.now(UTC).isoformat(),
                    },
                )
            )
            if order_type == "LIMIT":
                book.add_order(
                    OrderEntry(
                        priority=price if side == "SELL" else -price,
                        timestamp=datetime.now(UTC).timestamp(),
                        order_id=order_id,
                        trader_id=trader_id,
                        symbol=symbol,
                        side=side,
                        quantity=remaining_qty,
                        price=price,
                    )
                )
        else:
            if order_type == "LIMIT":
                book.add_order(
                    OrderEntry(
                        priority=price if side == "SELL" else -price,
                        timestamp=datetime.now(UTC).timestamp(),
                        order_id=order_id,
                        trader_id=trader_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                    )
                )
                events.append(
                    Event(
                        event_type="ORDER_QUEUED",
                        payload={
                            "order_id": order_id,
                            "trader_id": trader_id,
                            "symbol": symbol,
                            "side": side,
                            "quantity": quantity,
                            "price": price,
                            "queued_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )
            else:
                events.append(
                    Event(
                        event_type="ORDER_REJECTED",
                        payload={
                            "order_id": order_id,
                            "trader_id": trader_id,
                            "reason": "No liquidity for MARKET order",
                            "rejected_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )

        return events

    @classmethod
    def reset_books(cls) -> None:
        cls.books.clear()

    @classmethod
    def get_book_depth(cls, symbol: str) -> dict:
        if symbol not in cls.books:
            return {"bids": [], "asks": []}
        book = cls.books[symbol]
        return {
            "bids": [
                (o.price, o.quantity)
                for o in sorted(
                    [o for o in book._orders.values() if o.side == "BUY"],
                    key=lambda x: (-x.price, x.timestamp),
                )[:5]
            ],
            "asks": [
                (o.price, o.quantity)
                for o in sorted(
                    [o for o in book._orders.values() if o.side == "SELL"],
                    key=lambda x: (x.price, x.timestamp),
                )[:5]
            ],
        }
