"""Structured output, field coercion and the rating parser."""

import pytest

from berkshire import decisions as d
from conftest import js


def test_schemas_render_tradingagents_markdown():
    """TST-OUT-01: Each schema validates its JSON and renders the TradingAgents headers [REQ-OUT-01]"""
    md, parsed, err = d.structured(js({"recommendation": "overweight", "rationale": "R", "strategic_actions": "S"}),
                                   "research_plan")
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


@pytest.mark.parametrize("text", ["No JSON at all, Rating: Sell", "```json\n{not json}\n```\nRating: Sell",
                                  js({"rating": "Strong Buy", "executive_summary": "E", "investment_thesis": "T"})])
def test_fallback_to_free_text(text):
    """TST-OUT-03: Missing, malformed or invalid JSON falls back to free text with an error [REQ-OUT-02]"""
    md, parsed, err = d.structured(text, "pm_decision")
    assert parsed is None and err and md


@pytest.mark.parametrize("raw,expected", [
    (189.5, 189.5), ("189.5", 189.5), ("$1,234.50", 1234.5), ("€99", 99.0), ("N/A", None), ("none", None),
    ("", None), ("15%", None), ("150-160", None), ("around 150", None), (None, None), (True, None)])
def test_optional_float(raw, expected):
    """TST-OUT-04: Prices coerce; placeholders, percentages, ranges and hedges become null [REQ-OUT-03]"""
    assert d.optional_float(raw) == expected


@pytest.mark.parametrize("text,expected", [
    ("**Rating**: Overweight\n\nThesis...", "Overweight"),
    ("Rating — **Sell**", "Sell"),
    ("Rating：Underweight", "Underweight"),                       # fullwidth colon (NFKC)
    ("Rating Scale: Buy, Overweight, Hold\nRating: Hold", "Hold"),  # legend ignored
    ("**Rating**: Sell\n(Rating scale: Buy / Overweight / Hold)", "Sell"),  # trailing legend ignored
    ("Rating: Buy\n...on reflection...\nRating: Hold", "Hold"),     # last label wins
    ("We recommend a Sell here.", "Sell"),                        # single bare word
    ("Buyers are holding back.", None),                           # no word-boundary match
    ("Not a Buy; we conclude Underweight.", None),                # two ratings, no label
    ("", None)])
def test_rating_parser(text, expected):
    """TST-OUT-05: Rating parser: last label, legend skipped, bare word only if unique [REQ-OUT-04, REQ-OUT-05]"""
    assert d.extract_rating(text) == expected
    assert d.parse_rating(text) == (expected or "REVIEW")


@pytest.mark.parametrize("payload", [
    {"overall_band": "Bullish", "overall_score": 11, "confidence": "high", "narrative": "n"},
    {"overall_band": "Euphoric", "overall_score": 8, "confidence": "high", "narrative": "n"},
    {"overall_band": "Bullish", "overall_score": 8, "confidence": "certain", "narrative": "n"},
    {"overall_band": "Bullish", "overall_score": "N/A", "confidence": "high", "narrative": "n"}])
def test_sentiment_bounds(payload):
    """TST-OUT-06: Sentiment score bounded 0-10; band and confidence restricted [REQ-OUT-06]"""
    assert d.structured(js(payload), "sentiment")[1] is None
    ok = d.structured(js({**payload, "overall_band": "mixed", "overall_score": 5, "confidence": "LOW"}), "sentiment")
    assert ok[1] == {"overall_band": "Mixed", "overall_score": 5.0, "confidence": "low", "narrative": "n"}
