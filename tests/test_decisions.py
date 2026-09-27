"""Structured output, field coercion and the rating parser."""

import pytest
from conftest import js

from berkshire import decisions as d


def test_schemas_render_tradingagents_markdown():
    """TST-OUT-01: Each schema validates its JSON and renders the TradingAgents headers [REQ-OUT-01]"""
    md, parsed, err = d.structured(
        js({"recommendation": "overweight", "rationale": "R", "strategic_actions": "S"}), "research_plan"
    )
    assert err is None and parsed["recommendation"] == "Overweight"
    assert md == "**Recommendation**: Overweight\n\n**Rationale**: R\n\n**Strategic Actions**: S"
    md, _, _ = d.structured(js({"action": "Sell", "reasoning": "R"}), "trader_proposal")
    assert "**Entry Price**: not provided" in md and md.endswith("FINAL TRANSACTION PROPOSAL: **SELL**")
    md, _, _ = d.structured(js({"rating": "Hold", "executive_summary": "E", "investment_thesis": "T"}), "pm_decision")
    assert md.startswith("**Rating**: Hold") and "**Price Target**: not provided" in md
    assert "**Time Horizon**: not provided" in md


def test_last_json_block_wins():
    """TST-OUT-02: With several JSON blocks the last one is used [REQ-OUT-01]"""
    text = js({"action": "Buy", "reasoning": "draft"}) + "\n" + js({"action": "Hold", "reasoning": "final"})
    assert d.structured(text, "trader_proposal")[1]["action"] == "Hold"


@pytest.mark.parametrize(
    "text",
    [
        "No JSON at all, Rating: Sell",
        "```json\n{not json}\n```\nRating: Sell",
        js({"rating": "Strong Buy", "executive_summary": "E", "investment_thesis": "T"}),
    ],
)
def test_fallback_to_free_text(text):
    """TST-OUT-03: Missing, malformed or invalid JSON falls back to free text with an error [REQ-OUT-02]"""
    md, parsed, err = d.structured(text, "pm_decision")
    assert parsed is None and err and md


@pytest.mark.parametrize(
    "raw,expected",
    [
        (189.5, 189.5),
        ("189.5", 189.5),
        ("$1,234.50", 1234.5),
        ("€99", 99.0),
        ("N/A", None),
        ("none", None),
        ("", None),
        ("15%", None),
        ("150-160", None),
        ("around 150", None),
        (None, None),
        (True, None),
    ],
)
def test_optional_float(raw, expected):
    """TST-OUT-04: Prices coerce; placeholders, percentages, ranges and hedges become null [REQ-OUT-03]"""
    assert d.optional_float(raw) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("**Rating**: Overweight\n\nThesis...", "Overweight"),
        ("Rating — **Sell**", "Sell"),
        ("Rating：Underweight", "Underweight"),  # fullwidth colon (NFKC)
        ("Rating Scale: Buy, Overweight, Hold\nRating: Hold", "Hold"),  # legend ignored
        ("**Rating**: Sell\n(Rating scale: Buy / Overweight / Hold)", "Sell"),  # trailing legend ignored
        ("Rating: Buy\n...on reflection...\nRating: Hold", None),  # two rating lines disagree: no call
        ("Buy was argued. Final rating — Underweight. Trim.", "Underweight"),  # label inside prose
        ("**Rating**: Hold\n\nStreet consensus rating: Buy (28 of 35).", "Hold"),  # quoted in a sentence
        ("**Rating**: Hold\n\nOperating margin: Sell-side estimates sit low.", "Hold"),  # not a word-start label
        ("Our rating: Hold\n- Rating: Buy (Goldman)\n| Rating: Buy | MS |\n> Rating: Buy", "Hold"),  # list, table, quote
        ("## Final Rating - Sell\n\nExit.", "Sell"),  # heading with one qualifier word
        ("We recommend a Sell here.", "Sell"),  # single bare word
        ("Buyers are holding back.", None),  # no word-boundary match
        ("Not a Buy; we conclude Underweight.", None),  # two ratings, no label
        ("", None),
    ],
)
def test_rating_parser(text, expected):
    """TST-OUT-05: Rating parser: the decision's own rating line, not a quoted one; legend skipped; bare word only if unique [REQ-OUT-04, REQ-OUT-05]"""
    assert d.extract_rating(text) == expected
    assert d.parse_rating(text) == (expected or "REVIEW")


@pytest.mark.parametrize(
    "payload",
    [
        {"overall_band": "Bullish", "overall_score": 11, "confidence": "high", "narrative": "n"},
        {"overall_band": "Euphoric", "overall_score": 8, "confidence": "high", "narrative": "n"},
        {"overall_band": "Bullish", "overall_score": 8, "confidence": "certain", "narrative": "n"},
        {"overall_band": "Bullish", "overall_score": "N/A", "confidence": "high", "narrative": "n"},
    ],
)
def test_sentiment_bounds(payload):
    """TST-OUT-06: Sentiment score bounded 0-10; band and confidence restricted [REQ-OUT-06]"""
    assert d.structured(js(payload), "sentiment")[1] is None
    ok = d.structured(js({**payload, "overall_band": "mixed", "overall_score": 5, "confidence": "LOW"}), "sentiment")
    assert ok[1] == {"overall_band": "Mixed", "overall_score": 5.0, "confidence": "low", "narrative": "n"}


@pytest.mark.parametrize(
    "action,entry,stop,target,expected",
    [
        ("Buy", 100.0, 90.0, 130.0, 3.0),
        ("Sell", 100.0, 110.0, 80.0, 2.0),
        ("Buy", 100.0, 110.0, 130.0, "levels inverted for a Buy"),  # stop above entry
        ("Buy", 100.0, 90.0, 95.0, "levels inverted for a Buy"),  # target below entry
        ("Sell", 100.0, 90.0, 80.0, "levels inverted for a Sell"),  # stop below entry
        ("Buy", 100.0, 100.0, 130.0, "levels inverted for a Buy"),  # zero risk is not infinite reward/risk
        ("Buy", 100.0, 90.0, None, "not provided"),
        ("Buy", None, 90.0, 130.0, "not provided"),  # a missing entry never reaches a comparison
        ("Sell", 100.0, None, 80.0, "not provided"),
        ("Hold", 100.0, 90.0, 130.0, "Hold: no position change"),
    ],
)
def test_risk_reward(action, entry, stop, target, expected):
    """TST-OUT-09: Risk/reward is computed only from correctly ordered levels; inverted or missing levels are named, never abs()-ed [REQ-OUT-07]"""
    rr, why = d.risk_reward(action, entry, stop, target)
    if isinstance(expected, float):
        assert rr == pytest.approx(expected) and why == ""
    else:
        assert rr is None and expected in why


def test_trader_render_with_target():
    """TST-OUT-10: TraderProposal accepts target_price like the other levels and renders the engine's R/R line [REQ-OUT-01, REQ-OUT-03, REQ-OUT-07]"""
    md, parsed, _ = d.structured(
        js({"action": "Buy", "reasoning": "R", "entry_price": "$100", "stop_loss": 90, "target_price": "130.0"}),
        "trader_proposal",
    )
    assert parsed["target_price"] == 130.0
    assert "**Target Price**: 130.0" in md and "**Risk/Reward**: 3.00 (computed from entry, stop and target)" in md
    assert md.endswith("FINAL TRANSACTION PROPOSAL: **BUY**")
    md, _, _ = d.structured(
        js({"action": "Buy", "reasoning": "R", "entry_price": 100, "stop_loss": 110, "target_price": "15%"}), "trader_proposal"
    )
    assert "**Target Price**: not provided" in md and "**Risk/Reward**: n/a (entry, stop or target not provided)" in md
