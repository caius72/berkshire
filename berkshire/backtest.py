"""Backtest grid and scoring (REQ-BT). Ports TradingAgents backtest.py.

Cells run the normal pipeline under an isolated BERKSHIRE_HOME, so the live
decision log and order queue are never touched and no orders are created
(REQ-BT-01/04). The decision log in that home is the results table.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .config import safe_component
from .data import today
from .decisions import REVIEW
from .memory import DecisionLog

DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
# REQ-BT-05: the data guards cannot stop the models from knowing how a past date turned out (upstream #805).
LOOKAHEAD = ("Point-in-time guards limit the data the agents see, not what the models learned in training: "
             "cells dated before the models' training cutoff are historically grounded simulations, not causal "
             "backtests. Only cells after the cutoff, or live runs, measure skill.")


def _canonical(date: str) -> datetime:
    try:
        parsed = datetime.strptime(str(date), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"grid dates must be in YYYY-MM-DD format, got {date!r}") from exc
    if parsed.strftime("%Y-%m-%d") != str(date):
        raise ValueError(f"grid dates must be in YYYY-MM-DD format, got {date!r}")
    return parsed


def iter_grid(start: str, end: str, every: int = 1) -> list[str]:
    s, e = _canonical(start), _canonical(end)
    if every < 1:
        raise ValueError("every must be at least 1")
    if e < s:
        raise ValueError(f"the grid ends before it starts: {end} is before {start}")
    last, out = min(e, _canonical(today())), []
    while s <= last:
        out.append(s.strftime("%Y-%m-%d"))
        s += timedelta(days=every)
    return out


def backtest_home(base: Path, run_id: str) -> Path:
    return Path(base) / "backtest" / safe_component(run_id)


def plan(tickers: list[str], dates: list[str], log: DecisionLog) -> dict:
    """Cells still to run; cells already in this run's log are skipped (REQ-BT-02)."""
    done = {(e["ticker"], e["date"]) for e in log.entries()}
    cells = [{"ticker": t.upper(), "date": d} for t in tickers for d in dates]
    todo = [c for c in cells if (c["ticker"], c["date"]) not in done]
    return {"cells": todo, "skipped": len(cells) - len(todo)}


def _alpha(entry: dict) -> float | None:
    try:
        return float((entry.get("alpha") or "").strip().rstrip("%")) / 100
    except ValueError:
        return None


def summarize(log: DecisionLog) -> dict:
    """Per-rating n, hit rate and mean alpha over settled cells (REQ-BT-03)."""
    entries = log.entries()
    scored = [(e, _alpha(e)) for e in entries if not e["pending"] and e["rating"] != REVIEW]
    scored = [(e, a) for e, a in scored if a is not None]
    by_rating = {}
    for rating in dict.fromkeys(e["rating"] for e, _ in scored):
        alphas = [a for e, a in scored if e["rating"] == rating]
        d = DIRECTION.get(rating, 0)
        by_rating[rating] = {"count": len(alphas),
                             "hit_rate": sum(a * d > 0 for a in alphas) / len(alphas) if d else None,
                             "mean_alpha": sum(alphas) / len(alphas)}
    unscored = sum(1 for e in entries if e["rating"] == REVIEW)
    return {"resolved": len(scored), "pending": len(entries) - len(scored) - unscored,
            "unscored": unscored, "by_rating": by_rating, "caveat": LOOKAHEAD}


def render(summary: dict) -> str:
    lines = [f"Resolved cells: {summary['resolved']} · pending: {summary['pending']}"
             + (f" · unscored: {summary['unscored']}" if summary["unscored"] else "")]
    for rating, s in summary["by_rating"].items():
        called = f"called the direction {s['hit_rate']:.0%}" if s["hit_rate"] is not None else "no direction claimed"
        lines.append(f"- {rating}: n={s['count']}, {called}, mean alpha {s['mean_alpha']:+.2%} vs the benchmark")
    if summary["pending"]:
        lines.append("\nPending cells are not scored above; re-run the settle step to settle them.")
    lines.append("One model sampling per cell and web/social sources are not archived, so these figures are "
                 "indicative rather than repeatable.")
    lines.append(summary["caveat"])
    return "\n".join(lines)
