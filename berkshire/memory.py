"""Decision log (TradingAgents file format), settlement and past context (REQ-MEM)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from .config import atomic_write
from .decisions import parse_rating

SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
_DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
_REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)


class DecisionLog:
    def __init__(self, path: Path, max_entries: int | None = None):
        self.path = Path(path).expanduser()
        self.max_entries = max_entries

    # -- write ---------------------------------------------------------------
    def store(self, ticker: str, trade_date: str, decision: str) -> bool:
        """Append a pending entry; a second one for ticker+date is a no-op (REQ-MEM-02)."""
        text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        prefix = f"[{trade_date} | {ticker} |"
        if any(line.startswith(prefix) and line.endswith("]") for line in text.splitlines()):
            return False
        entry = f"[{trade_date} | {ticker} | {parse_rating(decision)} | pending]\n\nDECISION:\n{decision}{SEPARATOR}"
        atomic_write(self.path, text + entry)
        return True

    def apply_outcomes(self, updates: list[dict]) -> int:
        """Resolve pending entries in one atomic rewrite (REQ-MEM-04). Returns count applied."""
        if not self.path.exists() or not updates:
            return 0
        todo = {(u["trade_date"], u["ticker"]): u for u in updates}
        blocks, applied = [], 0
        for block in self.path.read_text(encoding="utf-8").split(SEPARATOR):
            stripped = block.strip()
            lines = stripped.splitlines()
            tag = lines[0].strip() if lines else ""
            key = next((k for k in todo if tag.startswith(f"[{k[0]} | {k[1]} |")
                        and tag.endswith("| pending]")), None)
            if key is None:
                blocks.append(block)
                continue
            u = todo.pop(key)
            rating = [f.strip() for f in tag[1:-1].split("|")][2]
            new_tag = (f"[{u['trade_date']} | {u['ticker']} | {rating} | {u['raw_return']:+.1%} | "
                       f"{u['alpha_return']:+.1%} | {u['holding_days']}d")
            if u.get("resolution_date"):
                new_tag += f" | resolved:{u['resolution_date']}"
            rest = "\n".join(lines[1:]).lstrip()
            blocks.append(f"{new_tag}]\n\n{rest}\n\nREFLECTION:\n{u['reflection'].strip()}")
            applied += 1
        if applied:
            atomic_write(self.path, SEPARATOR.join(self._rotate(blocks)))
        return applied

    def _rotate(self, blocks: list[str]) -> list[str]:
        """Drop the oldest resolved blocks beyond max_entries; pending are kept (REQ-MEM-06)."""
        if not self.max_entries or self.max_entries <= 0:
            return blocks
        resolved = [b for b in blocks if b.strip() and not b.strip().splitlines()[0].endswith("| pending]")]
        drop = set(map(id, resolved[: max(0, len(resolved) - self.max_entries)]))
        return [b for b in blocks if id(b) not in drop]

    # -- read ----------------------------------------------------------------
    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for raw in self.path.read_text(encoding="utf-8").split(SEPARATOR):
            e = self._parse(raw.strip())
            if e:
                out.append(e)
        return out

    def pending(self, ticker: str | None = None) -> list[dict]:
        return [e for e in self.entries() if e["pending"] and (ticker is None or e["ticker"] == ticker)]

    @staticmethod
    def _parse(raw: str) -> dict | None:
        lines = raw.splitlines()
        if not lines or not (lines[0].startswith("[") and lines[0].endswith("]")):
            return None
        f = [x.strip() for x in lines[0][1:-1].split("|")]
        if len(f) < 4:
            return None
        body = "\n".join(lines[1:])
        d, r = _DECISION_RE.search(body), _REFLECTION_RE.search(body)
        return {
            "date": f[0], "ticker": f[1], "rating": f[2], "pending": f[3] == "pending",
            "raw": None if f[3] == "pending" else f[3],
            "alpha": f[4] if len(f) > 4 else None,
            "holding": f[5] if len(f) > 5 else None,
            "resolved": next((x[9:] for x in f[6:] if x.startswith("resolved:")), None),
            "decision": d.group(1).strip() if d else "",
            "reflection": r.group(1).strip() if r else "",
        }

    def past_context(self, ticker: str, as_of: str | None = None, n_same: int = 5, n_cross: int = 3) -> str:
        """Lessons for the Portfolio Manager, point-in-time filtered (REQ-MEM-05)."""
        entries = [e for e in self.entries() if not e["pending"]]
        if as_of is not None:
            entries = [e for e in entries if e["resolved"] and e["resolved"] <= as_of]
        same, cross = [], []
        for e in reversed(entries):
            if e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif e["ticker"] != ticker and len(cross) < n_cross:
                cross.append(e)
        parts = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            for e in same:
                tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'} | {e['alpha'] or 'n/a'} | {e['holding'] or 'n/a'}]"
                parts.append("\n\n".join(x for x in (tag, f"DECISION:\n{e['decision']}",
                                                     e["reflection"] and f"REFLECTION:\n{e['reflection']}") if x))
        if cross:
            parts.append("Recent cross-ticker lessons:")
            for e in cross:
                body = e["reflection"] or (e["decision"][:300] + ("..." if len(e["decision"]) > 300 else ""))
                parts.append(f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'}]\n{body}")
        return "\n\n".join(parts)


# --- settlement (REQ-MEM-03) -----------------------------------------------

def resolve_benchmark(ticker: str, cfg: dict) -> str:
    if cfg.get("benchmark_ticker"):
        return cfg["benchmark_ticker"]
    t = ticker.upper()
    bmap = cfg.get("benchmark_map", {})
    for suffix, bench in bmap.items():
        if suffix and t.endswith(suffix.upper()):
            return bench
    return bmap.get("", "SPY")


def compute_returns(stock, bench, holding_days: int):
    """(raw, alpha, resolution_date) from two close series starting at the trade date, or None."""
    if len(stock) <= holding_days or len(bench) <= holding_days:
        return None
    raw = float((stock.iloc[holding_days] - stock.iloc[0]) / stock.iloc[0])
    b = float((bench.iloc[holding_days] - bench.iloc[0]) / bench.iloc[0])
    return raw, raw - b, stock.index[holding_days].strftime("%Y-%m-%d")


def settle_candidates(log: DecisionLog, cfg: dict, tickers: list[str] | None, closes) -> list[dict]:
    """Pending entries whose holding window has traded, with returns filled in.

    ``closes(symbol, start, end)`` returns a date-indexed close Series; injected so
    tests run offline. Entries not yet settleable are skipped (retry next run).
    """
    days = int(cfg["holding_period_days"])
    out = []
    for e in log.pending():
        if tickers is not None and e["ticker"] not in tickers:
            continue
        start = datetime.strptime(e["date"], "%Y-%m-%d")
        end = (start + timedelta(days=round(days * 7 / 5) + 7)).strftime("%Y-%m-%d")
        bench = resolve_benchmark(e["ticker"], cfg)
        try:
            res = compute_returns(closes(e["ticker"], e["date"], end), closes(bench, e["date"], end), days)
        except Exception:  # noqa: BLE001 - unreachable/delisted: stays pending
            res = None
        if res is None:
            continue
        raw, alpha, resolved = res
        out.append({"ticker": e["ticker"], "trade_date": e["date"], "raw_return": raw,
                    "alpha_return": alpha, "holding_days": days, "resolution_date": resolved,
                    "benchmark": bench, "decision": e["decision"]})
    return out


def reflection_prompt(c: dict) -> str:
    """Input for the Reflector agent (TradingAgents reflection.py)."""
    return (f"The outcome covers {c['holding_days']} trading days after the analysis date, which may be "
            f"shorter than the horizon the decision was written for.\n\n"
            f"Raw return over {c['holding_days']} trading days: {c['raw_return']:+.1%}\n"
            f"Alpha vs {c['benchmark']}: {c['alpha_return']:+.1%}\n\nFinal Decision:\n{c['decision']}")
