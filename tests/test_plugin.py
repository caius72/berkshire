"""Inspection tests over the plugin files: roles, tool boundaries, execution guardrails."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("market-analyst", "sentiment-analyst", "news-analyst", "fundamentals-analyst", "bull-researcher",
         "bear-researcher", "research-manager", "trader", "aggressive-analyst", "conservative-analyst",
         "neutral-analyst", "portfolio-manager", "reflector")
NO_WEB = ("bull-researcher", "bear-researcher", "research-manager", "trader", "aggressive-analyst",
          "conservative-analyst", "neutral-analyst", "portfolio-manager", "reflector")


def front(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    assert m, f"{path} has no frontmatter"
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)
    return meta, m.group(2)


def agent(name):
    return front(ROOT / "agents" / f"{name}.md")


def skill(name):
    return front(ROOT / "skills" / name / "SKILL.md")


def tools(name):
    return {t.strip() for t in agent(name)[0]["tools"].split(",")}


def test_all_roles_present():
    """TST-ROLE-01: One valid subagent per TradingAgents role plus the Reflector [REQ-ROLE-01]"""
    assert sorted(p.stem for p in (ROOT / "agents").glob("*.md")) == sorted(ROLES)
    for name in ROLES:
        meta, body = agent(name)
        assert meta["name"] == name and meta["description"] and meta["model"] in ("opus", "sonnet", "haiku", "fable")
        assert "DONE <output file>" in body  # file-based hand-off protocol
    assert json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["name"] == "berkshire"


def test_analyst_data_access():
    """TST-ROLE-03: Analysts get their TradingAgents data sources [REQ-ROLE-03]"""
    assert {"Bash", "Read", "Write"} <= tools("market-analyst") and "WebSearch" not in tools("market-analyst")
    assert {"Bash", "Read", "Write"} <= tools("fundamentals-analyst")
    for name in ("news-analyst", "sentiment-analyst"):
        assert {"Bash", "WebSearch", "WebFetch"} <= tools(name)
    body = {n: agent(n)[1] for n in ("market-analyst", "fundamentals-analyst", "news-analyst", "sentiment-analyst")}
    for t in ("stock", "indicators", "snapshot"):
        assert f"`{t}`" in body["market-analyst"]
    for t in ("fundamentals", "valuation", "earnings", "etf_profile", "balance_sheet", "cashflow", "income_statement", "insider"):
        assert f"`{t}`" in body["fundamentals-analyst"]
    assert "global_news" in body["news-analyst"] and "FRED" in body["news-analyst"] and "Polymarket" in body["news-analyst"]
    assert "Google News, headline only" in body["news-analyst"] and "WebFetch the article" in body["news-analyst"]
    assert "stocktwits" in body["sentiment-analyst"].lower() and "reddit" in body["sentiment-analyst"].lower()


def test_deciders_have_no_external_tools():
    """TST-ROLE-04: Researchers, debaters, managers and Trader have only Read/Write [REQ-ROLE-04]"""
    for name in NO_WEB:
        assert tools(name) <= {"Read", "Write"}, name


def test_tool_using_agents_have_turn_bound():
    """TST-ROLE-12: Every analyst with data or web tools declares a turn bound, and the pipeline loop treats a stop without output as a failed step [REQ-ROLE-07, REQ-SCHED-05]"""
    bounded = [n for n in ROLES if tools(n) & {"Bash", "WebSearch", "WebFetch"}]
    assert sorted(bounded) == ["fundamentals-analyst", "market-analyst", "news-analyst", "sentiment-analyst"]
    for name in bounded:
        assert int(agent(name)[0].get("maxTurns", "0")) > 0, name
    for name in NO_WEB:
        assert "maxTurns" not in agent(name)[0], name
    loop = (ROOT / "skills" / "analyze" / "pipeline-loop.md").read_text()
    assert "stopped at its turn limit (`maxTurns`)" in loop and "Re-run that\n     one step once" in loop


def test_syndicated_copies_count_once():
    """TST-ROLE-13: The News and Sentiment Analysts count a syndicated story once, not as independent confirmation [REQ-ROLE-03]"""
    for name in ("news-analyst", "sentiment-analyst"):
        body = agent(name)[1]
        assert "re-headlined by several outlets (wire copies, aggregators)" in body, name
        assert "not independent confirmation" in body and "Count a story once" in body, name


PERSONA = {
    "bull-researcher": ["Growth Potential", "Competitive Advantages", "Bear Counterpoints", "open with your own case"],
    "bear-researcher": ["Risks and Challenges", "Competitive Weaknesses", "Bull Counterpoints"],
    "research-manager": ["**Buy**", "**Underweight**", "conflict alone is not a reason to Hold",
                         "regardless of which side spoke first or last", '"recommendation"'],
    "trader": ["absolute price levels", "never as a percentage or a range", "Overweight is a Buy", '"stop_loss"',
               '"target_price"', "do not state a ratio yourself"],
    "aggressive-analyst": ["high-reward, high-risk"], "conservative-analyst": ["protect assets, minimize volatility"],
    "neutral-analyst": ["balanced perspective"],
    "portfolio-manager": ["**Rating Scale**", "conflict alone is not a reason to Hold", "lessons from prior decisions",
                          '"price_target"'],
    "market-analyst": ["source of truth", "flag the discrepancy", "Markdown table"],
    "fundamentals-analyst": ["red flags", "Markdown table"], "news-analyst": ["Markdown table"],
    "sentiment-analyst": ["70/30", "Distinguish opinion from event", '"overall_score"'],
    "reflector": ["2-4 sentences", "too short to judge", "implied move", "not a failure"],
}


@pytest.mark.parametrize("name", sorted(PERSONA))
def test_persona_directives(name):
    """TST-ROLE-05: Each persona keeps the TradingAgents prompt's substantive directives [REQ-ROLE-05]"""
    body = agent(name)[1]
    for phrase in PERSONA[name]:
        assert phrase in body, f"{name}: missing {phrase!r}"


def test_market_indicator_catalogue():
    """TST-ROLE-06: Market Analyst picks up to 8 indicators from the full catalogue [REQ-ROLE-06]"""
    from berkshire.data import INDICATORS
    body = agent("market-analyst")[1]
    assert "up to **8 indicators**" in body
    for name in INDICATORS:
        assert f"- {name}:" in body


def test_orders_only_via_dedicated_tools():
    """TST-EXE-01: Opens/closes go through prepare/place tools, never execute-write [REQ-EXE-01]"""
    _, body = skill("approve")
    for t in ("prepare-trade", "place-trade", "prepare-close", "place-close"):
        assert t in body
    assert "never use\n`execute-write`" in body or "never use `execute-write`" in body
    for name in ("analyze", "tick", "approve", "backtest"):
        meta, _ = skill(name)
        assert not re.search(r"place-(trade|close)|execute-write", meta.get("allowed-tools", "")), name


def test_human_approval_gate():
    """TST-EXE-02: place-* only after a per-order AskUserQuestion; unattended skills never place [REQ-EXE-02]"""
    _, approve = skill("approve")
    assert "One approval per order, and one approval per eToro call" in approve
    assert approve.index("AskUserQuestion") < approve.index("then `place-trade` with the token")
    _, tick = skill("tick")
    assert "never places orders" in tick and "Ask the user nothing" in tick
    assert "place-trade` or `place-close` from this skill" in skill("analyze")[1]
    assert "Never run `gate`, `enqueue`, or any eToro tool" in skill("backtest")[1]


def test_account_shown_in_confirmation():
    """TST-EXE-08: The approval confirmation names the account (DEMO/REAL) [REQ-EXE-03]"""
    assert "the account (DEMO or REAL)" in skill("approve")[1]


def test_pending_and_unknown_outcomes():
    """TST-EXE-05: pending is never re-placed; unknown retries once with the same token [REQ-EXE-05]"""
    body = skill("approve")[1]
    assert "`pending` → `pending_fill` (do NOT place again)" in body
    assert "retry `place-trade`\n     once with the **same token**" in body or "once with the **same token**" in body


def test_settle_before_run():
    """TST-MEM-07: analyze and tick settle/reflect before starting new runs [REQ-MEM-07]"""
    for name in ("analyze", "tick"):
        body = skill(name)[1]
        assert body.index("berkshire settle") < body.index("berkshire init"), name
        assert "berkshire settle --apply" in body


def test_pipeline_loop_dispatch():
    """TST-FLOW-10: The shared loop dispatches due steps in parallel and submits each [REQ-FLOW-02, REQ-FLOW-08]"""
    body = (ROOT / "skills" / "analyze" / "pipeline-loop.md").read_text()
    assert "all in the same message" in body and "berkshire submit RUN <id>" in body
    assert "Never decide the order yourself" in body
    for name in ("analyze", "tick", "backtest"):
        assert "pipeline-loop.md" in skill(name)[1]


def test_pipeline_loop_honours_stop():
    """TST-UI-24: The pipeline loop stops dispatching when the run was stopped [REQ-UI-13]"""
    body = (ROOT / "skills" / "analyze" / "pipeline-loop.md").read_text()
    assert "`stopped` says the user stopped it" in body and "the run was stopped" in body


def test_analysts_honour_no_data_markers():
    """TST-ROLE-07: Every analyst treats NO_DATA_AVAILABLE / DATA_UNAVAILABLE output as missing data, not a finding [REQ-DATA-06, REQ-ROLE-05]"""
    for name in ("market-analyst", "fundamentals-analyst", "news-analyst", "sentiment-analyst"):
        body = agent(name)[1]
        assert "NO_DATA_AVAILABLE" in body and "DATA_UNAVAILABLE" in body, name
    for name in ("market-analyst", "fundamentals-analyst", "news-analyst"):
        assert "make no exact numeric claim" in agent(name)[1] and "Do not fill the gap from memory" in agent(name)[1]


def test_sentiment_bluesky_source():
    """TST-ROLE-08: The Sentiment Analyst queries Bluesky within the run's window, labels engagement as current, and an empty feed never lowers confidence [REQ-ROLE-03, REQ-DATA-07]"""
    body = agent("sentiment-analyst")[1]
    assert "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=%24<SYMBOL>" in body
    assert "since=<START>T00:00:00Z&until=<END>T23:59:59Z" in body and "7 days up to the analysis date" in body
    assert "cite them as current" in body and "never lowers confidence when it is empty" in body
    assert "four complementary sources" in body and "Mastodon" not in body and "Fear" not in body


def test_sentiment_screens_posts():
    """TST-ROLE-10: The Sentiment Analyst drops off-topic social posts and reports on-topic and stance counts per source [REQ-ROLE-03]"""
    body = agent("sentiment-analyst")[1]
    assert "drop posts that are not about this instrument" in body and "sharing the symbol" in body
    assert "including posts without a user tag" in body
    assert "`N of M posts on-topic: b bullish, r bearish, n neutral, u unclear`" in body
    assert "on the on-topic posts only" in body and "user-tag split separately" in body


def test_fundamentals_macro_branch():
    """TST-ROLE-11: For an index, commodity or currency pair, the Fundamentals Analyst researches macro drivers on the web instead of calling company tools [REQ-ROLE-03, REQ-FLOW-11]"""
    assert {"WebSearch", "WebFetch"} <= tools("fundamentals-analyst")
    body = agent("fundamentals-analyst")[1]
    assert "a stock index, a commodity or a currency pair" in body and "do not call the statement, insider, earnings" in body
    for driver in ("**Index:**", "**Commodity:**", "**Currency pair:**", "Commitments of Traders", "OPEC+", "real yields"):
        assert driver in body, driver
    assert "use only items published on or before that date" in body
    from berkshire import pipeline
    for mode in pipeline.MACRO_TYPES:     # the persona's trigger phrase matches the engine's context wording
        assert "Treat it as a " + {"index": "stock market index", "commodity": "commodity", "fx": "currency pair"}[mode] \
            in pipeline.MACRO_CONTEXT[mode]


def test_fundamentals_fund_branch():
    """TST-ROLE-09: For a fund, the Fundamentals Analyst uses etf_profile instead of company tools and never infers undisclosed concentration [REQ-ROLE-03, REQ-FLOW-10]"""
    body = agent("fundamentals-analyst")[1]
    assert "call `etf_profile` instead of the statement, insider and earnings tools" in body
    assert "instead of inferring concentration" in body and "daily-reset decay" in body and "`valuation` does not apply to a fund" in body
