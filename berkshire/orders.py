"""Risk gate (rating -> order intent) and the approval queue (REQ-RISK, REQ-EXE-04).

The gate can only shrink or veto. It never emits a short or leveraged order
(REQ-RISK-04). Placement happens only in /berkshire:approve after a human
approves the eToro confirmation block.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .config import atomic_write
from .etoro import position_in

TARGET_FRACTION = {"Buy": 1.0, "Overweight": 0.5}
STRENGTH = {"Sell": 0, "Underweight": 1, "Buy": 2, "Overweight": 3}  # queue priority, lower first


def gate(*, ticker: str, etoro_symbol: str | None, instrument_id, rating: str, portfolio: dict,
         ask: float | None, trader: dict | None, pm: dict | None, atr: float | None, cfg: dict) -> dict:
    """Return {"intent": dict|None, "reasons": [str]} for one completed run (REQ-RISK-01..05, 07)."""
    reasons: list[str] = []
    held = position_in(portfolio, etoro_symbol or ticker)
    base = {"ticker": ticker, "etoro_symbol": etoro_symbol or ticker, "instrument_id": instrument_id,
            "rating": rating, "account": cfg["account"]}

    if rating in ("Hold", "REVIEW") or rating not in STRENGTH:
        reasons.append(f"{rating}: no order" + (" (flagged for human review)" if rating == "REVIEW" else ""))
        return {"intent": None, "reasons": reasons}

    if rating in ("Sell", "Underweight"):
        ids = (held or {}).get("position_ids") or []
        if not ids:
            reasons.append(f"{rating}: no directly held position to reduce")
            return {"intent": None, "reasons": reasons}
        frac = 1.0 if rating == "Sell" else float(cfg["underweight_close_fraction"])
        closes = [{"position_id": p["id"], "units_to_deduct": None if frac >= 1 else round(p["units"] * frac, 6)}
                  for p in ids]
        reasons.append(f"{rating}: close {frac:.0%} of {len(ids)} position(s)")
        return {"intent": {**base, "kind": "close", "closes": closes}, "reasons": reasons}

    # Buy / Overweight: move toward target weight.
    equity, cash = portfolio.get("equity"), portfolio.get("cash")
    if not equity or cash is None:
        return {"intent": None, "reasons": ["portfolio equity/cash unknown: cannot size"]}
    if not ask or ask <= 0:
        return {"intent": None, "reasons": ["no live ask price: cannot size or place a stop"]}
    current = float((held or {}).get("value") or 0.0)
    target = TARGET_FRACTION[rating] * float(cfg["target_weight"]) * equity
    caps = {
        "distance to target": target - current,
        "max_order_pct": float(cfg["max_order_pct"]) * equity,
        "max_instrument_pct": float(cfg["max_instrument_pct"]) * equity - current,
        "min_cash_pct": cash - float(cfg["min_cash_pct"]) * equity,
    }
    binding = min(caps, key=caps.get)
    amount = round(caps[binding], 2)
    if amount < float(cfg["min_order_amount"]):
        return {"intent": None, "reasons": [f"{rating}: amount {amount:,.2f} below min_order_amount "
                                            f"(binding limit: {binding})"]}
    reasons.append(f"{rating}: amount {amount:,.2f} (binding limit: {binding})")

    stop = (trader or {}).get("stop_loss")
    if stop is not None and 0 < stop < ask:
        reasons.append(f"stop-loss {stop} from Trader")
    else:
        if stop is not None:
            reasons.append(f"Trader stop {stop} is not below ask {ask}: ignored")
        if not atr:
            reasons.append("veto: no valid stop-loss (no Trader stop, no ATR)")
            return {"intent": None, "reasons": reasons}
        stop = round(ask - float(cfg["atr_stop_multiple"]) * atr, 4)
        if stop <= 0:
            reasons.append("veto: ATR stop would be at or below zero")
            return {"intent": None, "reasons": reasons}
        reasons.append(f"stop-loss {stop} = ask - {cfg['atr_stop_multiple']} x ATR {atr:.4f}")

    tp = (pm or {}).get("price_target")
    take_profit = tp if tp is not None and tp > ask else None
    return {"intent": {**base, "kind": "open", "direction": "buy", "leverage": 1, "amount": amount,
                       "stop_loss_rate": stop, "take_profit_rate": take_profit, "ask": ask},
            "reasons": reasons}


# --- queue -----------------------------------------------------------------

OPEN_STATES = ("pending",)
TRANSITIONS = {"pending": {"approved", "rejected", "expired", "superseded"},
               "approved": {"placed", "failed", "pending_fill", "unknown"},
               "pending_fill": {"placed", "failed"}, "unknown": {"placed", "failed", "pending_fill"}}


class Queue:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def save(self, items: list[dict]) -> None:
        atomic_write(self.path, json.dumps(items, indent=2, default=str))

    def enqueue(self, intents: list[dict], run_tag: str, max_orders: int, now: datetime | None = None) -> list[dict]:
        """Queue up to max_orders intents, closes first, then strongest opens (REQ-RISK-06).

        A newer intent for the same instrument supersedes a pending one.
        """
        now = now or datetime.now()
        ranked = sorted(intents, key=lambda i: (i["kind"] != "close", STRENGTH.get(i["rating"], 9)))[:max_orders]
        items = self.load()
        for it in items:
            if it["status"] == "pending" and any(r["etoro_symbol"] == it["intent"]["etoro_symbol"] for r in ranked):
                it["status"] = "superseded"
                it["updated"] = now.isoformat(timespec="seconds")
        added = [{"id": uuid.uuid4().hex[:8], "created": now.isoformat(timespec="seconds"),
                  "updated": now.isoformat(timespec="seconds"), "run_tag": run_tag, "status": "pending",
                  "intent": i, "result": None} for i in ranked]
        self.save(items + added)
        return added

    def expire(self, ttl_hours: float, now: datetime | None = None) -> int:
        now = now or datetime.now()
        items, n = self.load(), 0
        for it in items:
            if it["status"] == "pending" and datetime.fromisoformat(it["created"]) + timedelta(hours=ttl_hours) < now:
                it["status"], it["updated"], n = "expired", now.isoformat(timespec="seconds"), n + 1
        if n:
            self.save(items)
        return n

    def mark(self, item_id: str, status: str, result=None, now: datetime | None = None) -> dict:
        items = self.load()
        it = next((i for i in items if i["id"] == item_id), None)
        if it is None:
            raise ValueError(f"no queue item {item_id!r}")
        if status not in TRANSITIONS.get(it["status"], set()):
            raise ValueError(f"cannot move {item_id} from {it['status']} to {status}")
        it["status"], it["updated"] = status, (now or datetime.now()).isoformat(timespec="seconds")
        if result is not None:
            it["result"] = result
        self.save(items)
        return it

    def pending(self) -> list[dict]:
        return [i for i in self.load() if i["status"] == "pending"]
