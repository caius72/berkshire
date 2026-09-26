"""Config precedence, CLI surface, input validation, path safety, backtest."""

import json
from pathlib import Path

import pytest
from conftest import canned

from berkshire import backtest, config, pipeline
from berkshire.cli import main
from berkshire.memory import DecisionLog


def test_config_precedence(monkeypatch):
    """TST-IF-05: defaults < config.json < BERKSHIRE_* env < CLI flags; bad env values fail loudly [REQ-IF-05]"""
    (config.home()).mkdir(parents=True, exist_ok=True)
    (config.home() / "config.json").write_text(json.dumps({"max_debate_rounds": 2, "quick_think_llm": "haiku"}))
    assert config.load()["max_debate_rounds"] == 2
    monkeypatch.setenv("BERKSHIRE_MAX_DEBATE_ROUNDS", "4")
    monkeypatch.setenv("BERKSHIRE_CHECKPOINT_ENABLED", "yes")
    cfg = config.load()
    assert cfg["max_debate_rounds"] == 4 and cfg["checkpoint_enabled"] is True and cfg["quick_think_llm"] == "haiku"
    assert config.load({"max_debate_rounds": 5})["max_debate_rounds"] == 5
    monkeypatch.setenv("BERKSHIRE_CHECKPOINT_ENABLED", "treu")
    with pytest.raises(ValueError, match="BERKSHIRE_CHECKPOINT_ENABLED"):
        config.load()


def test_cli_end_to_end(capsys, monkeypatch):
    """TST-IF-02: init/next/submit/status drive a whole run from the CLI with TradingAgents flags [REQ-IF-02, REQ-IF-08]"""
    def call(*argv):
        assert main(list(argv)) == 0, capsys.readouterr().err
        out = capsys.readouterr().out
        return json.loads(out) if out.lstrip().startswith("{") else out
    res = call("init", "NVDA", "2026-09-18", "--analysts", "market,news", "--depth", "shallow",
               "--language", "German", "--deep-model", "fable", "--checkpoint")
    run = res["run_dir"]
    while not (nxt := call("next", run))["done"]:
        for s in nxt["steps"]:
            assert Path(s["prompt_file"]).is_file()
            Path(s["output_file"]).parent.mkdir(parents=True, exist_ok=True)
            Path(s["output_file"]).write_text(canned(s["id"]))
            last = call("submit", run, s["id"])
    assert last["complete"] and last["signal"] == "Buy" and last["report"].endswith("complete_report.md")
    state = pipeline.load_state(Path(run))
    assert state["analysts"] == ["market", "news"] and state["config"]["deep_think_llm"] == "fable"
    assert state["config"]["output_language"] == "German"
    assert "| Trading Team | Trader | done |" in call("status", run)
    assert main(["submit", run, "trader"]) == 2
    assert "not due" in capsys.readouterr().err


@pytest.mark.parametrize("date,msg", [("2026-9-1", "YYYY-MM-DD"), ("2026-02-30", "YYYY-MM-DD"),
                                      ("2026-09-25", "future"), ("yesterday", "YYYY-MM-DD")])
def test_trade_date_validation(date, msg):
    """TST-IF-03: Trade dates must be canonical and not in the future [REQ-IF-03]"""
    with pytest.raises(ValueError, match=msg):
        pipeline.validate_date(date)
    assert pipeline.validate_date("2026-09-24") == "2026-09-24"


@pytest.mark.parametrize("ticker,ok", [("RHM.DE", True), ("7203.T", True), ("BTC-USD", True), ("^GSPC", True),
                                       ("GC=F", True), ("../etc", False), ("a/b", False), ("..", False), ("", False)])
def test_ticker_safety(ticker, ok):
    """TST-SAFE-01: Suffixes survive; path-escaping tickers and run ids are rejected [REQ-SAFE-01, REQ-IF-04]"""
    if ok:
        assert config.safe_component(ticker) == ticker
        assert pipeline.detect_asset_type(ticker) == {"BTC-USD": "crypto", "^GSPC": "index",
                                                      "GC=F": "commodity"}.get(ticker, "stock")
    else:
        with pytest.raises(ValueError):
            config.safe_component(ticker)


def test_atomic_write(tmp_path):
    """TST-SAFE-02: atomic_write replaces the file via rename, leaving no temp file [REQ-SAFE-02]"""
    p = tmp_path / "x" / "f.json"
    config.atomic_write(p, "one")
    config.atomic_write(p, "two")
    assert p.read_text() == "two" and [f.name for f in p.parent.iterdir()] == ["f.json"]


def test_backtest_grid_and_isolation(capsys):
    """TST-BT-01: Grid stops at today; plan uses an isolated home under backtest/ [REQ-BT-01]"""
    assert backtest.iter_grid("2026-09-01", "2026-12-31", 7) == ["2026-09-01", "2026-09-08", "2026-09-15", "2026-09-22"]
    with pytest.raises(ValueError):
        backtest.iter_grid("2026-09-10", "2026-09-01")
    with pytest.raises(ValueError):
        backtest.iter_grid("2026-9-1", "2026-09-10")
    assert main(["backtest", "plan", "NVDA,AAPL", "--start", "2026-09-01", "--end", "2026-09-10", "--every", "7",
                 "--run-id", "bt1"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["home"] == str(config.home() / "backtest" / "bt1") and len(res["cells"]) == 4
    with pytest.raises(ValueError):
        backtest.backtest_home(config.home(), "../escape")


def test_backtest_resume(tmp_path):
    """TST-BT-02: Cells already in the backtest log are skipped [REQ-BT-02]"""
    log = DecisionLog(tmp_path / "log.md")
    log.store("NVDA", "2026-09-01", "Rating: Buy")
    res = backtest.plan(["nvda", "AAPL"], ["2026-09-01", "2026-09-08"], log)
    assert res["skipped"] == 1 and {"ticker": "NVDA", "date": "2026-09-01"} not in res["cells"] and len(res["cells"]) == 3


def test_backtest_summary(tmp_path):
    """TST-BT-03: Summary counts resolved/pending/unscored and scores hit rate and mean alpha per rating [REQ-BT-03]"""
    log = DecisionLog(tmp_path / "log.md")
    rows = [("A", "Buy", 0.02), ("B", "Buy", -0.01), ("C", "Sell", -0.03), ("D", "Hold", 0.01)]
    for t, r, _ in rows:
        log.store(t, "2026-08-03", f"Rating: {r}")
    log.store("E", "2026-08-03", "no idea")
    log.store("F", "2026-09-17", "Rating: Buy")
    log.apply_outcomes([{"ticker": t, "trade_date": "2026-08-03", "raw_return": a, "alpha_return": a,
                         "holding_days": 5, "reflection": "x"} for t, _, a in rows])
    s = backtest.summarize(log)
    assert (s["resolved"], s["pending"], s["unscored"]) == (4, 1, 1)
    assert s["by_rating"]["Buy"]["hit_rate"] == 0.5 and s["by_rating"]["Buy"]["mean_alpha"] == pytest.approx(0.005)
    assert s["by_rating"]["Sell"]["hit_rate"] == 1.0 and s["by_rating"]["Hold"]["hit_rate"] is None
    text = backtest.render(s)
    assert "Buy: n=2, called the direction 50%" in text and "no direction claimed" in text


def test_backtest_never_enqueues(capsys, monkeypatch, tmp_path):
    """TST-BT-04: Runs under a backtest home are refused by enqueue [REQ-BT-04]"""
    run = config.home() / "backtest" / "bt1" / "runs" / "NVDA" / "2026-09-01"
    run.mkdir(parents=True)
    (run / "orders.json").write_text(json.dumps({"intent": {"etoro_symbol": "NVDA", "kind": "open", "rating": "Buy"}}))
    main(["enqueue", str(run), "--tag", "x"])
    out = json.loads(capsys.readouterr().out)
    assert out["queued"] == [] and "backtest runs never create orders" in out["skipped"][0]


def test_tui_optional(monkeypatch, capsys):
    """TST-UI-16: Without textual, `berkshire tui` explains the extra instead of a traceback [REQ-UI-09]"""
    import builtins
    import sys

    from berkshire.cli import main
    real_import = builtins.__import__

    def no_textual(name, *a, **kw):
        if name.startswith("textual") or name == "berkshire.tui" or (name == "tui" and a and a[2]):
            raise ImportError("No module named 'textual'")
        return real_import(name, *a, **kw)
    monkeypatch.delitem(sys.modules, "berkshire.tui", raising=False)
    monkeypatch.setattr(builtins, "__import__", no_textual)
    with pytest.raises(SystemExit) as exc:
        main(["tui"])
    assert exc.value.code == 3 and "optional 'tui' extra" in capsys.readouterr().err
