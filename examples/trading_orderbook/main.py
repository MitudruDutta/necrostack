#!/usr/bin/env python3
"""
Trading Order Book - NecroStack Demo Application

A real-time order matching engine demonstrating:
- Complex state management (order book)
- Multi-event fan-out (trades, fills, settlements)
- Async handlers with latency simulation
- DLQ for failed settlements
- Circuit breaker testing
- Handler timeout handling

Run modes:
  python main.py                      # Sample orders demo
  python main.py --stress --orders 500  # Stress test
  python main.py --file orders.json   # Load from JSON file
  python main.py --interactive        # Interactive CLI mode
"""

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from organs import (
    AuditTrail,
    MatchingEngine,
    RiskManager,
    SettlementOrgan,
    ValidateOrder,
)

from necrostack.backends.inmemory import InMemoryBackend
from necrostack.core.event import Event
from necrostack.core.spine import (
    EnqueueFailureMode,
    HandlerFailureMode,
    InMemoryFailedEventStore,
    Spine,
)


class AutoStopBackend(InMemoryBackend):
    """Backend that stops spine when queue empties after processing."""

    def __init__(self, spine_holder: list, idle_timeout: float = 0.5):
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
            # Stop if idle for too long
            if time.monotonic() - self._last_event_time > self._idle_timeout:
                if self._spine_holder[0]:
                    self._spine_holder[0].stop()
        return event


def create_sample_orders() -> list[Event]:
    """Create a realistic sequence of orders."""
    orders = [
        # Initial liquidity - limit orders to build the book
        {
            "trader_id": "mm_1",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 100,
            "price": 149.50,
        },
        {
            "trader_id": "mm_1",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 200,
            "price": 149.00,
        },
        {
            "trader_id": "mm_1",
            "symbol": "AAPL",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 100,
            "price": 150.50,
        },
        {
            "trader_id": "mm_1",
            "symbol": "AAPL",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 200,
            "price": 151.00,
        },
        # Aggressive orders that will match
        {
            "trader_id": "trader_1",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 50,
            "price": 0,
        },
        {
            "trader_id": "trader_2",
            "symbol": "AAPL",
            "side": "SELL",
            "order_type": "MARKET",
            "quantity": 75,
            "price": 0,
        },
        # Partial fill scenario
        {
            "trader_id": "trader_3",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 300,
            "price": 150.75,
        },
        # Cross-spread order
        {
            "trader_id": "trader_4",
            "symbol": "AAPL",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 150,
            "price": 149.25,
        },
        # Invalid orders (will be rejected)
        {
            "trader_id": "",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 100,
            "price": 150.00,
        },
        {
            "trader_id": "trader_5",
            "symbol": "INVALID",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 100,
            "price": 100.00,
        },
        {
            "trader_id": "trader_6",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": -50,
            "price": 150.00,
        },
        # Orders from problematic traders (settlement will fail)
        {
            "trader_id": "trader_bad_1",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 25,
            "price": 0,
        },
        # More valid orders
        {
            "trader_id": "trader_7",
            "symbol": "GOOGL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 50,
            "price": 140.00,
        },
        {
            "trader_id": "trader_8",
            "symbol": "GOOGL",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 50,
            "price": 140.00,
        },
        # Large order to trigger risk alert
        {
            "trader_id": "whale_1",
            "symbol": "TSLA",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 5000,
            "price": 250.00,
        },
        {
            "trader_id": "whale_2",
            "symbol": "TSLA",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 5000,
            "price": 250.00,
        },
    ]
    return [Event(event_type="ORDER_SUBMITTED", payload=o) for o in orders]


def create_stress_orders(count: int) -> list[Event]:
    """Generate random orders for stress testing."""
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META"]
    traders = [f"trader_{i}" for i in range(50)] + ["trader_bad_1", "trader_bad_2"]

    orders = []
    for _ in range(count):
        symbol = random.choice(symbols)
        base_price = {
            "AAPL": 150,
            "GOOGL": 140,
            "MSFT": 380,
            "AMZN": 180,
            "TSLA": 250,
            "NVDA": 480,
            "META": 500,
        }[symbol]

        order = {
            "trader_id": random.choice(traders),
            "symbol": symbol,
            "side": random.choice(["BUY", "SELL"]),
            "order_type": random.choices(["LIMIT", "MARKET"], weights=[0.8, 0.2])[0],
            "quantity": random.randint(10, 500),
            "price": round(base_price * random.uniform(0.98, 1.02), 2),
        }
        if order["order_type"] == "MARKET":
            order["price"] = 0
        orders.append(Event(event_type="ORDER_SUBMITTED", payload=order))

    return orders


def load_orders_from_file(filepath: str) -> list[Event]:
    """Load orders from JSON or CSV file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    if path.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        orders = data if isinstance(data, list) else data.get("orders", [])
    elif path.suffix == ".csv":
        import csv
        orders = []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    order = {
                        "trader_id": row.get("trader_id", ""),
                        "symbol": row.get("symbol", ""),
                        "side": row.get("side", ""),
                        "order_type": row.get("order_type", "LIMIT"),
                        "quantity": int(row.get("quantity", 0)),
                        "price": float(row.get("price", 0)),
                    }
                    orders.append(order)
                except (ValueError, KeyError) as e:
                    print(f"Warning: Skipping invalid row: {e}")
                    continue
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    return [Event(event_type="ORDER_SUBMITTED", payload=o) for o in orders]


def parse_order_string(order_str: str, trader_id: str = "interactive") -> dict | None:
    """Parse order string like 'BUY 100 AAPL @ 150.50' or 'SELL 50 TSLA MKT'."""
    parts = order_str.upper().split()
    if len(parts) < 3:
        return None

    try:
        side = parts[0]
        quantity = int(parts[1])
        symbol = parts[2]

        if len(parts) >= 5 and parts[3] == "@":
            price = float(parts[4])
            order_type = "LIMIT"
        elif len(parts) >= 4 and parts[3] == "MKT":
            price = 0
            order_type = "MARKET"
        else:
            return None

        return {
            "trader_id": trader_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
        }
    except (ValueError, IndexError):
        return None


async def run_trading_system(orders: list[Event], verbose: bool = True):
    """Run the trading system with given orders."""
    # Reset state
    MatchingEngine.reset_books()

    # Create components
    failed_store = InMemoryFailedEventStore()
    spine_holder: list = [None]
    backend = AutoStopBackend(spine_holder, idle_timeout=0.3)

    # Create organs
    audit = AuditTrail()
    matching = MatchingEngine()
    settlement = SettlementOrgan()
    risk = RiskManager()

    spine = Spine(
        organs=[
            ValidateOrder(),
            matching,
            settlement,
            risk,
            audit,
        ],
        backend=backend,
        max_steps=50000,
        enqueue_failure_mode=EnqueueFailureMode.STORE,
        handler_failure_mode=HandlerFailureMode.STORE,
        failed_event_store=failed_store,
        retry_attempts=2,
        retry_base_delay=0.01,
        handler_timeout=5.0,
    )
    spine_holder[0] = spine

    if verbose:
        print("=" * 60)
        print("TRADING ORDER BOOK SYSTEM")
        print("=" * 60)
        print(f"\nSubmitting {len(orders)} orders...\n")

    # Enqueue all orders
    for order in orders:
        await backend.enqueue(order)
        if verbose and len(orders) <= 20:
            p = order.payload
            price_str = p.get("price") or "MKT"
            print(f"  → {p['trader_id']}: {p['side']} {p['quantity']} {p['symbol']} @ {price_str}")

    if verbose:
        print("\nProcessing orders...\n")

    start = time.monotonic()
    stats = await spine.run()
    elapsed = time.monotonic() - start

    if verbose:
        print("\n" + "=" * 60)
        print("EXECUTION RESULTS")
        print("=" * 60)
        print(f"  Events processed: {stats.events_processed}")
        print(f"  Events emitted: {stats.events_emitted}")
        print(f"  Trades executed: {matching.trade_count}")
        print(f"  Settlements: {settlement.settled_count}")
        print(f"  Settlement failures: {settlement.failed_count}")
        print(f"  Time elapsed: {elapsed:.3f}s")
        print(f"  Throughput: {stats.events_processed / elapsed:.1f} events/sec")

        if stats.handler_errors:
            print(f"\n  Handler errors: {dict(stats.handler_errors)}")

        # DLQ report
        failed = failed_store.get_failed_events()
        if failed:
            print("\n" + "=" * 60)
            print("DEAD LETTER QUEUE")
            print("=" * 60)
            for event, error in failed[:5]:  # Show first 5
                print(f"  {event.event_type}: {str(error)[:60]}")
            if len(failed) > 5:
                print(f"  ... and {len(failed) - 5} more")

        # Risk alerts
        if risk.alerts:
            print("\n" + "=" * 60)
            print("RISK ALERTS")
            print("=" * 60)
            for alert in risk.alerts[:5]:
                print(f"  {alert['type']}: {alert['trader_id']}")

        # Order book state
        print("\n" + "=" * 60)
        print("ORDER BOOK STATE (AAPL)")
        print("=" * 60)
        depth = MatchingEngine.get_book_depth("AAPL")
        bids = depth.get("bids", [])
        asks = depth.get("asks", [])
        print("  BIDS:")
        for price, qty in bids[:3] if bids else [("--", "--")]:
            print(f"    {qty:>6} @ ${price}")
        print("  ASKS:")
        for price, qty in asks[:3] if asks else [("--", "--")]:
            print(f"    {qty:>6} @ ${price}")

        audit.print_summary()

    return stats, audit, failed_store


def main():
    parser = argparse.ArgumentParser(description="Trading Order Book Demo")
    parser.add_argument("--stress", action="store_true", help="Run stress test")
    parser.add_argument("--orders", type=int, default=500, help="Number of orders for stress test")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--file", type=str, help="Load orders from JSON/CSV file")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Interactive order entry mode"
    )
    parser.add_argument(
        "--trader", type=str, default="trader_cli", help="Trader ID for interactive mode"
    )
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(run_interactive_mode(args.trader))
    elif args.file:
        print(f"📂 Loading orders from: {args.file}\n")
        orders = load_orders_from_file(args.file)
        asyncio.run(run_trading_system(orders, verbose=not args.quiet))
    elif args.stress:
        print(f"🚀 STRESS TEST MODE: {args.orders} orders\n")
        orders = create_stress_orders(args.orders)
        asyncio.run(run_trading_system(orders, verbose=not args.quiet))
    else:
        orders = create_sample_orders()
        asyncio.run(run_trading_system(orders, verbose=not args.quiet))


async def run_interactive_mode(trader_id: str):
    """Run interactive order entry mode with spine running in background."""
    MatchingEngine.reset_books()

    failed_store = InMemoryFailedEventStore()
    backend = InMemoryBackend()

    audit = AuditTrail()
    matching = MatchingEngine()
    settlement = SettlementOrgan()
    risk = RiskManager()

    spine = Spine(
        organs=[ValidateOrder(), matching, settlement, risk, audit],
        backend=backend,
        max_steps=50000,
        enqueue_failure_mode=EnqueueFailureMode.STORE,
        handler_failure_mode=HandlerFailureMode.STORE,
        failed_event_store=failed_store,
        handler_timeout=5.0,
    )

    print("=" * 60)
    print("INTERACTIVE TRADING MODE")
    print("=" * 60)
    print(f"Trader ID: {trader_id}")
    print("Symbols: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META")
    print()
    print("Order format:")
    print("  BUY 100 AAPL @ 150.50   (limit order)")
    print("  SELL 50 TSLA MKT        (market order)")
    print()
    print("Commands: book <symbol>, stats, quit")
    print("=" * 60)

    # Start spine in background
    spine_task = asyncio.create_task(spine.run())

    try:
        while True:
            # Use asyncio-friendly input
            try:
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(None, lambda: input("\n> ").strip())
            except (EOFError, KeyboardInterrupt):
                print("\nExiting...")
                break

            if not user_input:
                continue

            cmd = user_input.lower()

            if cmd in ("quit", "exit"):
                break
            elif cmd == "stats":
                audit.print_summary()
                print(f"  Trades: {matching.trade_count}")
                print(f"  Settlements: {settlement.settled_count}")
            elif cmd.startswith("book"):
                parts = cmd.split()
                symbol = parts[1].upper() if len(parts) > 1 else "AAPL"
                depth = MatchingEngine.get_book_depth(symbol)
                bids = depth.get("bids", [])
                asks = depth.get("asks", [])
                print(f"\n  ORDER BOOK: {symbol}")
                print("  BIDS:")
                for price, qty in bids[:5] if bids else [("--", "--")]:
                    print(f"    {qty:>6} @ ${price}")
                print("  ASKS:")
                for price, qty in asks[:5] if asks else [("--", "--")]:
                    print(f"    {qty:>6} @ ${price}")
            else:
                order = parse_order_string(user_input, trader_id)
                if order:
                    event = Event(event_type="ORDER_SUBMITTED", payload=order)
                    await backend.enqueue(event)
                    price_str = order["price"] or "MKT"
                    side = order["side"]
                    qty = order["quantity"]
                    sym = order["symbol"]
                    print(f"  ✓ Submitted: {side} {qty} {sym} @ {price_str}")
                    await asyncio.sleep(0.5)  # Allow spine to process
                else:
                    print("  ✗ Invalid format. Use: BUY 100 AAPL @ 150.50 or SELL 50 TSLA MKT")
    finally:
        spine.stop()
        await spine_task


if __name__ == "__main__":
    main()
