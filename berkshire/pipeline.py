"""The deterministic graph engine: run state, routing, per-step context, reports.

The LLM nodes are Claude subagents. This module decides which step is due
(`next_steps`), writes that step's context prompt, and folds the agent's output
back into `state.json` (`submit`). The routing ports TradingAgents'
graph/setup.py + conditional_logic.py (REQ-FLOW), and the context builders port
the agent prompt bodies and grounding guards (REQ-CTX).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from . import data as data_mod
from .config import atomic_write, safe_component
from .decisions import parse_rating, structured
from .etoro import fingerprint, render_portfolio
from .memory import DecisionLog

ANALYSTS = ("market", "social", "news", "fundamentals")
ANALYST_AGENT = {"market": "market-analyst", "social": "sentiment-analyst",
                 "news": "news-analyst", "fundamentals": "fundamentals-analyst"}
REPORT_KEY = {"market": "market_report", "social": "sentiment_report",
              "news": "news_report", "fundamentals": "fundamentals_report"}
DEPTH = {"shallow": 1, "medium": 3, "deep": 5}
DEEP_AGENTS = ("research-manager", "portfolio-manager")
DISCLAIMER = ("> Research output from a multi-agent LLM system. It is not financial, investment, or trading "
              "advice. Every order requires explicit human approval.")


# --- validation (REQ-IF-03/04, REQ-FLOW-05/06) ------------------------------

def validate_date(value: str) -> str:
    try:
        ok = datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y-%m-%d") == str(value)
    except ValueError:
        ok = False
    if not ok:
        raise ValueError(f"trade_date must be a date in YYYY-MM-DD format, got {value!r}")
    if value > data_mod.today():
        raise ValueError(f"trade_date cannot be in the future: {value}")
    return value


def detect_asset_type(ticker: str) -> str:
    return "crypto" if ticker.upper().endswith("-USD") else "stock"


def select_analysts(selection, asset_type: str) -> list[str]:
    chosen = [a.strip().lower() for a in (selection or ANALYSTS) if a and a.strip()]
    unknown = [a for a in chosen if a not in ANALYSTS]
    if unknown:
        raise ValueError(f"unknown analyst(s): {', '.join(unknown)}; choose from {', '.join(ANALYSTS)}")
    ordered = [a for a in ANALYSTS if a in chosen]
    if asset_type == "crypto":
        ordered = [a for a in ordered if a != "fundamentals"]
    if not ordered:
        raise ValueError("at least one analyst must be selected")
    return ordered


# --- context helpers (REQ-CTX) ----------------------------------------------

def instrument_context(ticker: str, asset_type: str, identity: dict, trade_date: str) -> str:
    crypto = asset_type == "crypto"
    ctx = (f"The {'asset' if crypto else 'instrument'} to analyze is `{ticker}`. Use this exact ticker in every "
           "tool call, report, and recommendation, preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, "
           "`.T`, `-USD`).")
    details = []
    if identity.get("company_name"):
        details.append(f"{'Name' if crypto else 'Company'}: {identity['company_name']}")
    sector, industry = identity.get("sector"), identity.get("industry")
    if sector and industry:
        details.append(f"Business classification: {sector} / {industry}")
    elif sector or industry:
        details.append(f"{'Sector' if sector else 'Industry'}: {sector or industry}")
    if identity.get("exchange"):
        details.append(f"Exchange: {identity['exchange']}")
    if details:
        ctx += (f" Resolved identity: {'; '.join(details)}. Do not substitute a different company or ticker "
                "unless a tool result explicitly disproves this resolved identity.")
        if trade_date < data_mod.today():
            ctx += (f" This identity is how the vendor describes the instrument today, not necessarily on "
                    f"{trade_date}: a name or classification changed since then would read as the current one.")
    if crypto:
        ctx += " Treat it as a crypto asset rather than a company, and do not assume company fundamentals are available."
    return ctx


def report_or_absent(text: str, source: str) -> str:
    text = (text or "").strip()
    return text or f"(No {source} report in this run: it is not available, not an empty finding.)"


def opponent_or_opening(text: str, opponent: str) -> str:
    text = (text or "").strip()
    return text or f"(The {opponent} has not spoken yet — open the debate with your own case.)"


def language_instruction(lang: str) -> str:
    return "" if (lang or "English").strip().lower() == "english" else f" Write your entire response in {lang}."


# --- state ------------------------------------------------------------------

def run_dir(results_dir: str | Path, ticker: str, trade_date: str) -> Path:
    return Path(results_dir).expanduser() / safe_component(ticker) / safe_component(trade_date)


def load_state(rdir: Path) -> dict:
    return json.loads((Path(rdir) / "state.json").read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    atomic_write(Path(state["run_dir"]) / "state.json", json.dumps(state, indent=2, ensure_ascii=False))


def signature(analysts, cfg, asset_type, portfolio) -> str:
    return "|".join([f"analysts={','.join(analysts)}", f"debate={cfg['max_debate_rounds']}",
                     f"risk={cfg['max_risk_discuss_rounds']}", f"asset={asset_type}",
                     f"portfolio={fingerprint(portfolio)}", f"language={cfg['output_language']}"])


def init_run(ticker: str, trade_date: str, cfg: dict, *, results_dir, memory_log: DecisionLog,
             analysts=None, asset_type: str | None = None, portfolio: dict | None = None,
             checkpoint: bool = False, skip_if_complete: bool = False,
             etoro_symbol: str | None = None, instrument_id=None, identity: dict | None = None) -> dict:
    """Create (or resume) a run. Returns a summary dict (REQ-CKPT-02/03)."""
    ticker = safe_component(ticker.strip().upper())
    trade_date = validate_date(trade_date)
    asset_type = asset_type or detect_asset_type(ticker)
    chosen = select_analysts(analysts, asset_type)
    sig = signature(chosen, cfg, asset_type, portfolio)
    rdir = run_dir(results_dir, ticker, trade_date)

    if (rdir / "state.json").exists():
        old = load_state(rdir)
        if old.get("complete") and skip_if_complete:
            return {"run_dir": str(rdir), "skipped": True, "signal": old.get("signal"), "resumed": False}
        if not old.get("complete") and checkpoint and old.get("signature") == sig:
            return {"run_dir": str(rdir), "skipped": False, "resumed": True, "completed": old["completed"]}
        shutil.rmtree(rdir)

    identity = data_mod.profile(ticker) if identity is None else identity
    as_of = trade_date if trade_date < data_mod.today() else None  # REQ-MEM-05
    state = {
        "run_dir": str(rdir), "company_of_interest": ticker, "trade_date": trade_date,
        "asset_type": asset_type, "etoro_symbol": etoro_symbol, "instrument_id": instrument_id,
        "analysts": chosen, "signature": sig, "config": {k: cfg[k] for k in (
            "max_debate_rounds", "max_risk_discuss_rounds", "output_language",
            "deep_think_llm", "quick_think_llm")},
        "instrument_context": instrument_context(ticker, asset_type, identity, trade_date),
        "past_context": memory_log.past_context(ticker, as_of=as_of),
        "portfolio": portfolio,
        "portfolio_context": render_portfolio(portfolio, etoro_symbol or ticker),
        "market_report": "", "sentiment_report": "", "news_report": "", "fundamentals_report": "",
        "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "",
                                    "current_response": "", "judge_decision": "", "count": 0},
        "investment_plan": "", "trader_investment_plan": "",
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "", "neutral_history": "",
                              "history": "", "latest_speaker": "", "current_aggressive_response": "",
                              "current_conservative_response": "", "current_neutral_response": "",
                              "judge_decision": "", "count": 0},
        "final_trade_decision": "", "structured": {}, "warnings": [],
        "completed": [], "complete": False, "signal": None,
    }
    save_state(state)
    return {"run_dir": str(rdir), "skipped": False, "resumed": False, "completed": []}


# --- routing (REQ-FLOW-01..04, 08) ------------------------------------------

def _step(state: dict, step_id: str, agent: str) -> dict:
    cfg = state["config"]
    rdir = Path(state["run_dir"])
    return {"id": step_id, "agent": f"berkshire:{agent}",
            "model": cfg["deep_think_llm"] if agent in DEEP_AGENTS else cfg["quick_think_llm"],
            "prompt_file": str(rdir / "prompts" / f"{step_id}.md"),
            "output_file": str(rdir / "outputs" / f"{step_id}.md")}


def next_steps(state: dict) -> list[dict]:
    if state["complete"]:
        return []
    done = set(state["completed"])
    todo = [a for a in state["analysts"] if f"analyst_{a}" not in done]
    if todo:  # independent: offered together (REQ-FLOW-02)
        return [_step(state, f"analyst_{a}", ANALYST_AGENT[a]) for a in todo]
    inv, rounds = state["investment_debate_state"], state["config"]["max_debate_rounds"]
    if inv["count"] < 2 * rounds:
        who = "bear" if inv["current_response"].startswith("Bull") else "bull"
        return [_step(state, f"{who}_{inv['count'] + 1}", f"{who}-researcher")]
    if "research_manager" not in done:
        return [_step(state, "research_manager", "research-manager")]
    if "trader" not in done:
        return [_step(state, "trader", "trader")]
    risk, rrounds = state["risk_debate_state"], state["config"]["max_risk_discuss_rounds"]
    if risk["count"] < 3 * rrounds:
        who = {"Aggressive": "conservative", "Conservative": "neutral"}.get(risk["latest_speaker"], "aggressive")
        return [_step(state, f"{who}_{risk['count'] + 1}", f"{who}-analyst")]
    return [_step(state, "portfolio_manager", "portfolio-manager")]


# --- per-step context (REQ-CTX, REQ-DATA-07) ---------------------------------

def _reports(state: dict) -> dict:
    return {k: report_or_absent(state[f"{k}_report"], k) for k in ("market", "sentiment", "news", "fundamentals")}


def build_prompt(state: dict, step: dict) -> str:
    sid, rdir, date = step["id"], state["run_dir"], state["trade_date"]
    lang = language_instruction(state["config"]["output_language"])
    ic = state["instrument_context"]
    out = f"\n\nWrite your complete answer to this file with the Write tool: `{step['output_file']}`"
    historical = date < data_mod.today()
    pit = (f"\n\nPoint-in-time rule: this run is dated {date}. Web search, social feeds and the company profile "
           "describe the present, not that date; label any such evidence as current and prefer dated items "
           f"published on or before {date}." if historical else "")

    if sid.startswith("analyst_"):
        return (f"Today's date is {date}; treat it as 'now' for all analysis and tool-call date ranges. {ic}\n\n"
                f"Run your data tools with Bash as `berkshire data --run {rdir} <tool> ...` (dates after {date} "
                f"are clamped automatically). Report what your tools support; another agent decides the trade."
                f"{pit}{lang}{out}")

    r = _reports(state)
    inv, risk = state["investment_debate_state"], state["risk_debate_state"]
    if sid.startswith(("bull_", "bear_")):
        bull = sid.startswith("bull_")
        target = "stock" if state["asset_type"] == "stock" else "asset"
        flabel = "Company fundamentals report" if state["asset_type"] == "stock" else \
            "Asset fundamentals report (may be unavailable for crypto)"
        opp = opponent_or_opening(inv["current_response"], "bear analyst" if bull else "bull analyst")
        return (f"Resources available:\n\n{ic}\nMarket research report: {r['market']}\n"
                f"Social media sentiment report: {r['sentiment']}\nLatest world affairs news: {r['news']}\n"
                f"{flabel}: {r['fundamentals']}\nConversation history of the debate: {inv['history']}\n"
                f"Last {'bear' if bull else 'bull'} argument: {opp}\n\nUse this information to deliver a "
                f"compelling {'bull' if bull else 'bear'} argument about the {target}.{lang}{out}")

    if sid == "research_manager":
        return f"{ic}\n\n**Debate History:**\n{inv['history']}{lang}{out}"

    if sid == "trader":
        mr = (state["market_report"] or "").strip()
        grounding = ("Ground concrete price levels (entry, stop-loss, position sizing) in the technical market "
                     "report's price structure -- current price, support/resistance, ATR, and volatility -- and "
                     "use the research plan for direction and strategy.\n\n"
                     f"Technical Market Report:\n{mr}\n\n") if mr else ""
        return (f"Here is the research team's investment plan for {state['company_of_interest']}. {ic}\n\n"
                f"{grounding}{state['portfolio_context']}\n\nProposed Investment Plan:\n{state['investment_plan']}"
                f"\n\nMake an informed, strategic trading decision.{lang}{out}")

    if sid.startswith(("aggressive_", "conservative_", "neutral_")):
        me = sid.split("_")[0]
        others = [o for o in ("aggressive", "conservative", "neutral") if o != me]
        last = "\n".join(f"Here are the last arguments from the {o} analyst: "
                         f"{opponent_or_opening(risk[f'current_{o}_response'], o + ' analyst')}" for o in others)
        return (f"Here is the trader's decision:\n\n{state['trader_investment_plan']}\n\n{ic}\n"
                f"{state['portfolio_context']}\nMarket Research Report: {r['market']}\n"
                f"Social Media Sentiment Report: {r['sentiment']}\nLatest World Affairs Report: {r['news']}\n"
                f"Company Fundamentals Report: {r['fundamentals']}\nHere is the current conversation history: "
                f"{risk['history']}\n{last}\nIf there are no responses from the other viewpoints yet, present "
                f"your own argument based on the available data.{lang}{out}")

    if sid == "portfolio_manager":
        lessons = (f"- Lessons from prior decisions and outcomes:\n{state['past_context']}\n"
                   if state["past_context"] else "")
        return (f"{ic}\n\n{state['portfolio_context']}\n\n---\n\n**Context:**\n"
                f"- Research Manager's investment plan: **{state['investment_plan']}**\n"
                f"- Trader's transaction proposal: **{state['trader_investment_plan']}**\n{lessons}\n"
                f"**Risk Analysts Debate History:**\n{risk['history']}{lang}{out}")
    raise ValueError(f"unknown step {sid!r}")


def write_prompts(state: dict) -> list[dict]:
    steps = next_steps(state)
    for s in steps:
        atomic_write(Path(s["prompt_file"]), build_prompt(state, s))
    return steps


# --- submit (REQ-FLOW-09, REQ-OUT, REQ-CKPT-01) -----------------------------

def submit(state: dict, step_id: str, text: str, memory_log: DecisionLog | None = None) -> dict:
    due = {s["id"] for s in next_steps(state)}
    if step_id not in due:
        raise ValueError(f"step {step_id!r} is not due; due now: {sorted(due) or 'nothing (run complete)'}")
    text = (text or "").strip()
    if not text:
        raise ValueError(f"step {step_id!r} produced no output")

    def use_schema(schema):
        md, parsed, err = structured(text, schema)
        if parsed is not None:
            state["structured"][schema] = parsed
        if err:
            state["warnings"].append(f"{step_id}: {err}; used free text")
        return md

    if step_id.startswith("analyst_"):
        key = step_id.removeprefix("analyst_")
        state[REPORT_KEY[key]] = use_schema("sentiment") if key == "social" else text
    elif step_id.startswith(("bull_", "bear_")):
        who = "Bull" if step_id.startswith("bull_") else "Bear"
        arg = f"{who} Analyst: {text}"
        inv = state["investment_debate_state"]
        inv["history"] += "\n" + arg
        inv[f"{who.lower()}_history"] += "\n" + arg
        inv["current_response"] = arg
        inv["count"] += 1
    elif step_id == "research_manager":
        plan = use_schema("research_plan")
        state["investment_plan"] = plan
        state["investment_debate_state"]["judge_decision"] = plan
    elif step_id == "trader":
        state["trader_investment_plan"] = use_schema("trader_proposal")
    elif step_id.startswith(("aggressive_", "conservative_", "neutral_")):
        who = step_id.split("_")[0]
        arg = f"{who.capitalize()} Analyst: {text}"
        risk = state["risk_debate_state"]
        risk["history"] += "\n" + arg
        risk[f"{who}_history"] += "\n" + arg
        risk[f"current_{who}_response"] = arg
        risk["latest_speaker"] = who.capitalize()
        risk["count"] += 1
    elif step_id == "portfolio_manager":
        decision = use_schema("pm_decision")
        state["final_trade_decision"] = decision
        state["risk_debate_state"]["judge_decision"] = decision
        state["risk_debate_state"]["latest_speaker"] = "Judge"
        state["signal"] = parse_rating(decision)  # REQ-OUT-04/05
    state["completed"].append(step_id)
    if step_id == "portfolio_manager":
        finalize(state, memory_log)
    save_state(state)
    return state


# --- reports (REQ-RPT, REQ-MEM-01) ------------------------------------------

def write_report_tree(state: dict, save_path: Path) -> Path:
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    def put(rel, text):
        p = save_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    parts = []
    for name, key, rel in (("Market Analyst", "market_report", "market"), ("Sentiment Analyst", "sentiment_report", "sentiment"),
                           ("News Analyst", "news_report", "news"), ("Fundamentals Analyst", "fundamentals_report", "fundamentals")):
        if state.get(key):
            put(f"1_analysts/{rel}.md", state[key])
            parts.append(f"### {name}\n{state[key]}")
    if parts:
        sections.append("## I. Analyst Team Reports\n\n" + "\n\n".join(parts))
    inv, parts = state["investment_debate_state"], []
    for name, key, rel in (("Bull Researcher", "bull_history", "bull"), ("Bear Researcher", "bear_history", "bear"),
                           ("Research Manager", "judge_decision", "manager")):
        if inv.get(key):
            put(f"2_research/{rel}.md", inv[key])
            parts.append(f"### {name}\n{inv[key]}")
    if parts:
        sections.append("## II. Research Team Decision\n\n" + "\n\n".join(parts))
    if state.get("trader_investment_plan"):
        put("3_trading/trader.md", state["trader_investment_plan"])
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{state['trader_investment_plan']}")
    risk, parts = state["risk_debate_state"], []
    for name, key, rel in (("Aggressive Analyst", "aggressive_history", "aggressive"),
                           ("Conservative Analyst", "conservative_history", "conservative"),
                           ("Neutral Analyst", "neutral_history", "neutral")):
        if risk.get(key):
            put(f"4_risk/{rel}.md", risk[key])
            parts.append(f"### {name}\n{risk[key]}")
    if parts:
        sections.append("## IV. Risk Management Team Decision\n\n" + "\n\n".join(parts))
    if risk.get("judge_decision"):
        put("5_portfolio/decision.md", risk["judge_decision"])
        sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}")
    header = (f"# Trading Analysis Report: {state['company_of_interest']}\n\nAnalysis date: {state['trade_date']} · "
              f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S} · Signal: **{state.get('signal')}**\n\n{DISCLAIMER}\n\n")
    put("complete_report.md", header + "\n\n".join(sections))
    return save_path / "complete_report.md"


def full_states_log(state: dict) -> dict:
    inv, risk = state["investment_debate_state"], state["risk_debate_state"]
    return {
        "company_of_interest": state["company_of_interest"], "trade_date": state["trade_date"],
        "market_report": state["market_report"], "sentiment_report": state["sentiment_report"],
        "news_report": state["news_report"], "fundamentals_report": state["fundamentals_report"],
        "investment_debate_state": {k: inv[k] for k in ("bull_history", "bear_history", "history",
                                                        "current_response", "judge_decision")},
        "trader_investment_decision": state["trader_investment_plan"],
        "risk_debate_state": {k: risk[k] for k in ("aggressive_history", "conservative_history",
                                                   "neutral_history", "history", "judge_decision")},
        "investment_plan": state["investment_plan"], "final_trade_decision": state["final_trade_decision"],
    }


def finalize(state: dict, memory_log: DecisionLog | None) -> None:
    rdir = Path(state["run_dir"])
    state["report"] = str(write_report_tree(state, rdir / "reports"))
    atomic_write(rdir / f"full_states_log_{state['trade_date']}.json",
                 json.dumps(full_states_log(state), indent=4, ensure_ascii=False))
    if memory_log is not None:
        memory_log.store(state["company_of_interest"], state["trade_date"], state["final_trade_decision"])
    state["complete"] = True


# --- progress (REQ-IF-06) ---------------------------------------------------

TEAMS = (("Analyst Team", None), ("Research Team", ("bull", "bear", "research_manager")),
         ("Trading Team", ("trader",)), ("Risk Management", ("aggressive", "conservative", "neutral")),
         ("Portfolio Management", ("portfolio_manager",)))


def progress(state: dict) -> str:
    done = state["completed"]
    due = {s["id"] for s in next_steps(state)}

    def status(prefix: str) -> str:
        ids = [d for d in done if d == prefix or d.startswith(prefix + "_")]
        if any(d == prefix or d.startswith(prefix + "_") for d in due):
            return "in progress"
        if prefix in ("bull", "bear"):
            total = state["config"]["max_debate_rounds"]
            return "done" if len(ids) >= total else ("in progress" if ids else "pending")
        if prefix in ("aggressive", "conservative", "neutral"):
            total = state["config"]["max_risk_discuss_rounds"]
            return "done" if len(ids) >= total else ("in progress" if ids else "pending")
        return "done" if ids else "pending"

    rows = []
    for team, members in TEAMS:
        for m in members or [f"analyst_{a}" for a in state["analysts"]]:
            label = m.removeprefix("analyst_").replace("_", " ").title()
            rows.append(f"| {team} | {label} | {status(m)} |")
    last = done[-1] if done else None
    return (f"**{state['company_of_interest']} · {state['trade_date']}** — "
            f"{len(done)} steps done{' · signal ' + state['signal'] if state.get('signal') else ''}\n\n"
            "| Team | Agent | Status |\n|---|---|---|\n" + "\n".join(rows)
            + (f"\n\nLatest: `{last}`" if last else ""))
