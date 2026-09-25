"""Point-in-time data tools (offline, via the FakeTicker in conftest)."""

from datetime import UTC, datetime

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
    """TST-DATA-06: A failing data tool prints a readable error line, not a traceback [REQ-DATA-06]"""
    state = new_run(cfg, log)
    monkeypatch.setattr(data, "_ticker", lambda s: (_ for _ in ()).throw(ConnectionError("yahoo down")))
    assert main(["data", "--run", state["run_dir"], "snapshot", "NVDA"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Data tool snapshot failed") and "yahoo down" in out and "Traceback" not in out
    main(["data", "--run", state["run_dir"], "indicators"])
    assert "Missing arguments" in capsys.readouterr().out


def test_current_sources_labelled(cfg, log):
    """TST-DATA-07: Profile data and analyst prompts are labelled non-point-in-time for past dates [REQ-DATA-07]"""
    assert "as of today, not necessarily as of 2026-09-10" in data.tool_fundamentals("NVDA", TD)
    assert "not necessarily" not in data.tool_fundamentals("NVDA", "2026-09-24")
    from berkshire import pipeline
    state = new_run(cfg, log)
    prompt = pipeline.build_prompt(state, pipeline.next_steps(state)[0])
    assert "Point-in-time rule" in prompt and "label any such evidence as current" in prompt
