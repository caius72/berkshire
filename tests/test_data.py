"""Point-in-time data tools (offline, via the FakeTicker in conftest)."""

from datetime import UTC, datetime

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
