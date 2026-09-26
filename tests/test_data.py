"""Point-in-time data tools (offline, via the FakeTicker in conftest)."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from conftest import FakeTicker, bars, new_run

from berkshire import data
from berkshire.cli import main

TD = "2026-09-10"


def test_date_clamping():
    """TST-DATA-01: Requested dates and windows are clamped to the trade date [REQ-DATA-01]"""
    assert data.as_of("2026-12-31", TD) == TD
    assert data.as_of("2026-09-01", TD) == "2026-09-01"
    assert data.as_of(None, TD) == TD and data.as_of("garbage", TD) == TD
    assert data.as_of_window("2026-09-01", "2026-12-31", TD) == ("2026-09-01", TD)
    assert data.as_of_window("2026-12-01", "2026-12-31", TD) == (TD, TD)
    out = data.tool_stock("NVDA", "2026-09-01", "2026-12-31", TD)
    rows = [r.split(",")[0] for r in out.splitlines()[2:]]
    assert rows[-1] == TD and all(r <= TD for r in rows)


def test_snapshot(tmp_path):
    """TST-DATA-02: Snapshot uses the last row on/before the trade date, fixed indicators, <=30 closes [REQ-DATA-02]"""
    out = data.tool_snapshot("NVDA", "2026-12-31", TD)
    assert f"- Latest trading row used: {TD}" in out
    for name in data.SNAPSHOT_INDICATORS:
        assert f"| {name} |" in out
    close_rows = [ln for ln in out.split("### Recent verified closes")[1].splitlines() if ln.startswith("| 2026")]
    assert len(close_rows) == 30 and close_rows[-1].startswith(f"| {TD} |")
    assert "source of truth" in out


def test_indicator_values():
    """TST-DATA-03: Indicators match hand-computed values; unknown names list the valid ones [REQ-DATA-03]"""
    df = bars()
    c = df["Close"]
    assert data.compute_indicator(df, "close_50_sma").iloc[-1] == pytest.approx(c.tail(50).mean())
    assert data.compute_indicator(df, "atr").iloc[-1] == pytest.approx(2.0, rel=1e-3)  # H-L = 2 dominates
    assert data.compute_indicator(df, "rsi").isna().iloc[-1]                          # no losses -> undefined
    down = df.iloc[::-1].set_axis(df.index)
    assert data.compute_indicator(down, "rsi").iloc[-1] == pytest.approx(0.0)
    assert data.compute_indicator(df, "vwma").iloc[-1] == pytest.approx(c.tail(20).mean())
    ub, lb = data.compute_indicator(df, "boll_ub").iloc[-1], data.compute_indicator(df, "boll_lb").iloc[-1]
    assert ub - lb == pytest.approx(4 * c.tail(20).std())
    macd = data.compute_indicator(df, "macd")
    assert data.compute_indicator(df, "macdh").iloc[-1] == pytest.approx(macd.iloc[-1] - data.compute_indicator(df, "macds").iloc[-1])
    for name in data.INDICATORS:
        data.compute_indicator(df, name)
    with pytest.raises(ValueError, match="Valid indicators: close_50_sma"):
        data.compute_indicator(df, "stochrsi")
    assert "Unknown indicator 'bogus'" in data.tool_indicators("NVDA", "rsi,bogus", TD, 5, TD)


def test_statements_and_insider_point_in_time():
    """TST-DATA-04: Statements need period end + filing lag <= trade date; later insider rows dropped [REQ-DATA-04]"""
    out = data.tool_statement("NVDA", "income_statement", "quarterly", "2026-09-13")
    assert "2026-07-31" not in out and "2026-04-30" in out          # 07-31 + 45d = 09-14
    assert "2026-07-31" in data.tool_statement("NVDA", "income_statement", "quarterly", "2026-09-14")
    assert "had been filed" in data.tool_statement("NVDA", "cashflow", "annual", "2026-02-01")
    ins = data.tool_insider("NVDA", TD)
    assert "2026-09-01" in ins and "2026-09-20" not in ins


def test_news_window_and_gap():
    """TST-DATA-05: News is trimmed to the window; an unobserved window is flagged, not called empty [REQ-DATA-05]"""
    ts = lambda s: int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp())
    FakeTicker.news_items = [
        {"title": "Old", "providerPublishTime": ts("2026-08-20T10:00:00"), "publisher": "Y"},
        {"content": {"title": "In window", "pubDate": "2026-09-05T12:00:00Z", "summary": "s",
                     "provider": {"displayName": "Reuters"}}},
        {"content": {"title": "Future leak", "pubDate": "2026-09-11T00:00:00Z"}}]
    out = data.tool_news("NVDA", "2026-09-01", "2026-12-01", TD)
    assert "In window (Reuters, 2026-09-05)" in out and "Future leak" not in out and "Old" not in out
    assert "unavailable" not in out
    FakeTicker.news_items = FakeTicker.news_items[1:]
    gap = data.tool_news("NVDA", "2026-08-01", TD, TD)
    assert "unavailable for 2026-08-01..2026-09-10" in gap and "not an absence of news" in gap


RSS = """<rss><channel>
<item><title>Rheinmetall wins order - Reuters</title><pubDate>Fri, 05 Sep 2026 07:00:00 +0200</pubDate>
  <source url="https://reuters.com">Reuters</source></item>
<item><title>In window</title><pubDate>Sat, 06 Sep 2026 09:00:00 GMT</pubDate><source>Yahoo copy</source></item>
<item><title>Before the window - FT</title><pubDate>Sun, 31 Aug 2026 23:00:00 GMT</pubDate><source>FT</source></item>
<item><title>After the date - FT</title><pubDate>Fri, 11 Sep 2026 06:00:00 GMT</pubDate><source>FT</source></item>
<item><title>Undated - FT</title><source>FT</source></item>
</channel></rss>"""


def test_google_news_windowed(monkeypatch):
    """TST-DATA-17: Google News is queried inside the window by company name, clamped, deduplicated against Yahoo and tagged headline-only [REQ-DATA-05, REQ-DATA-07]"""
    urls = []
    monkeypatch.setattr(data, "_http_get", lambda url: urls.append(url) or RSS.encode())
    FakeTicker.info_by_symbol["RHM.DE"] = {"longName": "Rheinmetall AG"}
    FakeTicker.news_items = [{"content": {"title": "In window!", "pubDate": "2026-09-05T12:00:00Z",
                                          "summary": "s", "provider": {"displayName": "Reuters"}}}]
    out = data.tool_news("RHM.DE", "2026-09-01", "2026-12-01", TD)
    from urllib.parse import parse_qs, urlparse
    assert parse_qs(urlparse(urls[0]).query)["q"] == ["Rheinmetall after:2026-08-31 before:2026-09-11"]
    assert "### Rheinmetall wins order (Reuters, 2026-09-05, Google News, headline only)" in out
    assert out.count("In window") == 1 and "In window! (Reuters, 2026-09-05)\ns" in out     # Yahoo's copy kept
    for leak in ("Before the window", "After the date", "Undated"):
        assert leak not in out, leak
    assert 'Google News searched for "Rheinmetall": 2 headlines in the window' in out
    assert out.index("Rheinmetall wins order") > out.index("In window!")               # Yahoo's items lead
    few = data.tool_news("RHM.DE", "2026-09-01", "2026-12-01", TD, limit=1)
    assert "In window!" in few and "Rheinmetall wins order" not in few                # Google only fills the limit
    assert [data.news_query(n, s) for n, s in (("NVIDIA Corporation", "NVDA"), ("Alphabet Holdings, Inc.", "GOOGL"),
                                              ("Bitcoin USD", "BTC-USD"), (None, "RHM.DE"), ("", "^GSPC"))] == \
        ["NVIDIA", "Alphabet", "Bitcoin", "RHM", "GSPC"]


def test_google_news_failure_is_soft(monkeypatch):
    """TST-DATA-18: A Google News failure adds an unavailable line and never fails the tool; both sources failing is DATA_UNAVAILABLE [REQ-DATA-05, REQ-DATA-06]"""
    def down(url):
        raise TimeoutError("timed out")
    monkeypatch.setattr(data, "_http_get", down)
    FakeTicker.news_items = [{"content": {"title": "Yahoo item", "pubDate": "2026-09-05T12:00:00Z"}}]
    out = data.tool_news("NVDA", "2026-09-01", TD, TD)
    assert "<Google News unavailable: TimeoutError: timed out>" in out and "Yahoo item" in out
    monkeypatch.setattr(data, "_http_get", lambda url: RSS.encode())

    class YahooDown(FakeTicker):
        @property
        def news(self):
            raise ConnectionError("yahoo down")
    monkeypatch.setattr(data, "_ticker", YahooDown)
    out = data.tool_news("NVDA", "2026-09-01", TD, TD)
    assert "<Yahoo Finance news unavailable: ConnectionError: yahoo down>" in out and "Rheinmetall wins order" in out
    assert "only serves recent items" not in out
    monkeypatch.setattr(data, "_http_get", down)
    with pytest.raises(ConnectionError):
        data.tool_news("NVDA", "2026-09-01", TD, TD)


def test_tool_errors_are_readable(cfg, log, capsys, monkeypatch):
    """TST-DATA-06: Failures are marked DATA_UNAVAILABLE (keeping the cause), empty sources NO_DATA_AVAILABLE, never a traceback [REQ-DATA-06]"""
    state = new_run(cfg, log)
    run = ["data", "--run", state["run_dir"]]
    monkeypatch.setattr(data, "_ticker", lambda s: (_ for _ in ()).throw(ConnectionError("yahoo down")))
    assert main(run + ["snapshot", "NVDA"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("DATA_UNAVAILABLE: data tool snapshot failed for NVDA: ConnectionError: yahoo down.")
    assert data.DIRECTIVE in out and "Traceback" not in out
    FakeTicker.frames["EMPTY"] = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex([]))
    monkeypatch.setattr(data, "_ticker", FakeTicker)
    main(run + ["snapshot", "EMPTY"])
    out = capsys.readouterr().out
    assert out.startswith("NO_DATA_AVAILABLE: No OHLCV data for EMPTY on or before 2026-09-18.") and data.DIRECTIVE in out
    main(run + ["indicators"])                                     # usage errors are not data errors
    out = capsys.readouterr().out
    assert "Missing arguments" in out and "DATA_UNAVAILABLE" not in out and "NO_DATA_AVAILABLE" not in out


def test_run_cache_downloads_once(cfg, log, capsys, monkeypatch):
    """TST-DATA-19: One run downloads a symbol's price history once; slices match an uncached fetch; out-of-range requests bypass the cache [REQ-DATA-12]"""
    state = new_run(cfg, log)
    calls = []

    class Counting(FakeTicker):
        def history(self, start, end, auto_adjust=False):
            calls.append((self.symbol, start, end))
            return super().history(start, end, auto_adjust)
    monkeypatch.setattr(data, "_ticker", Counting)
    run = ["data", "--run", state["run_dir"]]
    for args in (["snapshot", "NVDA"], ["indicators", "NVDA", "rsi,macd"], ["stock", "NVDA", "2026-09-01"],
                 ["valuation", "NVDA"]):
        main(run + args)
    outs = capsys.readouterr().out
    assert [c[0] for c in calls] == ["NVDA"] and "UNAVAILABLE" not in outs
    assert (Path(state["run_dir"]) / "cache" / "ohlcv-NVDA.csv").exists() and data._run_cache is None
    with data.run_cache(state["run_dir"], state["trade_date"]):
        cached = data.ohlcv("NVDA", "2026-09-01", "2026-09-10")
    pd.testing.assert_frame_equal(cached, data.ohlcv("NVDA", "2026-09-01", "2026-09-10"), check_freq=False)
    main(run + ["stock", "NVDA", "2024-01-01", "2024-02-01"])     # older than the cached span: fetched directly
    assert len(calls) == 3                                          # + the uncached comparison above


def test_rate_limit_backoff(cfg, log, capsys, monkeypatch):
    """TST-DATA-20: Yahoo rate limits are retried with bounded backoff, then reported DATA_UNAVAILABLE [REQ-DATA-12, REQ-DATA-06]"""
    from yfinance.exceptions import YFRateLimitError
    waits, failures = [], {"left": 2}
    monkeypatch.setattr(data, "_sleep", waits.append)

    class Limited(FakeTicker):
        def history(self, start, end, auto_adjust=False):
            if failures["left"]:
                failures["left"] -= 1
                raise YFRateLimitError()
            return super().history(start, end, auto_adjust)
    monkeypatch.setattr(data, "_ticker", Limited)
    assert not data.ohlcv("NVDA", "2026-09-01", TD).empty and waits == [2.0, 4.0]
    state = new_run(cfg, log)
    failures["left"], waits[:] = 99, []
    main(["data", "--run", state["run_dir"], "snapshot", "NVDA"])
    out = capsys.readouterr().out
    assert out.startswith("DATA_UNAVAILABLE: data tool snapshot failed for NVDA: YFRateLimitError") and waits == [2.0, 4.0]
    assert not (Path(state["run_dir"]) / "cache" / "ohlcv-NVDA.csv").exists()


def test_current_sources_labelled(cfg, log):
    """TST-DATA-07: Profile data and analyst prompts are labelled non-point-in-time for past dates [REQ-DATA-07]"""
    assert "as of today, not necessarily as of 2026-09-10" in data.tool_fundamentals("NVDA", TD)
    assert "not necessarily" not in data.tool_fundamentals("NVDA", "2026-09-24")
    from berkshire import pipeline
    state = new_run(cfg, log)
    prompt = pipeline.build_prompt(state, pipeline.next_steps(state)[0])
    assert "Point-in-time rule" in prompt and "label any such evidence as current" in prompt


# --- point-in-time valuation (REQ-DATA-07, REQ-DATA-08) -------------------------

class StatementTicker:
    """Yahoo-shaped statements: rows × period-end columns, on today's split basis."""

    def __init__(self, quarterly_income=None, annual_income=None, quarterly_bs=None, annual_bs=None, info=None):
        empty = pd.DataFrame()
        self.quarterly_income_stmt = quarterly_income if quarterly_income is not None else empty
        self.income_stmt = annual_income if annual_income is not None else empty
        self.quarterly_balance_sheet = quarterly_bs if quarterly_bs is not None else empty
        self.balance_sheet = annual_bs if annual_bs is not None else empty
        self.info = info or {}

    def history(self, start, end, auto_adjust=False):
        df = bars(end="2026-09-18")                      # close 299.5 on 2026-09-18
        return df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))]


def frame(rows: dict, periods: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=[pd.Timestamp(p) for p in periods]).T


Q = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]   # 06-30 filed on 08-14


def stub(monkeypatch, **kw):
    monkeypatch.setattr(data, "_ticker", lambda s: StatementTicker(**kw))


def test_fundamentals_withheld_on_past_dates(monkeypatch):
    """TST-DATA-08: Past-dated fundamentals show identity only; today's run shows the full profile [REQ-DATA-07]"""
    info = {"longName": "Acme", "sector": "Tech", "industry": "Chips", "marketCap": 9e12, "trailingPE": 99.0,
            "revenueGrowth": 0.5, "fiftyTwoWeekHigh": 400.0}
    stub(monkeypatch, info=info)
    past = data.tool_fundamentals("ACME", "2026-09-18")
    assert "Acme" in past and "Chips" in past
    for leak in ("marketCap", "trailingPE", "revenueGrowth", "fiftyTwoWeekHigh", "9000000000000.0", "99.0"):
        assert leak not in past, leak
    assert "withheld" in past and "`valuation`" in past
    live = data.tool_fundamentals("ACME", "2026-09-24")
    assert "marketCap" in live and "withheld" not in live


def test_fundamentals_units(monkeypatch):
    """TST-DATA-16: Same-day fundamentals mark dividendYield in percent and state that the ratios are fractions [REQ-DATA-11]"""
    stub(monkeypatch, info={"longName": "Acme", "dividendYield": 2.41, "profitMargins": 0.28})
    live = data.tool_fundamentals("ACME", "2026-09-24")
    assert "| dividendYield | 2.41% |" in live and "| profitMargins | 0.28 |" in live
    assert data.UNITS_NOTE in live
    stub(monkeypatch, info={"longName": "Acme", "profitMargins": 0.28})
    assert "dividendYield" not in data.tool_fundamentals("ACME", "2026-09-24")
    assert data.UNITS_NOTE not in data.tool_fundamentals("ACME", "2026-09-18")


def test_valuation_ttm(monkeypatch):
    """TST-DATA-09: Valuation uses the close on the date, 4 filed quarters of EPS and the newest filed balance sheet [REQ-DATA-08]"""
    stub(monkeypatch,
         quarterly_income=frame({"Diluted EPS": [9.0, 1.0, 1.5, 2.0, 0.5], "Net Income": [90, 10, 15, 20, 5],
                                 "Diluted Average Shares": [10, 10, 10, 10, 10]}, ["2026-09-30"] + Q[:4]),
         quarterly_bs=frame({"Ordinary Shares Number": [10.0, 11.0], "Stockholders Equity": [500.0, 450.0]},
                            ["2026-06-30", "2026-03-31"]))
    v = data.valuation("ACME", "2026-09-18")
    assert (v["close"], v["close_date"]) == (299.5, "2026-09-18")
    assert v["eps"] == 1.0 + 1.5 + 2.0 + 0.5 and "TTM, 4 filed quarters ending 2026-06-30" in v["eps_basis"]
    assert v["pe"] == pytest.approx(299.5 / 5.0)                   # the unfiled 2026-09-30 quarter is ignored
    assert (v["shares"], v["shares_date"]) == (10.0, "2026-06-30")
    assert v["market_cap"] == pytest.approx(2995.0) and v["pb"] == pytest.approx(2995.0 / 500.0)
    out = data.tool_valuation("ACME", "2026-09-18")
    assert "| P/E | 59.9 | close / EPS |" in out and "today's split basis" in out and "No enterprise value" in out


def test_valuation_annual_fallback_and_edge_cases(monkeypatch):
    """TST-DATA-10: Annual EPS when <4 quarters are filed; losses, negative equity, stale and mismatched inputs are explicit [REQ-DATA-08]"""
    annual_is = frame({"Diluted EPS": [-2.0], "Net Income": [-20], "Diluted Average Shares": [10]}, ["2025-12-31"])
    stub(monkeypatch, annual_income=annual_is,
         annual_bs=frame({"Ordinary Shares Number": [10.0], "Stockholders Equity": [-50.0]}, ["2025-12-31"]))
    v = data.valuation("ACME", "2026-09-18")
    assert v["eps_basis"] == "fiscal year ending 2025-12-31" and v["pe"] is None and v["pb"] is None
    out = data.tool_valuation("ACME", "2026-09-18")
    assert "n/m (negative earnings)" in out and "n/m (negative equity)" in out
    # Stale: the newest filing is older than the age limit.
    stub(monkeypatch, annual_income=frame({"Diluted EPS": [3.0]}, ["2024-12-31"]),
         annual_bs=frame({"Ordinary Shares Number": [10.0], "Stockholders Equity": [1.0]}, ["2024-12-31"]))
    v = data.valuation("ACME", "2026-09-18")
    assert "eps" not in v and "market_cap" not in v and any("No diluted EPS filed" in n for n in v["notes"])
    # Basis mismatch: EPS still on a pre-split basis (10x) against a post-split share count.
    stub(monkeypatch, annual_income=frame({"Diluted EPS": [30.0], "Net Income": [30.0], "Diluted Average Shares": [10.0]},
                                          ["2025-12-31"]),
         annual_bs=frame({"Ordinary Shares Number": [10.0], "Stockholders Equity": [5.0]}, ["2025-12-31"]))
    v = data.valuation("ACME", "2026-09-18")
    assert "pe" not in v and any("different split bases" in n for n in v["notes"]) and v["market_cap"] == 2995.0
    # Only 3 filed quarters: never a partial "TTM" -- the annual EPS is used instead.
    stub(monkeypatch, quarterly_income=frame({"Diluted EPS": [1.0, 1.0, 1.0]}, Q[:3]),
         annual_income=frame({"Diluted EPS": [3.5]}, ["2025-12-31"]),
         annual_bs=frame({"Ordinary Shares Number": [10.0], "Stockholders Equity": [5.0]}, ["2025-12-31"]))
    v = data.valuation("ACME", "2026-09-18")
    assert v["eps"] == 3.5 and v["eps_basis"] == "fiscal year ending 2025-12-31"
    # Four quarters, all older than the age limit: no EPS rather than a stale TTM.
    stub(monkeypatch, quarterly_income=frame({"Diluted EPS": [1.0, 1.0, 1.0, 1.0]},
                                             ["2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30"]),
         annual_bs=frame({"Ordinary Shares Number": [10.0], "Stockholders Equity": [5.0]}, ["2025-12-31"]))
    v = data.valuation("ACME", "2026-09-18")
    assert "eps" not in v and "pe" not in v and any("No diluted EPS filed within 400 days" in n for n in v["notes"])
    # No close near the date.
    old = data.tool_valuation("ACME", "2020-01-01")
    assert old.startswith("NO_DATA_AVAILABLE: No valuation figures for ACME as of 2020-01-01.") and "No close" in old


def test_every_empty_source_is_marked(monkeypatch):
    """TST-DATA-11: Every tool's nothing-to-report answer starts with NO_DATA_AVAILABLE and the do-not-fabricate directive [REQ-DATA-06]"""
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex([]))
    FakeTicker.frames["EMPTY"] = empty

    class Bare(FakeTicker):
        info = {}
        insider_transactions = pd.DataFrame()
        quarterly_income_stmt = quarterly_balance_sheet = quarterly_cashflow = pd.DataFrame()
        income_stmt = balance_sheet = cashflow = pd.DataFrame()
    monkeypatch.setattr(data, "_ticker", Bare)
    answers = {
        "stock": data.tool_stock("EMPTY", "2026-09-01", TD, TD),
        "fundamentals": data.tool_fundamentals("EMPTY", TD),
        "statement": data.tool_statement("EMPTY", "cashflow", "quarterly", TD),
        "insider": data.tool_insider("EMPTY", TD),
        "valuation": data.tool_valuation("EMPTY", TD),
    }
    for tool, out in answers.items():
        assert out.startswith("NO_DATA_AVAILABLE: ") and out.endswith(data.DIRECTIVE), (tool, out)
    monkeypatch.setattr(data, "_ticker", FakeTicker)               # filed-by cutoff: nothing filed yet
    assert data.tool_statement("NVDA", "income_statement", "annual", "2026-02-01").startswith("NO_DATA_AVAILABLE: ")
    assert data.tool_insider("NVDA", "2026-08-01").startswith("NO_DATA_AVAILABLE: ")
    with pytest.raises(data.NoData):
        data.tool_snapshot("EMPTY", TD, TD)


# --- earnings calendar (REQ-DATA-09) -----------------------------------------

class EarningsTicker(FakeTicker):
    calendar = None
    requested_limit = None

    def get_earnings_dates(self, limit=12):
        EarningsTicker.requested_limit = limit
        return EarningsTicker.calendar


def earnings_frame(rows):
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, *_ in rows]).tz_localize("America/New_York")
    return pd.DataFrame([r[1:] for r in rows], index=idx, columns=["EPS Estimate", "Reported EPS", "Surprise(%)"])


CAL = earnings_frame([
    ("2026-11-17 16:00", 2.47, None, None),
    ("2026-09-22 16:00", 2.30, 2.40, 4.3),     # after a 2026-09-18 trade date: its result must stay hidden
    ("2026-08-26 16:00", 2.09, 2.22, 6.16),
    ("2026-05-20 16:00", 1.77, 1.87, 5.54),
    ("2026-02-25 16:00", 1.54, 1.62, 5.32),
    ("2025-11-19 16:00", 1.26, 1.30, 3.46),
    ("2025-08-27 16:00", 1.01, 1.05, 4.10),
])


def test_earnings_point_in_time(monkeypatch):
    """TST-DATA-12: Earnings history uses announcements before the date only; a later result and today's consensus never leak into a past run [REQ-DATA-09]"""
    EarningsTicker.calendar = CAL
    monkeypatch.setattr(data, "_ticker", EarningsTicker)
    e = data.earnings("NVDA", "2026-09-18", horizon_days=5)
    assert [p["date"] for p in e["past"]] == ["2026-08-26", "2026-05-20", "2026-02-25", "2025-11-19"]
    assert e["past"][0] == {"date": "2026-08-26", "time": "16:00", "estimate": 2.09, "reported": 2.22, "surprise_pct": 6.16}
    assert e["next"] == {"date": "2026-09-22", "time": "16:00", "trading_days_away": 2, "inside_horizon": True,
                         "estimate": None}
    out = data.tool_earnings("NVDA", "2026-09-18", 5)
    assert "INSIDE the 5-trading-day decision horizon" in out and "2.40" not in out and "4.3%" not in out
    assert "consensus as of 2026-09-18 is not available, and its result is withheld" in out
    assert "| 2026-08-26 | 16:00 | 2.09 | 2.22 | +6.2% |" in out
    assert EarningsTicker.requested_limit >= 12 + 4


def test_earnings_same_day_horizon_and_no_calendar(monkeypatch):
    """TST-DATA-13: Same-day runs show consensus; the horizon flag follows holding_period_days; no calendar is NO_DATA_AVAILABLE [REQ-DATA-09, REQ-DATA-06]"""
    EarningsTicker.calendar = CAL
    monkeypatch.setattr(data, "_ticker", EarningsTicker)
    live = data.earnings("NVDA", "2026-09-24", horizon_days=5)       # conftest pins today to 2026-09-24
    assert live["same_day"] and live["next"]["date"] == "2026-11-17" and live["next"]["estimate"] == 2.47
    assert live["next"]["inside_horizon"] is False and live["next"]["trading_days_away"] == 38
    assert "Consensus EPS estimate for it (today): 2.47" in data.tool_earnings("NVDA", "2026-09-24", 5)
    assert data.earnings("NVDA", "2026-09-18", horizon_days=1)["next"]["inside_horizon"] is False
    same_day_event = data.earnings("NVDA", "2026-09-22", horizon_days=5)
    assert same_day_event["next"]["date"] == "2026-09-22" and same_day_event["next"]["trading_days_away"] == 0
    assert same_day_event["past"][0]["date"] == "2026-08-26"        # the result is announced after that day's close
    EarningsTicker.calendar = None
    with pytest.raises(data.NoData, match="No earnings calendar for GLD"):
        data.earnings("GLD", "2026-09-18")


def test_earnings_through_cli(cfg, log, capsys, monkeypatch):
    """TST-DATA-14: The CLI passes the run's holding_period_days to the earnings tool and marks a missing calendar [REQ-DATA-09, REQ-CTX-08]"""
    EarningsTicker.calendar = CAL
    monkeypatch.setattr(data, "_ticker", EarningsTicker)
    state = new_run({**cfg, "holding_period_days": 1}, log)
    main(["data", "--run", state["run_dir"], "earnings", "NVDA"])
    assert "outside the 1-trading-day decision horizon" in capsys.readouterr().out
    EarningsTicker.calendar = pd.DataFrame()
    main(["data", "--run", state["run_dir"], "earnings", "GLD"])
    assert capsys.readouterr().out.startswith("NO_DATA_AVAILABLE: No earnings calendar for GLD")


# --- ETF profile (REQ-DATA-10) --------------------------------------------------

class FundData:
    def __init__(self, holdings=None, sectors=None, asset_classes=None, category="Large Blend"):
        self.fund_overview = {"categoryName": category, "family": "State Street", "legalType": "Exchange Traded Fund"}
        self.fund_operations = pd.DataFrame({"SPY": [0.000945, 0.03]},
                                            index=["Annual Report Expense Ratio", "Annual Holdings Turnover"])
        self.asset_classes = asset_classes if asset_classes is not None else {"stockPosition": 0.9988, "cashPosition": 0.0011}
        self.sector_weightings = sectors if sectors is not None else {"technology": 0.3869, "energy": 0.0348}
        self.top_holdings = holdings if holdings is not None else pd.DataFrame(
            {"Name": ["NVIDIA Corp", "Apple Inc"], "Holding Percent": [0.0808, 0.0703]}, index=["NVDA", "AAPL"])


def fund_ticker(fd, quote_type="ETF"):
    class T(FakeTicker):
        info = {"quoteType": quote_type, "longName": "Test Fund", "totalAssets": 811937038336}
        funds_data = fd
    return T


def test_etf_profile(monkeypatch):
    """TST-DATA-15: etf_profile reports fees, mix, sectors and top-N concentration; undisclosed holdings and past dates are explicit [REQ-DATA-10, REQ-DATA-07]"""
    monkeypatch.setattr(data, "_ticker", fund_ticker(FundData()))
    out = data.tool_etf_profile("SPY", "2026-09-24")
    assert "| Expense ratio | 0.09% |" in out and "| Total assets | 811,937,038,336 |" in out
    assert "- stock: 99.88%" in out and "- technology: 38.69%" in out
    assert "top 2 shown only, not the full portfolio" in out and "| NVIDIA Corp | 8.08% |" in out
    assert "Concentration: the top 2 holdings are 15.11% of the fund." in out and "not necessarily" not in out
    assert "not necessarily as of 2026-09-18" in data.tool_etf_profile("SPY", "2026-09-18")
    gld = fund_ticker(FundData(holdings=pd.DataFrame(), sectors={}, asset_classes={"otherPosition": 1.0}, category="Commodities Focused"))
    monkeypatch.setattr(data, "_ticker", gld)
    out = data.tool_etf_profile("GLD", "2026-09-24")
    assert "Holdings are not disclosed by the source." in out and "Concentration" not in out and "- other: 100.00%" in out
    agg = fund_ticker(FundData(holdings=pd.DataFrame({"Name": ["BlackRock Cash Funds Instl"], "Holding Percent": [0.03]},
                                                    index=["XX"]), sectors={}))
    monkeypatch.setattr(data, "_ticker", agg)
    assert "(only a cash line is listed)" in data.tool_etf_profile("AGG", "2026-09-24")
    monkeypatch.setattr(data, "_ticker", fund_ticker(FundData(category="Trading--Leveraged Equity")))
    assert "resets daily" in data.tool_etf_profile("TQQQ", "2026-09-24")
    monkeypatch.setattr(data, "_ticker", fund_ticker(FundData(), quote_type="EQUITY"))
    with pytest.raises(data.NoData, match="not an exchange-traded fund"):
        data.tool_etf_profile("NVDA", "2026-09-24")
