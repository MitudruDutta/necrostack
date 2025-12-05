"""Audit trail organ for compliance logging."""

import threading
from collections import deque
from datetime import UTC, datetime

from necrostack.core.event import Event
from necrostack.core.organ import Organ

DEFAULT_MAX_LOG_SIZE = 100_000


class AuditTrail(Organ):
    """Records all significant events for compliance."""

    listens_to = [
        "ORDER_VALIDATED",
        "ORDER_REJECTED",
        "ORDER_FILLED",
        "ORDER_PARTIAL_FILL",
        "ORDER_QUEUED",
        "TRADE_EXECUTED",
        "SETTLEMENT_COMPLETE",
        "RISK_ALERT",
    ]

    def __init__(self, max_log_size: int = DEFAULT_MAX_LOG_SIZE):
        super().__init__()
        self.log: deque[dict] = deque(maxlen=max_log_size)
        self._lock = threading.Lock()
        self.stats = {
            "orders_validated": 0,
            "orders_rejected": 0,
            "orders_filled": 0,
            "orders_partial": 0,
            "orders_queued": 0,
            "trades_executed": 0,
            "settlements": 0,
            "risk_alerts": 0,
        }

    def handle(self, event: Event) -> None:
        try:
            record = {
                "event_id": event.id,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "recorded_at": datetime.now(UTC).isoformat(),
                "payload_summary": self._summarize(event),
            }
        except Exception as e:
            event_id = getattr(event, "id", None)
            raw_ts = getattr(event, "timestamp", None)
            if hasattr(raw_ts, "isoformat"):
                ts_str = raw_ts.isoformat()
            elif raw_ts:
                ts_str = str(raw_ts)
            else:
                ts_str = "unknown"
            record = {
                "event_id": event_id,
                "event_type": getattr(event, "event_type", "unknown"),
                "timestamp": ts_str,
                "recorded_at": datetime.now(UTC).isoformat(),
                "payload_summary": f"Error summarizing: {e}",
            }

        with self._lock:
            self.log.append(record)

        match event.event_type:
            case "ORDER_VALIDATED":
                self.stats["orders_validated"] += 1
            case "ORDER_REJECTED":
                self.stats["orders_rejected"] += 1
            case "ORDER_FILLED":
                self.stats["orders_filled"] += 1
            case "ORDER_PARTIAL_FILL":
                self.stats["orders_partial"] += 1
            case "ORDER_QUEUED":
                self.stats["orders_queued"] += 1
            case "TRADE_EXECUTED":
                self.stats["trades_executed"] += 1
            case "SETTLEMENT_COMPLETE":
                self.stats["settlements"] += 1
            case "RISK_ALERT":
                self.stats["risk_alerts"] += 1

    def _summarize(self, event: Event) -> str:
        p = event.payload
        match event.event_type:
            case "ORDER_VALIDATED":
                side = p.get("side", "?")
                qty = p.get("quantity", 0)
                sym = p.get("symbol", "?")
                price = p.get("price", "MKT")
                return f"{side} {qty} {sym} @ {price}"
            case "ORDER_REJECTED":
                return f"Rejected: {p.get('reason', 'unknown')}"
            case "ORDER_FILLED":
                avg_price = p.get("avg_price", 0.0)
                return f"Filled {p.get('quantity', 0)} {p.get('symbol', '?')} @ {avg_price:.2f}"
            case "ORDER_PARTIAL_FILL":
                filled = p.get("filled_quantity", 0)
                orig = p.get("original_quantity", 0)
                sym = p.get("symbol", "?")
                return f"Partial {filled}/{orig} {sym}"
            case "ORDER_QUEUED":
                side = p.get("side", "?")
                qty = p.get("quantity", 0)
                sym = p.get("symbol", "?")
                price = p.get("price", "MKT")
                return f"Queued {side} {qty} {sym} @ {price}"
            case "TRADE_EXECUTED":
                trade_id = p.get("trade_id", "-")
                qty = p.get("quantity", 0)
                sym = p.get("symbol", "?")
                price = p.get("price", 0)
                return f"Trade {trade_id}: {qty} {sym} @ {price}"
            case "SETTLEMENT_COMPLETE":
                total = p.get("total_value", 0.0)
                return f"Settled {p.get('trade_id', '-')}: ${total:.2f}"
            case "RISK_ALERT":
                return f"Alerts: {len(p.get('alerts', []))}"
            case _:
                return str(p)[:50]

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("AUDIT TRAIL SUMMARY")
        print("=" * 60)
        for key, val in self.stats.items():
            print(f"  {key.replace('_', ' ').title()}: {val}")
        print("=" * 60)
