"""`berkshire` command line: the engine surface the skills drive (REQ-IF-08).

Commands print JSON (or markdown for `status`) so the orchestrating skill can
act on them. Paths live under BERKSHIRE_HOME (default ~/.berkshire).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import backtest, config, data, etoro, orders, pipeline
from .memory import DecisionLog, reflection_prompt, settle_candidates


def _paths(cfg):
    h = config.home()
    return {"home": h, "runs": h / "runs", "log": h / "memory" / "trading_memory.md",
            "queue": h / "queue.json", "settle": h / "settlements", "prefs": h / "last_run.json"}


def _log(cfg):
    return DecisionLog(_paths(cfg)["log"], cfg.get("memory_log_max_entries"))


def _print(obj):
    print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def depth_overrides(depth, debate_rounds=None, risk_rounds=None) -> dict:
    """Research depth sets both round counts; an explicit env var or flag wins (REQ-FLOW-07)."""
    import os
    rounds = None if depth is None else (pipeline.DEPTH.get(str(depth).lower()) or int(depth))
    out = {}
    for key, env, flag in (("max_debate_rounds", "BERKSHIRE_MAX_DEBATE_ROUNDS", debate_rounds),
                           ("max_risk_discuss_rounds", "BERKSHIRE_MAX_RISK_ROUNDS", risk_rounds)):
        if flag:
            out[key] = flag
        elif rounds and not os.environ.get(env):
            out[key] = rounds
    return out


def _find_quote(overview: dict, symbol: str, instrument_id) -> float | None:
    """Ask price for one instrument in a get-instruments-overview response."""
    def walk(node):
        if isinstance(node, dict):
            sym = etoro._get(node, "symbol", "symbolName")
            iid = etoro._get(node, "instrumentId", "instrumentID")
            if (sym and str(sym).upper() == symbol.upper()) or (instrument_id and iid == instrument_id):
                ask = etoro._get(node, "ask")
                if ask is not None:
                    return float(ask)
            for v in node.values():
                r = walk(v)
                if r is not None:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = walk(v)
                if r is not None:
                    return r
        return None
    return walk(overview)


def cmd_init(a, cfg):
    cfg = config.load(depth_overrides(a.depth, a.debate_rounds, a.risk_rounds)
                      | {"output_language": a.language, "deep_think_llm": a.deep_model, "quick_think_llm": a.quick_model})
    portfolio = None
    if a.portfolio:
        portfolio = etoro.load_portfolio_file(a.portfolio)
    p = _paths(cfg)
    res = pipeline.init_run(a.ticker, a.date or data.today(), cfg, results_dir=p["runs"], memory_log=_log(cfg),
                            analysts=a.analysts.split(",") if a.analysts else None, asset_type=a.asset_type,
                            portfolio=portfolio, checkpoint=a.checkpoint or cfg["checkpoint_enabled"],
                            skip_if_complete=a.skip_if_complete, etoro_symbol=a.etoro_symbol,
                            instrument_id=a.instrument_id)
    _print(res)


def cmd_next(a, cfg):
    state = pipeline.load_state(a.run_dir)
    steps = pipeline.write_prompts(state)
    _print({"done": state["complete"], "signal": state.get("signal"), "steps": steps})


def cmd_submit(a, cfg):
    state = pipeline.load_state(a.run_dir)
    due = [s["id"] for s in pipeline.next_steps(state)]
    if a.step not in due:
        raise ValueError(f"step {a.step!r} is not due; due now: {due or 'nothing (run complete)'}")
    path = Path(a.file) if a.file else Path(a.run_dir) / "outputs" / f"{a.step}.md"
    if not path.is_file():
        raise ValueError(f"no output file for step {a.step!r} at {path}")
    state = pipeline.submit(state, a.step, path.read_text(encoding="utf-8"), _log(cfg))
    _print({"completed": a.step, "complete": state["complete"], "signal": state.get("signal"),
            "report": state.get("report"), "warnings": state["warnings"],
            "next": [s["id"] for s in pipeline.next_steps(state)]})


def cmd_status(a, cfg):
    print(pipeline.progress(pipeline.load_state(a.run_dir)))


def cmd_data(a, cfg):
    state = pipeline.load_state(a.run)
    td = state["trade_date"]
    x = a.args
    try:
        if a.tool == "stock":
            out = data.tool_stock(x[0], x[1] if len(x) > 1 else None, x[2] if len(x) > 2 else td, td)
        elif a.tool == "indicators":
            out = data.tool_indicators(x[0], x[1], x[2] if len(x) > 2 else td, a.look_back or 30, td)
        elif a.tool == "snapshot":
            out = data.tool_snapshot(x[0], x[1] if len(x) > 1 else td, td, a.look_back or 30)
        elif a.tool == "fundamentals":
            out = data.tool_fundamentals(x[0], td)
        elif a.tool in ("balance_sheet", "cashflow", "income_statement"):
            out = data.tool_statement(x[0], a.tool, a.freq, td)
        elif a.tool == "insider":
            out = data.tool_insider(x[0], td)
        elif a.tool == "news":
            out = data.tool_news(x[0], x[1] if len(x) > 1 else None, x[2] if len(x) > 2 else td, td,
                                 cfg["news_article_limit"])
        elif a.tool == "global_news":
            out = data.tool_global_news(x[0] if x else td, td, cfg, a.look_back)
        else:
            out = f"Unknown tool {a.tool!r}. Tools: {', '.join(data.TOOLS)}"
    except IndexError:
        out = f"Missing arguments for {a.tool}. See the tool list in your instructions."
    except Exception as exc:  # noqa: BLE001 - REQ-DATA-06: readable error, never a traceback
        out = f"Data tool {a.tool} failed for {x}: {type(exc).__name__}: {exc}"
    print(out)


def cmd_settle(a, cfg):
    p = _paths(cfg)
    work = p["settle"] / "pending.json"
    log = _log(cfg)
    if a.apply:
        cands = _read_json(work) or []
        updates = []
        for c in cands:
            out = Path(c["output_file"])
            if out.is_file() and out.read_text(encoding="utf-8").strip():
                updates.append({**c, "reflection": out.read_text(encoding="utf-8").strip()})
        n = log.apply_outcomes(updates)
        work.unlink(missing_ok=True)
        _print({"applied": n, "missing_reflection": len(cands) - len(updates)})
        return
    tickers = None if a.all else [t.upper() for t in a.tickers]
    cands = settle_candidates(log, cfg, tickers, data.closes)
    for i, c in enumerate(cands):
        c["id"] = f"{c['ticker']}_{c['trade_date']}"
        c["prompt_file"] = str(p["settle"] / f"{c['id']}.prompt.md")
        c["output_file"] = str(p["settle"] / f"{c['id']}.reflection.md")
        config.atomic_write(Path(c["prompt_file"]), reflection_prompt(c)
                            + f"\n\nWrite your reflection to this file with the Write tool: `{c['output_file']}`")
    config.atomic_write(work, json.dumps(cands, indent=2, default=str))
    _print({"to_reflect": [{k: c[k] for k in ("id", "prompt_file", "output_file")} for c in cands],
            "agent": "berkshire:reflector", "model": cfg["quick_think_llm"]})


def cmd_gate(a, cfg):
    state = pipeline.load_state(a.run_dir)
    if not state["complete"]:
        raise ValueError("run is not complete")
    portfolio = etoro.load_portfolio_file(a.portfolio_file) if a.portfolio_file else state["portfolio"]
    sym = state.get("etoro_symbol") or state["company_of_interest"]
    ask = a.ask if a.ask is not None else _find_quote(_read_json(a.quote_file) or {}, sym, state.get("instrument_id"))
    atr = a.atr if a.atr is not None else data.latest_atr(state["company_of_interest"], state["trade_date"])
    res = orders.gate(ticker=state["company_of_interest"], etoro_symbol=sym, instrument_id=state.get("instrument_id"),
                      rating=state["signal"], portfolio=portfolio or {}, ask=ask,
                      trader=state["structured"].get("trader_proposal"), pm=state["structured"].get("pm_decision"),
                      atr=atr, cfg=cfg)
    config.atomic_write(Path(a.run_dir) / "orders.json", json.dumps(res, indent=2))  # REQ-RISK-09
    _print(res)


def cmd_enqueue(a, cfg):
    """Queue gated intents. A run is queued at most once (a re-run tick cannot
    double-order), and backtest runs never are (REQ-BT-04)."""
    intents, sources, skipped = [], [], []
    for rd in a.run_dirs:
        f = Path(rd) / "orders.json"
        if "backtest" in Path(rd).resolve().parts:
            skipped.append(f"{rd}: backtest runs never create orders")
            continue
        res = _read_json(f) if f.is_file() else {}
        if res.get("queued"):
            skipped.append(f"{rd}: already queued as {res['queued']}")
        elif res.get("intent"):
            intents.append(res["intent"])
            sources.append((f, res))
    q = orders.Queue(_paths(cfg)["queue"])
    q.expire(cfg["queue_ttl_hours"])
    added = q.enqueue(intents, a.tag, int(cfg["max_orders_per_run"]))
    by_symbol = {i["intent"]["etoro_symbol"]: i["id"] for i in added}
    for f, res in sources:
        qid = by_symbol.get(res["intent"]["etoro_symbol"])
        config.atomic_write(f, json.dumps({**res, "queued": qid or "dropped (max_orders_per_run)"}, indent=2))
    _print({"queued": added, "dropped": len(intents) - len(added), "skipped": skipped})


def cmd_queue(a, cfg):
    q = orders.Queue(_paths(cfg)["queue"])
    if a.action == "list":
        q.expire(cfg["queue_ttl_hours"])
        _print(q.load() if a.all else q.pending())
    elif a.action == "mark":
        _print(q.mark(a.id, a.status, _read_json(a.result_file)))
    elif a.action == "expire":
        _print({"expired": q.expire(cfg["queue_ttl_hours"])})


def cmd_etoro_portfolio(a, cfg):
    p = etoro.from_etoro_summary(_read_json(a.summary_file))
    config.atomic_write(Path(a.out), json.dumps(p, indent=2))
    _print(p)


def cmd_universe(a, cfg):
    portfolio = etoro.load_portfolio_file(a.portfolio_file) if a.portfolio_file else None
    items, skipped = etoro.universe(portfolio, _read_json(a.watchlists_file), a.watchlist or cfg["watchlist_name"],
                                    cfg["symbol_map"], int(cfg["max_tickers_per_tick"]))
    _print({"date": a.date or data.today(), "trading_day": is_trading_day(a.date or data.today()),
            "instruments": items, "skipped": skipped})


def is_trading_day(date: str) -> bool:
    """Weekdays only (REQ-SCHED-02); exchange holidays surface as stale data, not an error."""
    return datetime.strptime(date, "%Y-%m-%d").weekday() < 5


def cmd_clear(a, cfg):
    runs, removed = _paths(cfg)["runs"], []
    for sf in runs.glob("*/*/state.json") if runs.exists() else []:
        if not json.loads(sf.read_text(encoding="utf-8")).get("complete"):
            import shutil
            shutil.rmtree(sf.parent)
            removed.append(str(sf.parent))
    _print({"removed": removed})


def cmd_backtest(a, cfg):
    if a.action == "plan":
        run_id = a.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        home = backtest.backtest_home(config.home(), run_id)
        log = DecisionLog(home / "memory" / "trading_memory.md")
        res = backtest.plan(a.tickers.split(","), backtest.iter_grid(a.start, a.end, a.every), log)
        _print({"run_id": run_id, "home": str(home), **res})
    else:
        log = DecisionLog(backtest.backtest_home(config.home(), a.run_id) / "memory" / "trading_memory.md")
        s = backtest.summarize(log)
        print(backtest.render(s) if not a.json else json.dumps(s, indent=2))


def cmd_prefs(a, cfg):
    f = _paths(cfg)["prefs"]
    if a.action == "set":
        config.atomic_write(f, json.dumps(json.loads(a.value), indent=2))
    _print(_read_json(f) if f.exists() else {})


def cmd_config(a, cfg):
    _print(cfg)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="berkshire", description="Berkshire multi-agent trading engine")
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("init", help="create or resume a run")
    s.add_argument("ticker"); s.add_argument("date", nargs="?")
    s.add_argument("--analysts"); s.add_argument("--depth"); s.add_argument("--language")
    s.add_argument("--debate-rounds", type=int); s.add_argument("--risk-rounds", type=int)
    s.add_argument("--asset-type", choices=["stock", "crypto"]); s.add_argument("--portfolio")
    s.add_argument("--checkpoint", action="store_true"); s.add_argument("--skip-if-complete", action="store_true")
    s.add_argument("--etoro-symbol"); s.add_argument("--instrument-id", type=int)
    s.add_argument("--deep-model"); s.add_argument("--quick-model")
    s.set_defaults(fn=cmd_init)

    for name, fn in (("next", cmd_next), ("status", cmd_status)):
        s = sp.add_parser(name); s.add_argument("run_dir"); s.set_defaults(fn=fn)
    s = sp.add_parser("submit"); s.add_argument("run_dir"); s.add_argument("step"); s.add_argument("--file")
    s.set_defaults(fn=cmd_submit)

    s = sp.add_parser("data", help="point-in-time data tools for analysts")
    s.add_argument("--run", required=True); s.add_argument("tool"); s.add_argument("args", nargs="*")
    s.add_argument("--look-back", type=int); s.add_argument("--freq", default="quarterly", choices=["quarterly", "annual"])
    s.set_defaults(fn=cmd_data)

    s = sp.add_parser("settle"); s.add_argument("tickers", nargs="*"); s.add_argument("--all", action="store_true")
    s.add_argument("--apply", action="store_true"); s.set_defaults(fn=cmd_settle)

    s = sp.add_parser("gate", help="risk gate for a completed run")
    s.add_argument("run_dir"); s.add_argument("--quote-file"); s.add_argument("--portfolio-file")
    s.add_argument("--ask", type=float); s.add_argument("--atr", type=float); s.set_defaults(fn=cmd_gate)

    s = sp.add_parser("enqueue"); s.add_argument("run_dirs", nargs="*"); s.add_argument("--tag", required=True)
    s.set_defaults(fn=cmd_enqueue)

    s = sp.add_parser("queue"); s.add_argument("action", choices=["list", "mark", "expire"])
    s.add_argument("id", nargs="?"); s.add_argument("status", nargs="?"); s.add_argument("--result-file")
    s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_queue)

    s = sp.add_parser("etoro-portfolio"); s.add_argument("summary_file"); s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_etoro_portfolio)

    s = sp.add_parser("universe"); s.add_argument("--portfolio-file"); s.add_argument("--watchlists-file")
    s.add_argument("--watchlist"); s.add_argument("--date"); s.set_defaults(fn=cmd_universe)

    sp.add_parser("clear-checkpoints").set_defaults(fn=cmd_clear)

    s = sp.add_parser("backtest"); s.add_argument("action", choices=["plan", "summary"])
    s.add_argument("tickers", nargs="?"); s.add_argument("--start"); s.add_argument("--end")
    s.add_argument("--every", type=int, default=7); s.add_argument("--run-id"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_backtest)

    s = sp.add_parser("prefs"); s.add_argument("action", choices=["get", "set"]); s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_prefs)
    sp.add_parser("config").set_defaults(fn=cmd_config)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        a.fn(a, config.load())
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    return 0
