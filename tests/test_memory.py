"""Decision log, settlement and past context."""

import pandas as pd
import pytest
from conftest import bars

from berkshire.memory import DecisionLog, compute_returns, reflection_prompt, resolve_benchmark, settle_candidates


def outcome(ticker, date, raw=0.05, alpha=0.02, resolved="2026-09-10", text="Lesson."):
    return {"ticker": ticker, "trade_date": date, "raw_return": raw, "alpha_return": alpha,
            "holding_days": 5, "resolution_date": resolved, "reflection": text}


def test_store_pending_format(log):
    """TST-MEM-01: A decision is appended in the TradingAgents pending format [REQ-MEM-01]"""
    assert log.store("NVDA", "2026-09-01", "**Rating**: Buy\n\nThesis")
    text = log.path.read_text()
    assert text.startswith("[2026-09-01 | NVDA | Buy | pending]\n\nDECISION:\n**Rating**: Buy")
    assert text.endswith("\n\n<!-- ENTRY_END -->\n\n")
    e = log.entries()[0]
    assert e["pending"] and e["rating"] == "Buy" and e["decision"].endswith("Thesis")


def test_store_idempotent(log):
    """TST-MEM-02: A second decision for the same ticker+date is a no-op, pending or settled [REQ-MEM-02]"""
    log.store("NVDA", "2026-09-01", "Rating: Buy")
    assert not log.store("NVDA", "2026-09-01", "Rating: Sell")
    log.apply_outcomes([outcome("NVDA", "2026-09-01")])
    assert not log.store("NVDA", "2026-09-01", "Rating: Sell")
    assert len(log.entries()) == 1


def test_benchmark_and_returns():
    """TST-MEM-03: Benchmark by override/suffix/default; returns need the full window [REQ-MEM-03]"""
    cfg = {"benchmark_ticker": None, "benchmark_map": {".T": "^N225", ".DE": "^GDAXI", "": "SPY"}}
    assert resolve_benchmark("7203.T", cfg) == "^N225"
    assert resolve_benchmark("rhm.de", cfg) == "^GDAXI"
    assert resolve_benchmark("BRK.B", cfg) == "SPY"
    assert resolve_benchmark("7203.T", {**cfg, "benchmark_ticker": "QQQ"}) == "QQQ"
    idx = pd.bdate_range("2026-09-01", periods=6)
    stock = pd.Series([100, 101, 102, 103, 104, 110.0], index=idx)
    bench = pd.Series([400, 400, 400, 400, 400, 404.0], index=idx)
    raw, alpha, resolved = compute_returns(stock, bench, 5)
    assert raw == pytest.approx(0.10) and alpha == pytest.approx(0.09) and resolved == "2026-09-08"
    assert compute_returns(stock.iloc[:5], bench, 5) is None


def test_settle_candidates_and_apply(log, cfg):
    """TST-MEM-04: Due entries settle with a reflection and resolved tag; not-yet-traded stay pending [REQ-MEM-03, REQ-MEM-04]"""
    log.store("NVDA", "2026-08-03", "Rating: Buy")
    log.store("NVDA", "2026-09-17", "Rating: Sell")   # window not traded by 2026-09-18
    log.store("AMD", "2026-08-03", "Rating: Hold")
    closes = lambda sym, start, end: bars()["Close"].loc[start:end]
    cands = settle_candidates(log, cfg, ["NVDA"], closes)
    assert [(c["ticker"], c["trade_date"]) for c in cands] == [("NVDA", "2026-08-03")]
    c = cands[0]
    assert c["benchmark"] == "SPY" and c["resolution_date"] == "2026-08-10"
    assert "Alpha vs SPY" in reflection_prompt(c)
    assert log.apply_outcomes([{**c, "reflection": "Trend call held."}]) == 1
    tag = log.path.read_text().splitlines()[0]
    assert tag.startswith("[2026-08-03 | NVDA | Buy | +") and tag.endswith("| 5d | resolved:2026-08-10]")
    pend = {(e["ticker"], e["date"]) for e in log.pending()}
    assert pend == {("NVDA", "2026-09-17"), ("AMD", "2026-08-03")}
    assert not list(log.path.parent.glob("*.tmp"))


def test_settle_unreachable_stays_pending(log, cfg):
    """TST-MEM-08: A price-fetch failure leaves the entry pending [REQ-MEM-03]"""
    log.store("DEAD", "2026-08-03", "Rating: Buy")
    boom = lambda *a: (_ for _ in ()).throw(RuntimeError("delisted"))
    assert settle_candidates(log, cfg, None, boom) == []
    assert log.pending()[0]["ticker"] == "DEAD"


def test_past_context_selection_and_pit(log):
    """TST-MEM-05: 5 same-ticker + 3 cross-ticker, newest first, point-in-time filtered [REQ-MEM-05]"""
    for i in range(7):
        log.store("NVDA", f"2026-07-0{i + 1}", f"Rating: Buy {i}")
    for t in ("AMD", "INTC", "TSM", "META"):
        log.store(t, "2026-07-01", "Rating: Hold")
    log.apply_outcomes([outcome("NVDA", f"2026-07-0{i + 1}", resolved=f"2026-07-1{i}", text=f"L{i}") for i in range(7)]
                       + [outcome(t, "2026-07-01", resolved="2026-07-09", text=f"X-{t}") for t in ("AMD", "INTC", "TSM", "META")])
    ctx = log.past_context("NVDA")
    assert ctx.count("DECISION:") == 5 and ctx.index("L6") < ctx.index("L2") and "L1" not in ctx
    assert ctx.count("X-") == 3 and "X-AMD" not in ctx  # AMD is the oldest cross-ticker lesson
    pit = log.past_context("NVDA", as_of="2026-07-11")
    assert "L0" in pit and "L1" in pit and "L2" not in pit
    assert log.past_context("NVDA", as_of="2026-01-01") == ""


def test_rotation_keeps_pending(tmp_path):
    """TST-MEM-06: Rotation drops oldest resolved entries only [REQ-MEM-06]"""
    log = DecisionLog(tmp_path / "log.md", max_entries=2)
    for day in ("01", "02", "03"):
        log.store("NVDA", f"2026-07-{day}", "Rating: Buy")
    log.store("NVDA", "2026-07-04", "Rating: Buy")   # stays pending
    log.apply_outcomes([outcome("NVDA", f"2026-07-{day}") for day in ("01", "02", "03")])
    kept = [(e["date"], e["pending"]) for e in log.entries()]
    assert kept == [("2026-07-02", False), ("2026-07-03", False), ("2026-07-04", True)]


def test_target_move_in_reflection(log, cfg):
    """TST-MEM-09: The Reflector is told the PM target's implied move from the same start close as the return; no target, no line [REQ-MEM-08]"""
    from berkshire.decisions import render_pm_decision
    from berkshire.memory import decision_target
    buy = render_pm_decision({"rating": "Buy", "executive_summary": "Buy near 100; stop 90.", "investment_thesis": "T",
                              "price_target": 120.0, "time_horizon": "3-6 months"})
    sell = render_pm_decision({"rating": "Sell", "executive_summary": "E", "investment_thesis": "T",
                               "price_target": 80.0, "time_horizon": None})
    none = render_pm_decision({"rating": "Hold", "executive_summary": "Target 150 later.", "investment_thesis": "T",
                               "price_target": None, "time_horizon": None})
    assert decision_target(buy) == (120.0, "3-6 months")
    assert decision_target(sell) == (80.0, None)
    assert decision_target(none) == (None, None)                    # "150" in the prose is not a target
    assert decision_target("Rating: Buy, target 130") == (None, None)
    for t, dec in (("AAA", buy), ("BBB", sell), ("CCC", none)):
        log.store(t, "2026-09-01", dec)
    idx = pd.bdate_range("2026-09-01", periods=8)
    closes = lambda sym, start, end: pd.Series([100.0, 101, 102, 103, 104, 105, 106, 107], index=idx)
    cands = {c["ticker"]: c for c in settle_candidates(log, cfg, None, closes)}
    assert cands["AAA"]["target_move"] == pytest.approx(0.20) and cands["AAA"]["start_close"] == 100.0
    assert cands["BBB"]["target_move"] == pytest.approx(-0.20) and cands["CCC"]["target_move"] is None
    prompt = reflection_prompt(cands["AAA"])
    assert "Price target 120 implied +20.0% from the 2026-09-01 close of 100.00, over the stated horizon (3-6 months); " \
           "this 5-day window realised +5.0%." in prompt
    assert "implied -20.0%" in reflection_prompt(cands["BBB"]) and "over the stated horizon (not stated)" in reflection_prompt(cands["BBB"])
    assert "Price target" not in reflection_prompt(cands["CCC"])
