"""The caller's book and eToro adapters (REQ-CTX-04, REQ-EXE-06/07, REQ-SCHED-01).

eToro MCP responses are saved to JSON by the skills and read here, so every
mapping is testable offline. Key lookups are tolerant (`_get`) because the MCP
relays upstream field names verbatim and some are casing-variant.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ASSET_FOREX, ASSET_COMMODITY, ASSET_INDEX, ASSET_STOCK, ASSET_ETF, ASSET_CRYPTO = 1, 2, 4, 5, 6, 10
_CLASS_SHARE = {"A", "B", "C"}  # BRK.B -> BRK-B on Yahoo
# eToro venue suffixes Yahoo spells differently: Zurich, Amsterdam, and US extended-hours listings.
_VENUE = {"ZU": ".SW", "NV": ".AS", "RTH": ""}


def _get(d: dict, *keys, default=None):
    """First present key, case-insensitive, searching one level of nesting too."""
    if not isinstance(d, dict):
        return default
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in lower and lower[k.lower()] is not None:
            return lower[k.lower()]
    for v in d.values():
        if isinstance(v, dict):
            found = _get(v, *keys)
            if found is not None:
                return found
    return default


# --- portfolio context -----------------------------------------------------


def render_portfolio(p: dict | None, ticker: str) -> str:
    """Block for Trader / risk team / PM. None = not provided, never flat (REQ-CTX-04)."""
    if p is None:
        return (
            "Portfolio context: not provided. You do not know the caller's current holdings or cash, "
            "so do not assume a flat book; give direction and sizing guidance in terms the caller can "
            "apply to their own position."
        )
    sym = ticker.strip().upper()
    held = position_in(p, sym)
    if held is None:
        lines = [f"- No current position in {sym}"]
    else:
        price = f", average price {held['average_price']:,.2f}" if held.get("average_price") else ""
        value = f", value {held['value']:,.2f}" if held.get("value") is not None else ""
        lines = [f"- Current position in {sym}: {held['quantity']:,.4g} units{price}{value}"]
    cur = f" {p['currency']}" if p.get("currency") else ""
    if p.get("equity") is not None:
        lines.append(f"- Total equity: {p['equity']:,.2f}{cur}")
    if p.get("cash") is not None:
        lines.append(f"- Cash available: {p['cash']:,.2f}{cur}")
    others = [q for q in p.get("positions", []) if q is not held]
    if others:
        lines.append("- Other positions: " + ", ".join(f"{q['ticker'].upper()} {q['quantity']:,.4g}" for q in others))
    return "Portfolio at the analysis date:\n" + "\n".join(lines)


def position_in(p: dict | None, ticker: str) -> dict | None:
    if not p:
        return None
    t = ticker.strip().upper()
    return next((q for q in p.get("positions", []) if t in (q["ticker"].upper(), str(q.get("etoro_symbol", "")).upper())), None)


def fingerprint(p: dict | None) -> str:
    if p is None:
        return "none"
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]


def load_portfolio_file(path: str | Path) -> dict:
    """User JSON in TradingAgents shape: {cash, currency, positions:[{ticker, quantity, average_price}]}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"portfolio file {path} is not usable: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("positions", []), list):
        raise ValueError(f"portfolio file {path} must be an object with a positions list")
    if "totals" in data or "holdings" in data:
        return from_etoro_summary(data)
    positions = []
    for q in data.get("positions", []):
        if "ticker" not in q or "quantity" not in q:
            raise ValueError(f"portfolio file {path}: each position needs ticker and quantity")
        positions.append(
            {
                "ticker": str(q["ticker"]).upper(),
                "quantity": float(q["quantity"]),
                "average_price": q.get("average_price"),
                "value": q.get("value"),
            }
        )
    return {"cash": data.get("cash"), "currency": data.get("currency"), "equity": data.get("equity"), "positions": positions}


# --- eToro mapping ---------------------------------------------------------


def yf_symbol(etoro_symbol: str, asset_type: int | None, symbol_map: dict) -> str | None:
    """eToro symbol -> Yahoo symbol, or None if unmappable (REQ-EXE-07)."""
    s = etoro_symbol.strip().upper()
    mapped = {k.upper(): v for k, v in symbol_map.items()}
    if s in mapped:
        return mapped[s]
    if asset_type == ASSET_CRYPTO:
        return f"{s}-USD"
    if asset_type == ASSET_FOREX:
        return f"{s}=X"
    if asset_type in (ASSET_COMMODITY, ASSET_INDEX):
        return None
    head, dot, tail = s.rpartition(".")
    if dot and tail in _CLASS_SHARE:
        return f"{head}-{tail}"
    if dot and tail in _VENUE:
        return head + _VENUE[tail]
    return s


_KINDS = {ASSET_CRYPTO: "crypto", ASSET_ETF: "etf", ASSET_INDEX: "index", ASSET_COMMODITY: "commodity", ASSET_FOREX: "fx"}


def asset_kind(asset_type: int | None, yf: str) -> str:
    """The analysis mode from eToro's asset type, known without a network call (REQ-FLOW-10/11)."""
    if yf.endswith("-USD"):
        return "crypto"
    return _KINDS.get(asset_type, "stock")


def from_etoro_summary(summary: dict) -> dict:
    """get-my-portfolio-summary (includePositions=true) -> portfolio context (REQ-EXE-06).

    Only direct holdings become positions; copied-trader mirrors are excluded so
    the gate can never try to close them (REQ-RISK-07).
    """
    totals = summary.get("totals") or {}
    positions = []
    for h in summary.get("holdings") or []:
        sym = _get(h, "symbol", "symbolName", "ticker")
        if not sym:
            continue
        rows = [r for r in (h.get("positions") or []) if not _get(r, "mirrorId", "isMirror")]
        units = _get(h, "units", "totalUnits")
        positions.append(
            {
                "ticker": str(sym).upper(),
                "etoro_symbol": str(sym).upper(),
                "instrument_id": _get(h, "instrumentId", "instrumentID"),
                "asset_type": _get(h, "assetTypeId", "instrumentTypeId", "instrumentTypeID"),
                "quantity": float(units if units is not None else sum(float(_get(r, "units", default=0)) for r in rows)),
                "average_price": _get(h, "averageOpenRate", "avgOpenRate", "openRate"),
                "value": _get(h, "currentValue", "value", "totalValue"),
                "position_ids": [
                    {"id": int(_get(r, "positionId", "positionID")), "units": float(_get(r, "units", default=0))}
                    for r in rows
                    if _get(r, "positionId", "positionID") is not None
                ],
            }
        )
    return {
        "cash": _get(totals, "availableCash", "credit"),
        "currency": summary.get("accountCurrency"),
        "equity": _get(totals, "totalValue", "equity"),
        "positions": positions,
    }


def universe(
    portfolio: dict | None, watchlists: dict | None, watchlist_name: str, symbol_map: dict, limit: int
) -> tuple[list[dict], list[str]]:
    """Holdings first, then the named watchlist; de-duplicated and capped (REQ-SCHED-01/04).

    Returns (instruments, skipped_reasons).
    """
    items, skipped, seen = [], [], set()

    def add(sym, iid, atype, source):
        if not sym:
            return
        y = yf_symbol(str(sym), atype, symbol_map)
        if y is None:
            skipped.append(f"{sym}: no Yahoo mapping for asset type {atype} (add it to symbol_map)")
            return
        if y in seen:
            return
        seen.add(y)
        items.append(
            {
                "etoro_symbol": str(sym).upper(),
                "instrument_id": iid,
                "ticker": y,
                "asset_type": asset_kind(atype, y),
                "source": source,
            }
        )

    for q in (portfolio or {}).get("positions", []):
        add(q.get("etoro_symbol") or q["ticker"], q.get("instrument_id"), q.get("asset_type"), "holding")

    lists = (watchlists or {}).get("watchlists") or {}
    lists = lists.get("watchlists", []) if isinstance(lists, dict) else lists
    chosen = next((w for w in lists if w.get("name") == watchlist_name), None)
    if watchlists is not None and chosen is None:
        skipped.append(f"watchlist {watchlist_name!r} not found")
    for it in (chosen or {}).get("items", []):
        if it.get("itemType") != "Instrument":
            continue
        m = it.get("market") or {}
        add(m.get("symbolName"), it.get("itemId"), m.get("assetTypeId"), "watchlist")

    if len(items) > limit:
        skipped += [f"{i['ticker']}: over max_tickers_per_tick={limit}" for i in items[limit:]]
        items = items[:limit]
    return items, skipped
