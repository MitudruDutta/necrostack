# Trading Order Book - NecroStack Example

A real-time order matching engine demonstrating NecroStack's full capabilities under high-throughput scenarios.

## Architecture

```
ORDER_SUBMITTED
       │
       ▼
┌──────────────────┐
│  ValidateOrder   │──► ORDER_REJECTED (invalid)
└──────────────────┘
       │ valid
       ▼
ORDER_VALIDATED
       │
       ▼
┌──────────────────┐
│  MatchingEngine  │──► Matches against order book
└──────────────────┘
       │
       ├──► ORDER_FILLED (full match)
       ├──► ORDER_PARTIAL_FILL (partial match)
       ├──► ORDER_QUEUED (no match, added to book)
       └──► TRADE_EXECUTED (for each match)
                │
                ▼
┌──────────────────┐
│  SettlementOrgan │──► SETTLEMENT_COMPLETE / SETTLEMENT_FAILED
└──────────────────┘
                │
                ▼
┌──────────────────┐
│  RiskManager     │──► RISK_ALERT (position limits, etc.)
└──────────────────┘
                │
                ▼
┌──────────────────┐
│   AuditTrail     │──► Records all events
└──────────────────┘
```

## Features Demonstrated

| Feature | Implementation |
|---------|----------------|
| Complex state | `MatchingEngine` maintains live order book |
| Multi-event emission | Single order can trigger multiple fills |
| Async handlers | `SettlementOrgan` simulates clearing house latency |
| Branching logic | Orders route to FILLED/PARTIAL/QUEUED |
| DLQ | Failed settlements go to dead letter queue |
| Circuit breaker | Simulated exchange outages |
| Handler timeout | Long-running settlement with timeout |
| Retry mode | Transient settlement failures retry |

## Order Types

- **LIMIT**: Execute at specified price or better
- **MARKET**: Execute immediately at best available price

## Event Types

| Event | Description |
|-------|-------------|
| `ORDER_SUBMITTED` | New order from trader |
| `ORDER_VALIDATED` | Order passed validation |
| `ORDER_REJECTED` | Order failed validation |
| `ORDER_FILLED` | Order completely filled |
| `ORDER_PARTIAL_FILL` | Order partially filled |
| `ORDER_QUEUED` | Order added to book (no match) |
| `ORDER_CANCELLED` | Order removed from book |
| `TRADE_EXECUTED` | A trade occurred (buyer + seller) |
| `SETTLEMENT_COMPLETE` | Trade settled successfully |
| `SETTLEMENT_FAILED` | Settlement failed (goes to DLQ) |
| `RISK_ALERT` | Position/exposure limit breached |

## Running

```bash
cd examples/trading_orderbook

# Demo with sample orders
python main.py

# Load orders from JSON file
python main.py --file sample_orders.json

# Load orders from CSV file
python main.py --file sample_orders.csv

# Interactive mode - enter orders manually
python main.py --interactive
python main.py -i --trader alice

# Stress test with random orders
python main.py --stress --orders 1000
```

## Interactive Mode

```
> BUY 100 AAPL @ 150.50    # Limit order
> SELL 50 TSLA MKT         # Market order
> book AAPL                 # Show order book
> stats                     # Show statistics
> quit                      # Exit
```

## File Formats

**JSON** (`sample_orders.json`):
```json
{
  "orders": [
    {"trader_id": "alice", "symbol": "AAPL", "side": "BUY", "order_type": "LIMIT", "quantity": 100, "price": 149.50},
    {"trader_id": "bob", "symbol": "AAPL", "side": "SELL", "order_type": "MARKET", "quantity": 50, "price": 0}
  ]
}
```

**CSV** (`sample_orders.csv`):
```csv
trader_id,symbol,side,order_type,quantity,price
alice,AAPL,BUY,LIMIT,100,149.50
bob,AAPL,SELL,MARKET,50,0
```
