"""Point-in-time data tools the analysts call via `berkshire data --run RUN_DIR <tool> ...`.

Every dated tool clamps to the run's trade date (REQ-DATA-01), and returns a
readable string, never a traceback (REQ-DATA-06). yfinance access goes through
`_ticker()` so tests can substitute an offline fake.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

INDICATORS = {
    "close_50_sma": "50 SMA: medium-term trend",
    "close_200_sma": "200 SMA: long-term trend benchmark",
    "close_10_ema": "10 EMA: responsive short-term average",
    "macd": "MACD line (EMA12 - EMA26)",
    "macds": "MACD signal (EMA9 of MACD)",
    "macdh": "MACD histogram",
    "rsi": "RSI(14), Wilder smoothing",
    "boll": "Bollinger middle (20 SMA)",
    "boll_ub": "Bollinger upper band (+2 sd)",
    "boll_lb": "Bollinger lower band (-2 sd)",
    "atr": "ATR(14), Wilder smoothing",
    "vwma": "20-period volume-weighted moving average",
}
SNAPSHOT_INDICATORS = ("close_10_ema", "close_50_sma", "close_200_sma", "rsi", "boll", "boll_ub",
                       "boll_lb", "macd", "macds", "macdh", "atr")
FILING_LAG = {"quarterly": 45, "annual": 90}  # REQ-DATA-04
CURRENT_NOTE = "(Source describes the instrument as of today, not necessarily as of {date}.)"


# --- no-data sentinels (REQ-DATA-06) ---------------------------------------
# Every "nothing to report" answer starts with one of these, so the analyst cannot
# mistake it for a finding or fill the gap from memory (TradingAgents #1408).
NO_DATA = "NO_DATA_AVAILABLE"        # the source has nothing for this instrument/date
UNAVAILABLE = "DATA_UNAVAILABLE"     # the call failed (network, vendor error, bug)
DIRECTIVE = "Report this data as unavailable; do not estimate, recall or fabricate values for it."


class NoData(ValueError):
    """The source answered, with nothing usable for this instrument and date."""


def no_data(message: str) -> str:
    return f"{NO_DATA}: {message} {DIRECTIVE}"


def unavailable(message: str) -> str:
    return f"{UNAVAILABLE}: {message} {DIRECTIVE}"


def _ticker(symbol: str):
    import yfinance as yf
    return yf.Ticker(symbol)


def _d(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# --- date clamping (REQ-DATA-01) -------------------------------------------

def as_of(requested: str | None, trade_date: str) -> str:
    """The model's date, but never later than the run's trade date."""
    try:
        return min(_d(requested), _d(trade_date)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return trade_date


def as_of_window(start: str | None, end: str | None, trade_date: str) -> tuple[str, str]:
    end = as_of(end, trade_date)
    try:
        start = min(_d(start), _d(end)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        start = (_d(end) - timedelta(days=30)).strftime("%Y-%m-%d")
    return start, end


# --- prices ----------------------------------------------------------------

def ohlcv(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Daily bars with start <= date <= end (inclusive), naive DatetimeIndex."""
    df = _ticker(symbol).history(start=start, end=(_d(end) + timedelta(days=1)).strftime("%Y-%m-%d"),
                                 auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[df.index <= pd.Timestamp(end)][["Open", "High", "Low", "Close", "Volume"]]


def check_listed(symbol: str, trade_date: str) -> bool | None:
    """True if Yahoo has daily bars in the 30 days up to trade_date, False if none, None if unreachable."""
    try:
        return not ohlcv(symbol, (_d(trade_date) - timedelta(days=30)).strftime("%Y-%m-%d"), trade_date).empty
    except Exception:  # noqa: BLE001 - network trouble is not "not listed"
        return None


def closes(symbol: str, start: str, end: str) -> pd.Series:
    return ohlcv(symbol, start, end)["Close"]


def _wilder(s: pd.Series, n: int = 14) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()


def compute_indicator(df: pd.DataFrame, name: str) -> pd.Series:
    c = df["Close"]
    if name == "close_50_sma":
        return c.rolling(50).mean()
    if name == "close_200_sma":
        return c.rolling(200).mean()
    if name == "close_10_ema":
        return c.ewm(span=10, adjust=False).mean()
    if name in ("macd", "macds", "macdh"):
        macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
        sig = macd.ewm(span=9, adjust=False).mean()
        return {"macd": macd, "macds": sig, "macdh": macd - sig}[name]
    if name == "rsi":
        delta = c.diff()
        gain, loss = _wilder(delta.clip(lower=0)), _wilder(-delta.clip(upper=0))
        return 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    if name in ("boll", "boll_ub", "boll_lb"):
        mid, sd = c.rolling(20).mean(), c.rolling(20).std()
        return {"boll": mid, "boll_ub": mid + 2 * sd, "boll_lb": mid - 2 * sd}[name]
    if name == "atr":
        prev = c.shift(1)
        tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
        return _wilder(tr)
    if name == "vwma":
        return (c * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()
    raise ValueError(f"Unknown indicator {name!r}. Valid indicators: {', '.join(INDICATORS)}")


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _history_for(symbol: str, trade_date: str) -> pd.DataFrame:
    # ~400 calendar days so the 200 SMA has enough rows.
    start = (_d(trade_date) - timedelta(days=400)).strftime("%Y-%m-%d")
    df = ohlcv(symbol, start, trade_date)
    if df.empty:
        raise NoData(f"No OHLCV data for {symbol} on or before {trade_date}.")
    return df


def tool_stock(symbol: str, start: str, end: str, trade_date: str) -> str:
    start, end = as_of_window(start, end, trade_date)
    df = ohlcv(symbol, start, end)
    if df.empty:
        return no_data(f"No price data for {symbol} between {start} and {end}.")
    return f"# {symbol} daily OHLCV {start}..{end} (no rows after {trade_date})\n" + df.round(4).to_csv()


def tool_indicators(symbol: str, names: str, curr_date: str | None, look_back_days: int, trade_date: str) -> str:
    curr = as_of(curr_date, trade_date)
    df = _history_for(symbol, curr)
    out = []
    for name in [n.strip().lower() for n in names.split(",") if n.strip()]:
        try:
            series = compute_indicator(df, name)
        except ValueError as exc:
            out.append(str(exc))
            continue
        window = series[series.index >= pd.Timestamp(curr) - timedelta(days=int(look_back_days))]
        rows = "\n".join(f"{i:%Y-%m-%d}: {_fmt(float(v))}" for i, v in window.items())
        out.append(f"## {name} values from {window.index.min():%Y-%m-%d} to {curr}:\n{rows}\n\n{INDICATORS[name]}")
    return "\n\n".join(out)


def latest_atr(symbol: str, trade_date: str) -> float | None:
    try:
        v = compute_indicator(_history_for(symbol, trade_date), "atr").iloc[-1]
        return None if pd.isna(v) else float(v)
    except Exception:  # noqa: BLE001
        return None


def tool_snapshot(symbol: str, curr_date: str | None, trade_date: str, look_back_days: int = 30) -> str:
    """Ground-truth snapshot (REQ-DATA-02)."""
    curr = as_of(curr_date, trade_date)
    df = _history_for(symbol, curr)
    last = df.iloc[-1]
    lines = [f"## Verified market data snapshot for {symbol.upper()}", "",
             f"- Requested analysis date: {curr}", f"- Latest trading row used: {df.index[-1]:%Y-%m-%d}",
             "- Rows after the requested analysis date are excluded before verification.", "",
             "### Latest verified OHLCV row", "", "| Field | Value |", "|---|---:|"]
    lines += [f"| {f} | {_fmt(float(last[f]))} |" for f in ("Open", "High", "Low", "Close", "Volume")]
    lines += ["", "### Verified technical indicators (latest row)", "", "| Indicator | Value |", "|---|---:|"]
    for name in SNAPSHOT_INDICATORS:
        lines.append(f"| {name} | {_fmt(float(compute_indicator(df, name).iloc[-1]))} |")
    recent = df.tail(max(1, min(int(look_back_days), 30)))
    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "", "| Date | Close |", "|---|---:|"]
    lines += [f"| {i:%Y-%m-%d} | {_fmt(float(r['Close']))} |" for i, r in recent.iterrows()]
    lines += ["", "Use this snapshot as the source of truth for exact OHLCV, price-level, and indicator-value "
              "claims. If another tool output conflicts with it, flag the discrepancy rather than inventing a "
              "reconciled number. Do not claim historical validation, support/resistance bounces, or exact "
              "percentage moves unless directly supported by tool output with concrete dates and prices."]
    return "\n".join(lines)


# --- identity & fundamentals -----------------------------------------------

def profile(symbol: str) -> dict:
    """Identity for REQ-CTX-01; {} on any failure (fail open)."""
    try:
        info = _ticker(symbol).info or {}
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    name = info.get("longName") or info.get("shortName")
    if isinstance(name, str) and name.strip():
        out["company_name"] = name.strip()
    for src, dst in (("sector", "sector"), ("industry", "industry"), ("exchange", "exchange"), ("quoteType", "quote_type")):
        v = info.get(src)
        if isinstance(v, str) and v.strip() and v.strip().lower() not in ("none", "n/a"):
            out[dst] = v.strip()
    return out


_FUNDAMENTAL_FIELDS = ("longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE", "pegRatio",
                       "priceToBook", "trailingEps", "forwardEps", "dividendYield", "beta", "profitMargins",
                       "operatingMargins", "returnOnEquity", "revenueGrowth", "earningsGrowth", "totalRevenue",
                       "totalDebt", "totalCash", "freeCashflow", "fiftyTwoWeekHigh", "fiftyTwoWeekLow")


IDENTITY_FIELDS = ("longName", "sector", "industry")


def tool_fundamentals(symbol: str, trade_date: str) -> str:
    """Company fundamentals. On a past date only identity is shown: Yahoo reports valuation,
    margins, growth, balance and 52-week figures as of today, which would leak what happened
    after the trade date (REQ-DATA-07)."""
    info = _ticker(symbol).info or {}
    past = trade_date < today()
    fields = IDENTITY_FIELDS if past else _FUNDAMENTAL_FIELDS
    rows = [f"| {k} | {info[k]} |" for k in fields if info.get(k) is not None]
    if not rows:
        return no_data(f"No fundamentals for {symbol}.")
    out = f"# {symbol} company fundamentals {CURRENT_NOTE.format(date=trade_date) if past else ''}\n\n"
    out += "| Field | Value |\n|---|---|\n" + "\n".join(rows)
    if past:
        out += (f"\n\nValuation, margins, growth, balance-sheet and 52-week figures are withheld: the source "
                f"reports them as of today, which would leak information from after {trade_date}. Use `valuation` "
                f"for market cap, P/E and P/B as of {trade_date}, and the filed statements for everything else.")
    return out


# --- point-in-time valuation (REQ-DATA-08) ----------------------------------

VALUATION_MAX_AGE_DAYS = 400   # oldest statement period accepted as an input
BASIS_TOLERANCE = 0.25         # net income / EPS must be within 25% of the share count


def _filed_values(t, attr: str, row: str, freq: str, trade_date: str) -> list[tuple[pd.Timestamp, float]]:
    """(period end, value) for one statement row, filed by the trade date, newest first, NaNs dropped."""
    df = getattr(t, ("quarterly_" if freq == "quarterly" else "") + attr, None)
    if df is None or df.empty or row not in df.index:
        return []
    df = filter_filed(df, freq, trade_date)
    vals = [(pd.Timestamp(c).tz_localize(None), float(df.loc[row, c])) for c in df.columns]
    return sorted(((d, v) for d, v in vals if not pd.isna(v)), key=lambda x: x[0], reverse=True)


def _basis_ok(t, attr_freq: str, period: pd.Timestamp, eps: float, trade_date: str) -> bool:
    """Net income / EPS ≈ diluted shares for the same period, i.e. EPS and shares share a split basis."""
    income = dict(_filed_values(t, "income_stmt", "Net Income", attr_freq, trade_date))
    shares = dict(_filed_values(t, "income_stmt", "Diluted Average Shares", attr_freq, trade_date))
    if period not in income or period not in shares or not eps or not shares[period]:
        return True  # nothing to check against; the EPS is used as reported
    return abs(income[period] / eps / shares[period] - 1) <= BASIS_TOLERANCE


def valuation(symbol: str, trade_date: str) -> dict:
    """Market cap, P/E and P/B as of trade_date from the close and statements filed by then.

    Yahoo restates prices, EPS and share counts to today's split basis, so every input is on one
    basis and the ratios are consistent across splits; a net-income/EPS/share-count check guards
    against an input that is not. Returns a dict of figures and the notes explaining each.
    """
    t = _ticker(symbol)
    limit = pd.Timestamp(trade_date) - timedelta(days=VALUATION_MAX_AGE_DAYS)
    out: dict = {"symbol": symbol, "trade_date": trade_date, "notes": []}

    bars = ohlcv(symbol, (_d(trade_date) - timedelta(days=10)).strftime("%Y-%m-%d"), trade_date)
    if bars.empty:
        out["notes"].append(f"No close on or within 10 days before {trade_date}: valuation unavailable.")
        return out
    out["close"], out["close_date"] = float(bars["Close"].iloc[-1]), bars.index[-1].strftime("%Y-%m-%d")

    # EPS: four filed quarters summed (TTM), else the latest filed fiscal year. Never one quarter.
    quarters = [(d, v) for d, v in _filed_values(t, "income_stmt", "Diluted EPS", "quarterly", trade_date) if d >= limit]
    annual = [(d, v) for d, v in _filed_values(t, "income_stmt", "Diluted EPS", "annual", trade_date) if d >= limit]
    if len(quarters) >= 4 and (quarters[0][0] - quarters[3][0]).days < 380:
        eps, eps_basis, freq, period = sum(v for _, v in quarters[:4]), \
            f"TTM, 4 filed quarters ending {quarters[0][0]:%Y-%m-%d}", "quarterly", None
    elif annual:
        (period, eps), freq = annual[0], "annual"
        eps_basis = f"fiscal year ending {period:%Y-%m-%d}"
    else:
        eps = None
        out["notes"].append(f"No diluted EPS filed within {VALUATION_MAX_AGE_DAYS} days before {trade_date}.")
    if eps is not None:
        checks = [(d, v) for d, v in quarters[:4]] if period is None else [(period, eps)]
        if all(_basis_ok(t, freq, d, v, trade_date) for d, v in checks):
            out["eps"], out["eps_basis"] = eps, eps_basis
        else:
            out["notes"].append("EPS and share count are on different split bases in the source: P/E unavailable.")

    # Shares and equity: the newest filed balance sheet, quarterly or annual.
    for key, row in (("shares", "Ordinary Shares Number"), ("equity", "Stockholders Equity")):
        cands = _filed_values(t, "balance_sheet", row, "quarterly", trade_date) + \
            _filed_values(t, "balance_sheet", row, "annual", trade_date)
        cands = [c for c in cands if c[0] >= limit]
        if cands:
            d, v = max(cands, key=lambda c: c[0])
            out[key], out[f"{key}_date"] = v, d.strftime("%Y-%m-%d")
        else:
            out["notes"].append(f"No {row.lower()} filed within {VALUATION_MAX_AGE_DAYS} days before {trade_date}.")

    if out.get("shares"):
        out["market_cap"] = out["close"] * out["shares"]
    if out.get("eps") is not None:
        out["pe"] = out["close"] / out["eps"] if out["eps"] > 0 else None  # n/m for losses
    if out.get("market_cap") and out.get("equity") is not None:
        out["pb"] = out["market_cap"] / out["equity"] if out["equity"] > 0 else None
    return out


def tool_valuation(symbol: str, trade_date: str) -> str:
    v = valuation(symbol, trade_date)
    money = lambda x: f"{x:,.0f}"  # noqa: E731
    rows = []
    if "close" in v:
        rows.append(f"| Close | {v['close']:.2f} | {v['close_date']} |")
    if "shares" in v:
        rows.append(f"| Shares outstanding | {money(v['shares'])} | balance sheet {v['shares_date']} |")
    if "market_cap" in v:
        rows.append(f"| Market cap | {money(v['market_cap'])} | close × shares |")
    if "eps" in v:
        rows.append(f"| Diluted EPS | {v['eps']:.2f} | {v['eps_basis']} |")
        pe = "n/m (negative earnings)" if v["pe"] is None else f"{v['pe']:.1f}"
        rows.append(f"| P/E | {pe} | close / EPS |")
    if "equity" in v:
        rows.append(f"| Stockholders' equity | {money(v['equity'])} | balance sheet {v['equity_date']} |")
    if "pb" in v:
        pb = "n/m (negative equity)" if v["pb"] is None else f"{v['pb']:.2f}"
        rows.append(f"| P/B | {pb} | market cap / equity |")
    if not rows:
        return no_data(f"No valuation figures for {symbol} as of {trade_date}. " + " ".join(v["notes"]))
    body = "| Figure | Value | Basis |\n|---|---:|---|\n" + "\n".join(rows)
    notes = "".join(f"\n- {n}" for n in v["notes"])
    return (f"# {symbol} valuation as of {trade_date} (point-in-time)\n\n{body}\n\n"
            f"Inputs are the close on or before {trade_date} and statements filed by then (filing date approximated "
            f"as period end + {FILING_LAG['quarterly']}/{FILING_LAG['annual']} days). Prices and per-share figures "
            f"are on today's split basis (the source restates history for later splits), so they can differ from "
            f"as-traded prices quoted in old news. No enterprise value: net debt is not point-in-time here."
            + (f"\n\nNotes:{notes}" if notes else ""))


def filter_filed(df: pd.DataFrame, freq: str, trade_date: str) -> pd.DataFrame:
    """Keep statement columns (period ends) filed by the trade date (REQ-DATA-04)."""
    lag = timedelta(days=FILING_LAG[freq])
    cols = [c for c in df.columns if pd.Timestamp(c).tz_localize(None) + lag <= pd.Timestamp(trade_date)]
    return df[cols]


def tool_statement(symbol: str, kind: str, freq: str, trade_date: str) -> str:
    freq = "annual" if freq == "annual" else "quarterly"
    attr = {"balance_sheet": "balance_sheet", "cashflow": "cashflow", "income_statement": "income_stmt"}[kind]
    t = _ticker(symbol)
    df = getattr(t, ("quarterly_" if freq == "quarterly" else "") + attr)
    if df is None or df.empty:
        return no_data(f"No {freq} {kind} data for {symbol}.")
    df = filter_filed(df, freq, trade_date)
    if df.empty:
        return no_data(f"No {freq} {kind} for {symbol} had been filed by {trade_date}.")
    df.columns = [pd.Timestamp(c).strftime("%Y-%m-%d") for c in df.columns]
    return (f"# {symbol} {freq} {kind} (periods filed by {trade_date}; filing date approximated as period end "
            f"+ {FILING_LAG[freq]} days)\n" + df.to_csv())


def tool_insider(symbol: str, trade_date: str) -> str:
    df = _ticker(symbol).insider_transactions
    if df is None or df.empty:
        return no_data(f"The source has no insider transactions for {symbol}.")
    if "Start Date" in df.columns:
        df = df[pd.to_datetime(df["Start Date"]).dt.tz_localize(None) <= pd.Timestamp(trade_date)]
    if df.empty:
        return no_data(f"No insider transactions for {symbol} on or before {trade_date}.")
    return f"# {symbol} insider transactions on or before {trade_date}\n" + df.head(30).to_csv(index=False)


# --- news (REQ-DATA-05) ----------------------------------------------------

def _news_item(raw: dict) -> dict:
    c = raw.get("content") or raw
    pub = c.get("pubDate") or c.get("providerPublishTime")
    if isinstance(pub, (int, float)):
        dt = datetime.fromtimestamp(pub, tz=UTC)
    else:
        try:
            dt = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    provider = c.get("provider")
    return {"title": c.get("title") or "", "summary": c.get("summary") or "",
            "publisher": (provider or {}).get("displayName") if isinstance(provider, dict) else c.get("publisher"),
            "date": dt}


def in_window(dt: datetime | None, start: str, end: str) -> bool:
    if dt is None:  # undated: only trusted for a live window
        return _d(end).date() >= datetime.now().date() - timedelta(days=1)
    dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    lo = _d(start).replace(tzinfo=UTC)
    return lo <= dt < _d(end).replace(tzinfo=UTC) + timedelta(days=1)


def coverage_gap(dates: list, start: str, end: str, source: str) -> str | None:
    """Marker when the feed could not observe the whole window."""
    now = datetime.now(UTC)
    oldest = min((d for d in dates if d is not None), default=now)
    if oldest.date() > _d(start).date():
        return (f"<{source} unavailable for {start}..{end}: it only serves recent items, "
                f"so this is not an absence of news>")
    return None


def format_news(items: list[dict], start: str, end: str, source: str, limit: int) -> str:
    kept = [i for i in items if in_window(i["date"], start, end)][:limit]
    lines = [f"### {i['title']} ({i['publisher'] or 'unknown'}, {i['date']:%Y-%m-%d})\n{i['summary']}"
             if i["date"] else f"### {i['title']} ({i['publisher'] or 'unknown'}, undated)\n{i['summary']}"
             for i in kept]
    gap = coverage_gap([i["date"] for i in items], start, end, source)
    if not lines:
        return gap or f"No {source} items between {start} and {end}."
    return "\n\n".join(([gap] if gap else []) + lines)


def tool_news(symbol: str, start: str, end: str, trade_date: str, limit: int = 20) -> str:
    start, end = as_of_window(start, end, trade_date)
    items = [_news_item(n) for n in (_ticker(symbol).news or [])]
    return f"## {symbol} news {start}..{end}\n\n" + format_news(items, start, end, "Yahoo Finance news", limit)


def tool_global_news(curr_date: str | None, trade_date: str, cfg: dict, look_back_days: int | None = None) -> str:
    import yfinance as yf
    end = as_of(curr_date, trade_date)
    start = (_d(end) - timedelta(days=look_back_days or cfg["global_news_lookback_days"])).strftime("%Y-%m-%d")
    items, seen = [], set()
    for q in cfg["global_news_queries"]:
        try:
            for raw in yf.Search(q, news_count=cfg["global_news_article_limit"]).news or []:
                item = _news_item(raw)
                if item["title"] not in seen:
                    seen.add(item["title"])
                    items.append(item)
        except Exception:  # noqa: S112 - one query failing is not the tool failing
            continue
    return f"## Global news {start}..{end}\n\n" + format_news(items, start, end, "Yahoo global news",
                                                              cfg["global_news_article_limit"])


TOOLS = ("stock", "indicators", "snapshot", "fundamentals", "valuation", "balance_sheet", "cashflow",
         "income_statement", "insider", "news", "global_news")
