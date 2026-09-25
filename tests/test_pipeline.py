"""Routing, context grounding, checkpointing and reports of the graph engine."""

import json
from pathlib import Path

import pytest
from conftest import CANNED, canned, new_run, run_all

from berkshire import config, pipeline

# --- Flow -------------------------------------------------------------------

def test_full_run_order(cfg, log):
    """TST-FLOW-01: A full run visits the teams in TradingAgents order [REQ-FLOW-01]"""
    trace = []
    run_all(new_run(cfg, log), log, trace=trace)
    flat = [s for batch in trace for s in batch]
    assert flat == ["analyst_market", "analyst_social", "analyst_news", "analyst_fundamentals",
                    "bull_1", "bear_2", "research_manager", "trader",
                    "aggressive_1", "conservative_2", "neutral_3", "portfolio_manager"]


def test_analysts_offered_together(cfg, log):
    """TST-FLOW-02: Selected analysts are offered as one parallel batch; debate waits for all [REQ-FLOW-02]"""
    state = new_run(cfg, log)
    batch = [s["id"] for s in pipeline.next_steps(state)]
    assert batch == ["analyst_market", "analyst_social", "analyst_news", "analyst_fundamentals"]
    for sid in batch[:-1]:
        state = pipeline.submit(state, sid, canned(sid))
    assert [s["id"] for s in pipeline.next_steps(state)] == ["analyst_fundamentals"]


@pytest.mark.parametrize("rounds", [1, 2, 3])
def test_investment_debate_rounds(cfg, log, rounds):
    """TST-FLOW-03: Bull opens and the debate alternates for 2 x rounds turns [REQ-FLOW-03]"""
    trace = []
    run_all(new_run({**cfg, "max_debate_rounds": rounds}, log), log, trace=trace)
    debate = [s for b in trace for s in b if s.startswith(("bull", "bear"))]
    assert debate == [f"{'bull' if i % 2 == 0 else 'bear'}_{i + 1}" for i in range(2 * rounds)]


@pytest.mark.parametrize("rounds", [1, 2])
def test_risk_debate_rounds(cfg, log, rounds):
    """TST-FLOW-04: Risk debate rotates Aggressive, Conservative, Neutral for 3 x rounds turns [REQ-FLOW-04]"""
    trace = []
    run_all(new_run({**cfg, "max_risk_discuss_rounds": rounds}, log), log, trace=trace)
    risk = [s.split("_")[0] for b in trace for s in b if s.startswith(("aggressive", "conservative", "neutral"))]
    assert risk == ["aggressive", "conservative", "neutral"] * rounds


def test_analyst_selection_validation(cfg, log):
    """TST-FLOW-05: Unknown or empty analyst selections are rejected; order is canonical [REQ-FLOW-05]"""
    with pytest.raises(ValueError, match="unknown analyst"):
        pipeline.select_analysts(["market", "astrology"], "stock")
    with pytest.raises(ValueError, match="at least one"):
        pipeline.select_analysts([" "], "stock")
    assert pipeline.select_analysts(["news", "market"], "stock") == ["market", "news"]


def test_crypto_drops_fundamentals(cfg, log):
    """TST-FLOW-06: Crypto drops the fundamentals analyst and is framed as an asset [REQ-FLOW-06]"""
    state = new_run(cfg, log, ticker="BTC-USD", identity={"company_name": "Bitcoin USD"})
    assert state["asset_type"] == "crypto"
    assert "fundamentals" not in state["analysts"]
    assert "Treat it as a crypto asset rather than a company" in state["instrument_context"]
    with pytest.raises(ValueError):
        pipeline.select_analysts(["fundamentals"], "crypto")


def test_depth_mapping_and_override(monkeypatch):
    """TST-FLOW-07: Depth maps to 1/3/5 rounds; explicit flags and env vars win [REQ-FLOW-07]"""
    from berkshire.cli import depth_overrides
    assert depth_overrides("shallow") == {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
    assert depth_overrides("medium")["max_debate_rounds"] == 3
    assert depth_overrides("deep")["max_risk_discuss_rounds"] == 5
    assert depth_overrides("deep", debate_rounds=2)["max_debate_rounds"] == 2
    monkeypatch.setenv("BERKSHIRE_MAX_RISK_ROUNDS", "2")
    assert "max_risk_discuss_rounds" not in depth_overrides("deep")


def test_routing_is_pure_function_of_state(cfg, log):
    """TST-FLOW-08: Same persisted state -> same next step, across a reload [REQ-FLOW-08]"""
    state = new_run(cfg, log)
    for sid in ("analyst_market", "analyst_social", "analyst_news", "analyst_fundamentals", "bull_1"):
        state = pipeline.submit(state, sid, canned(sid))
    reloaded = pipeline.load_state(Path(state["run_dir"]))
    assert pipeline.next_steps(state) == pipeline.next_steps(reloaded)
    assert pipeline.next_steps(reloaded)[0]["id"] == "bear_2"


def test_out_of_order_submit_rejected(cfg, log):
    """TST-FLOW-09: Submitting a step that is not due raises and leaves state unchanged [REQ-FLOW-09]"""
    state = new_run(cfg, log)
    before = json.dumps(state, sort_keys=True)
    with pytest.raises(ValueError, match="not due"):
        pipeline.submit(state, "trader", CANNED["trader"])
    with pytest.raises(ValueError, match="no output"):
        pipeline.submit(state, "analyst_market", "   ")
    assert json.dumps(pipeline.load_state(Path(state["run_dir"])), sort_keys=True) == before


def test_models_per_role(cfg, log):
    """TST-ROLE-02: Judges get the deep model, all other roles the quick model [REQ-ROLE-02]"""
    state = new_run({**cfg, "deep_think_llm": "fable", "quick_think_llm": "haiku"}, log)
    trace = {}
    while steps := pipeline.next_steps(state):
        for s in steps:
            trace[s["id"]] = s["model"]
            state = pipeline.submit(state, s["id"], canned(s["id"]), log)
    assert {k for k, v in trace.items() if v == "fable"} == {"research_manager", "portfolio_manager"}
    assert all(v == "haiku" for k, v in trace.items() if k not in ("research_manager", "portfolio_manager"))


# --- Context ----------------------------------------------------------------

def test_identity_injected_everywhere(cfg, log):
    """TST-CTX-01: Resolved identity + exact-ticker rule reach every prompt; past-date caveat; fail-open [REQ-CTX-01]"""
    state = new_run(cfg, log, identity={"company_name": "NVIDIA Corporation", "sector": "Technology",
                                        "industry": "Semiconductors", "exchange": "NMS"})
    ctx = state["instrument_context"]
    assert "Company: NVIDIA Corporation" in ctx and "Technology / Semiconductors" in ctx
    assert "not necessarily on 2026-09-18" in ctx
    prompts = []
    while steps := pipeline.write_prompts(state):
        for s in steps:
            prompts.append(Path(s["prompt_file"]).read_text())
            state = pipeline.submit(state, s["id"], canned(s["id"]), log)
    assert len(prompts) == 12 and all("`NVDA`" in p and "NVIDIA Corporation" in p for p in prompts)
    today_ctx = pipeline.instrument_context("NVDA", "stock", {"company_name": "X"}, "2026-09-24")
    assert "not necessarily" not in today_ctx
    bare = pipeline.instrument_context("ZZZZ", "stock", {}, "2026-09-18")
    assert "Resolved identity" not in bare and "`ZZZZ`" in bare


def test_profile_failure_falls_back(cfg, log, monkeypatch):
    """TST-CTX-08: An identity lookup error does not fail the run [REQ-CTX-01]"""
    from berkshire import data
    monkeypatch.setattr(data, "_ticker", lambda s: (_ for _ in ()).throw(RuntimeError("rate limited")))
    res = pipeline.init_run("NVDA", "2026-09-18", cfg, results_dir=config.home() / "runs", memory_log=log)
    assert "Resolved identity" not in pipeline.load_state(Path(res["run_dir"]))["instrument_context"]


def test_absent_reports_marked(cfg, log):
    """TST-CTX-02: A report from an unselected analyst is an explicit 'not available' marker [REQ-CTX-02]"""
    state = new_run(cfg, log, analysts=["market"])
    state = pipeline.submit(state, "analyst_market", CANNED["analyst_market"])
    prompt = pipeline.build_prompt(state, pipeline.next_steps(state)[0])
    assert "(No news report in this run: it is not available, not an empty finding.)" in prompt
    assert "(No fundamentals report in this run" in prompt


def test_opening_marker(cfg, log):
    """TST-CTX-03: First speakers get an opening marker instead of an empty opponent argument [REQ-CTX-03]"""
    state = new_run(cfg, log, analysts=["market"])
    state = pipeline.submit(state, "analyst_market", CANNED["analyst_market"])
    bull = pipeline.build_prompt(state, pipeline.next_steps(state)[0])
    assert "The bear analyst has not spoken yet — open the debate with your own case." in bull
    for sid in ("bull_1", "bear_2", "research_manager", "trader"):
        state = pipeline.submit(state, sid, canned(sid))
    aggressive = pipeline.build_prompt(state, pipeline.next_steps(state)[0])
    assert "The conservative analyst has not spoken yet" in aggressive
    assert "The neutral analyst has not spoken yet" in aggressive


def test_portfolio_three_states(cfg, log):
    """TST-CTX-04: Position held, flat book and not-provided render differently [REQ-CTX-04]"""
    from berkshire.etoro import render_portfolio
    none = render_portfolio(None, "NVDA")
    flat = render_portfolio({"cash": 1000.0, "currency": "USD", "positions": []}, "NVDA")
    held = render_portfolio({"cash": 1000.0, "positions": [{"ticker": "NVDA", "quantity": 10, "average_price": 150.0}]}, "NVDA")
    assert "not provided" in none and "do not assume a flat book" in none
    assert "No current position in NVDA" in flat and "Cash available: 1,000.00 USD" in flat
    assert "Current position in NVDA: 10 units, average price 150.00" in held
    state = new_run(cfg, log)
    assert "not provided" in state["portfolio_context"]


def test_trader_grounding(cfg, log):
    """TST-CTX-05: The Trader prompt carries the market report and grounding rule only when present [REQ-CTX-05]"""
    for analysts, expect in ((["market", "news"], True), (["news"], False)):
        state = new_run(cfg, log, analysts=analysts, ticker="AMD")
        while (steps := pipeline.next_steps(state))[0]["id"] != "trader":
            for s in steps:
                state = pipeline.submit(state, s["id"], canned(s["id"]))
        prompt = pipeline.build_prompt(state, steps[0])
        assert ("Technical Market Report:" in prompt) is expect
        assert ("Ground concrete price levels" in prompt) is expect


def test_lessons_only_for_pm(cfg, log):
    """TST-CTX-06: Past-decision lessons appear in the Portfolio Manager prompt only [REQ-CTX-06]"""
    state = new_run(cfg, log)
    state["past_context"] = "LESSON-MARKER: trust the trend."
    seen = {}
    while steps := pipeline.next_steps(state):
        for s in steps:
            seen[s["id"]] = "LESSON-MARKER" in pipeline.build_prompt(state, s)
            state = pipeline.submit(state, s["id"], canned(s["id"]), log)
    assert seen.pop("portfolio_manager") is True
    assert not any(seen.values())


def test_run_lessons_point_in_time(cfg, log):
    """TST-CTX-09: A historical run only sees lessons resolved by its trade date; a live run sees all [REQ-MEM-05, REQ-CTX-06]"""
    log.store("AMD", "2026-09-01", "Rating: Buy")
    log.store("INTC", "2026-09-02", "Rating: Sell")
    log.apply_outcomes([
        {"ticker": "AMD", "trade_date": "2026-09-01", "raw_return": 0.01, "alpha_return": 0.01, "holding_days": 5,
         "resolution_date": "2026-09-08", "reflection": "EARLY-LESSON"},
        {"ticker": "INTC", "trade_date": "2026-09-02", "raw_return": 0.01, "alpha_return": 0.01, "holding_days": 5,
         "resolution_date": "2026-09-20", "reflection": "LATE-LESSON"}])
    hist = new_run(cfg, log, date="2026-09-18")["past_context"]
    assert "EARLY-LESSON" in hist and "LATE-LESSON" not in hist
    live = new_run(cfg, log, ticker="MSFT", date="2026-09-24")["past_context"]
    assert "EARLY-LESSON" in live and "LATE-LESSON" in live


def test_language_instruction(cfg, log):
    """TST-CTX-07: Non-English output language reaches every report-producing prompt [REQ-CTX-07]"""
    assert pipeline.language_instruction("English") == ""
    state = new_run({**cfg, "output_language": "German"}, log)
    while steps := pipeline.next_steps(state):
        for s in steps:
            assert "Write your entire response in German." in pipeline.build_prompt(state, s)
            state = pipeline.submit(state, s["id"], canned(s["id"]), log)


# --- Output handling in the pipeline ------------------------------------------

def test_signal_and_structured_render(cfg, log):
    """TST-OUT-07: Structured outputs render to TradingAgents markdown and the signal is parsed [REQ-OUT-01, REQ-OUT-04]"""
    state = run_all(new_run(cfg, log), log)
    assert state["signal"] == "Buy"
    assert state["investment_plan"].startswith("**Recommendation**: Overweight")
    assert "**Stop Loss**: 290.0" in state["trader_investment_plan"]
    assert state["sentiment_report"].startswith("**Overall Sentiment:** **Mildly Bullish** (Score: 6.0/10)")
    assert state["structured"]["pm_decision"]["price_target"] == 340.0
    assert state["warnings"] == []


def test_pm_without_rating_is_review(cfg, log):
    """TST-OUT-08: A final decision without a rating yields REVIEW and is logged as REVIEW [REQ-OUT-05, REQ-OUT-02]"""
    out = lambda sid: "I cannot decide; the picture is unclear." if sid == "portfolio_manager" else canned(sid)
    state = run_all(new_run(cfg, log), log, outputs=out)
    assert state["signal"] == "REVIEW"
    assert any("portfolio_manager: no pm_decision JSON block" in w for w in state["warnings"])
    assert log.entries()[-1]["rating"] == "REVIEW"


# --- Checkpoint -------------------------------------------------------------

def test_state_persisted_each_step(cfg, log):
    """TST-CKPT-01: Each submit is on disk before the next step is offered [REQ-CKPT-01, REQ-SAFE-02]"""
    state = new_run(cfg, log)
    state = pipeline.submit(state, "analyst_market", CANNED["analyst_market"])
    on_disk = pipeline.load_state(Path(state["run_dir"]))
    assert on_disk["completed"] == ["analyst_market"] and on_disk["market_report"].startswith("Market report")
    assert not list(Path(state["run_dir"]).glob("*.tmp"))


def test_resume_same_signature(cfg, log):
    """TST-CKPT-02: --checkpoint resumes a same-signature run; a changed signature starts fresh [REQ-CKPT-02]"""
    state = new_run(cfg, log)
    state = pipeline.submit(state, "analyst_market", CANNED["analyst_market"])
    kw = dict(results_dir=config.home() / "runs", memory_log=log, identity={})
    res = pipeline.init_run("NVDA", "2026-09-18", cfg, checkpoint=True, **kw)
    assert res["resumed"] and res["completed"] == ["analyst_market"]
    res = pipeline.init_run("NVDA", "2026-09-18", cfg, checkpoint=True, analysts=["market"], **kw)
    assert not res["resumed"] and pipeline.load_state(Path(res["run_dir"]))["completed"] == []


def test_fresh_without_checkpoint_or_after_complete(cfg, log):
    """TST-CKPT-03: No --checkpoint, or a completed run, starts fresh; --skip-if-complete returns the signal [REQ-CKPT-03, REQ-SCHED-03]"""
    kw = dict(results_dir=config.home() / "runs", memory_log=log, identity={})
    state = new_run(cfg, log)
    pipeline.submit(state, "analyst_market", CANNED["analyst_market"])
    assert pipeline.init_run("NVDA", "2026-09-18", cfg, **kw)["resumed"] is False
    run_all(pipeline.load_state(Path(state["run_dir"])), log)
    skipped = pipeline.init_run("NVDA", "2026-09-18", cfg, checkpoint=True, skip_if_complete=True, **kw)
    assert skipped["skipped"] and skipped["signal"] == "Buy"
    again = pipeline.init_run("NVDA", "2026-09-18", cfg, checkpoint=True, **kw)
    assert not again["resumed"] and not again["skipped"]


def test_clear_checkpoints(cfg, log, capsys):
    """TST-CKPT-04: clear-checkpoints removes incomplete runs and keeps completed ones [REQ-CKPT-04]"""
    from berkshire.cli import main
    run_all(new_run(cfg, log, ticker="AAPL"), log)
    new_run(cfg, log, ticker="MSFT")
    assert main(["clear-checkpoints"]) == 0
    removed = json.loads(capsys.readouterr().out)["removed"]
    assert len(removed) == 1 and "MSFT" in removed[0]
    assert (config.home() / "runs" / "AAPL" / "2026-09-18" / "state.json").exists()


# --- Reports ----------------------------------------------------------------

def test_report_tree(cfg, log):
    """TST-RPT-01: A completed run writes the TradingAgents report tree and complete_report sections I-V [REQ-RPT-01, REQ-SAFE-03]"""
    state = run_all(new_run(cfg, log), log)
    root = Path(state["run_dir"]) / "reports"
    for rel in ("1_analysts/market.md", "1_analysts/sentiment.md", "1_analysts/news.md", "1_analysts/fundamentals.md",
                "2_research/bull.md", "2_research/bear.md", "2_research/manager.md", "3_trading/trader.md",
                "4_risk/aggressive.md", "4_risk/conservative.md", "4_risk/neutral.md", "5_portfolio/decision.md"):
        assert (root / rel).is_file(), rel
    report = (root / "complete_report.md").read_text()
    for header in ("## I. Analyst Team Reports", "## II. Research Team Decision", "## III. Trading Team Plan",
                   "## IV. Risk Management Team Decision", "## V. Portfolio Manager Decision"):
        assert header in report
    assert "not financial, investment, or trading advice" in report
    assert state["report"] == str(root / "complete_report.md")


def test_full_states_log(cfg, log):
    """TST-RPT-02: full_states_log_<date>.json has the TradingAgents keys [REQ-RPT-02]"""
    state = run_all(new_run(cfg, log), log)
    entry = json.loads((Path(state["run_dir"]) / "full_states_log_2026-09-18.json").read_text())
    assert set(entry) == {"company_of_interest", "trade_date", "market_report", "sentiment_report", "news_report",
                          "fundamentals_report", "investment_debate_state", "trader_investment_decision",
                          "risk_debate_state", "investment_plan", "final_trade_decision"}
    assert entry["final_trade_decision"].startswith("**Rating**: Buy")


def test_progress_table(cfg, log):
    """TST-IF-06: status shows every agent grouped by team with pending/in progress/done [REQ-IF-06]"""
    state = new_run(cfg, log)
    table = pipeline.progress(state)
    assert "| Analyst Team | Market | in progress |" in table
    assert "| Portfolio Management | Portfolio Manager | pending |" in table
    state = run_all(state, log)
    table = pipeline.progress(state)
    assert "signal Buy" in table and "pending" not in table and "in progress" not in table


# --- Stopping and instrument resolution ------------------------------------------

def test_stop_run(cfg, log, capsys):
    """TST-FLOW-11: A stopped run offers and accepts no steps; --checkpoint resumes it [REQ-UI-13]"""
    from berkshire.cli import main
    state = new_run(cfg, log)
    state = pipeline.submit(state, "analyst_market", CANNED["analyst_market"])
    state = pipeline.stop_run(state, "wrong instrument")
    assert pipeline.next_steps(state) == [] and pipeline.summary(state)["status"] == "stopped"
    with pytest.raises(ValueError, match="stopped \\(wrong instrument\\)"):
        pipeline.submit(state, "analyst_social", CANNED["analyst_social"])
    assert main(["next", state["run_dir"]]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["done"] is True and out["stopped"]["reason"] == "wrong instrument" and out["steps"] == []
    res = pipeline.init_run("NVDA", "2026-09-18", cfg, results_dir=config.home() / "runs", memory_log=log,
                            identity={}, checkpoint=True)
    resumed = pipeline.load_state(Path(res["run_dir"]))
    assert res["resumed"] and "stopped" not in resumed and resumed["completed"] == ["analyst_market"]
    done = run_all(resumed, log)
    with pytest.raises(ValueError, match="already complete"):
        pipeline.stop_run(done)


def test_etoro_symbols_and_unlisted(cfg, log):
    """TST-IF-10: eToro-only names map to Yahoo; an unlisted instrument is refused before any agent runs [REQ-IF-10]"""
    import pandas as pd
    from conftest import FakeTicker

    from berkshire import data
    assert pipeline.resolve_ticker("eurooil", cfg) == ("BZ=F", "EUROOIL")
    assert pipeline.resolve_ticker("NVDA", cfg) == ("NVDA", None)
    state = new_run(cfg, log, ticker="EUROOIL")
    assert state["company_of_interest"] == "BZ=F" and state["etoro_symbol"] == "EUROOIL"
    FakeTicker.frames["NOPE"] = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex([]))
    with pytest.raises(ValueError, match="no price data for NOPE.*symbol_map"):
        new_run(cfg, log, ticker="NOPE")
    assert not (config.home() / "runs" / "NOPE").exists()
    FakeTicker.frames["OFFLINE"] = None
    import berkshire.data as d
    real = d.ohlcv
    d.ohlcv = lambda *a: (_ for _ in ()).throw(ConnectionError("down"))
    try:
        assert data.check_listed("OFFLINE", "2026-09-18") is None
        assert new_run(cfg, log, ticker="MSFT")["company_of_interest"] == "MSFT"  # fail-open
    finally:
        d.ohlcv = real
