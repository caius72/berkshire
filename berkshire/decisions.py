"""Ratings, structured-output schemas and their markdown renderers.

Ports TradingAgents' rating.py + schemas.py + structured.py. Agents emit a
fenced ```json block; `structured()` validates and renders it, and falls back
to the free text when the block is missing or invalid (REQ-OUT-01/02).
"""

from __future__ import annotations

import json
import re
import unicodedata

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
TRADER_ACTIONS = ("Buy", "Hold", "Sell")
SENTIMENT_BANDS = ("Bullish", "Mildly Bullish", "Neutral", "Mixed", "Mildly Bearish", "Bearish")
REVIEW = "REVIEW"

# --- rating parser (REQ-OUT-04/05) -----------------------------------------

# "rating" must start a word, so "Operating margin: Sell-side" is not a label (TradingAgents #1383).
_LABEL_RE = re.compile(r"(?<![a-z])rating\b[^:\-‐-―]*[:\-‐-―][\s*]*(\w+)", re.IGNORECASE)
# The label opening its own line ("**Rating**: X", "## Final Rating - X", "Our rating: X"): the shape a
# decision states its call in. Only emphasis or heading marks and one word may precede it, so a list item,
# table row, quote or sentence citing someone else's rating is not one.
_LINE_RE = re.compile(r"[\s*_#]*(?:\w+\s+)?rating[^\w:\-‐-―]*[:\-‐-―][\s*]*(\w+)", re.IGNORECASE)
_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)
_WORD_RE = re.compile(r"\b(" + "|".join(RATINGS) + r")\b", re.IGNORECASE)
_RATING_SET = {r.lower() for r in RATINGS}


def extract_rating(text: str) -> str | None:
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)
    own_lines, labelled = set(), None
    for line in norm.splitlines():
        if _SCALE_RE.search(line):
            continue
        m = _LINE_RE.match(line)
        if m and m.group(1).lower() in _RATING_SET:
            own_lines.add(m.group(1).capitalize())
        m = _LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            labelled = m.group(1).capitalize()
    # A rating line is the call; two that disagree are no call (REVIEW), since a wrong direction is
    # worse than none. Without one, the last label anywhere: prose states its rating after the alternatives.
    if own_lines:
        return own_lines.pop() if len(own_lines) == 1 else None
    if labelled:
        return labelled
    named = {m.group(1).capitalize() for m in _WORD_RE.finditer(norm)}
    return named.pop() if len(named) == 1 else None


def parse_rating(text: str) -> str:
    return extract_rating(text) or REVIEW


# --- field coercion (REQ-OUT-03) -------------------------------------------

_NULLISH = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown", "not provided"}


def optional_float(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in _NULLISH or text.endswith("%"):
        return None
    try:
        return float(text.replace(",", "").lstrip("$€£¥").strip())
    except ValueError:
        return None


def _enum(value, allowed, field):
    for a in allowed:
        if str(value).strip().lower() == a.lower():
            return a
    raise ValueError(f"{field} must be one of {allowed}, got {value!r}")


def _text(data, field, required=True):
    v = data.get(field)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise ValueError(f"{field} is required")
        return None
    return str(v).strip()


# --- schemas: validate(dict) -> dict, render(dict) -> markdown --------------


def validate_research_plan(d: dict) -> dict:
    return {
        "recommendation": _enum(d.get("recommendation"), RATINGS, "recommendation"),
        "rationale": _text(d, "rationale"),
        "strategic_actions": _text(d, "strategic_actions"),
    }


def render_research_plan(p: dict) -> str:
    return (
        f"**Recommendation**: {p['recommendation']}\n\n**Rationale**: {p['rationale']}\n\n"
        f"**Strategic Actions**: {p['strategic_actions']}"
    )


def validate_trader_proposal(d: dict) -> dict:
    return {
        "action": _enum(d.get("action"), TRADER_ACTIONS, "action"),
        "reasoning": _text(d, "reasoning"),
        "entry_price": optional_float(d.get("entry_price")),
        "stop_loss": optional_float(d.get("stop_loss")),
        "target_price": optional_float(d.get("target_price")),
        "position_sizing": _text(d, "position_sizing", required=False),
    }


def risk_reward(action: str, entry, stop, target) -> tuple[float | None, str]:
    """Reward/risk from the proposal's own levels, or None with the reason (REQ-OUT-07).

    Direction-checked, never abs(): a Buy needs stop < entry < target and a Sell needs
    target < entry < stop. Inverted levels mean the proposal contradicts itself, which the
    ratio must expose rather than hide (TradingAgents #1082 adapted).
    """
    if action == "Hold":
        return None, "n/a (Hold: no position change)"
    if None in (entry, stop, target):
        return None, "n/a (entry, stop or target not provided)"
    if action == "Buy" and stop < entry < target:
        return (target - entry) / (entry - stop), ""
    if action == "Sell" and target < entry < stop:
        return (entry - target) / (stop - entry), ""
    return None, f"n/a (levels inverted for a {action}: entry {entry}, stop {stop}, target {target})"


def render_trader_proposal(p: dict) -> str:
    parts = [f"**Action**: {p['action']}", "", f"**Reasoning**: {p['reasoning']}"]
    for label, key in (
        ("Entry Price", "entry_price"),
        ("Stop Loss", "stop_loss"),
        ("Target Price", "target_price"),
        ("Position Sizing", "position_sizing"),
    ):
        v = p.get(key)
        parts += ["", f"**{label}**: {v if v not in (None, '') else 'not provided'}"]
    rr, why = risk_reward(p["action"], p.get("entry_price"), p.get("stop_loss"), p.get("target_price"))
    parts += ["", f"**Risk/Reward**: {f'{rr:.2f} (computed from entry, stop and target)' if rr is not None else why}"]
    parts += ["", f"FINAL TRANSACTION PROPOSAL: **{p['action'].upper()}**"]
    return "\n".join(parts)


def validate_pm_decision(d: dict) -> dict:
    return {
        "rating": _enum(d.get("rating"), RATINGS, "rating"),
        "executive_summary": _text(d, "executive_summary"),
        "investment_thesis": _text(d, "investment_thesis"),
        "price_target": optional_float(d.get("price_target")),
        "time_horizon": _text(d, "time_horizon", required=False),
    }


def render_pm_decision(p: dict) -> str:
    target = p["price_target"] if p.get("price_target") is not None else "not provided"
    return (
        f"**Rating**: {p['rating']}\n\n**Executive Summary**: {p['executive_summary']}\n\n"
        f"**Investment Thesis**: {p['investment_thesis']}\n\n**Price Target**: {target}\n\n"
        f"**Time Horizon**: {p.get('time_horizon') or 'not provided'}"
    )


def validate_sentiment(d: dict) -> dict:
    score = optional_float(d.get("overall_score"))
    if score is None or not 0 <= score <= 10:
        raise ValueError(f"overall_score must be a number in 0..10, got {d.get('overall_score')!r}")
    return {
        "overall_band": _enum(d.get("overall_band"), SENTIMENT_BANDS, "overall_band"),
        "overall_score": score,
        "confidence": _enum(d.get("confidence"), ("low", "medium", "high"), "confidence"),
        "narrative": _text(d, "narrative"),
    }


def render_sentiment(r: dict) -> str:
    return (
        f"**Overall Sentiment:** **{r['overall_band']}** (Score: {r['overall_score']:.1f}/10)\n"
        f"**Confidence:** {r['confidence'].capitalize()}\n\n{r['narrative']}"
    )


SCHEMAS = {
    "research_plan": (validate_research_plan, render_research_plan),
    "trader_proposal": (validate_trader_proposal, render_trader_proposal),
    "pm_decision": (validate_pm_decision, render_pm_decision),
    "sentiment": (validate_sentiment, render_sentiment),
}

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def structured(text: str, schema: str) -> tuple[str, dict | None, str | None]:
    """Return (markdown, parsed_or_None, error_or_None).

    Uses the last ```json block. On any failure the free text (minus a broken
    block) is the output, so the pipeline never blocks on a malformed answer.
    """
    validate, render = SCHEMAS[schema]
    blocks = _JSON_BLOCK.findall(text or "")
    if blocks:
        try:
            parsed = validate(json.loads(blocks[-1]))
            return render(parsed), parsed, None
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            error = f"invalid {schema} JSON: {exc}"
    else:
        error = f"no {schema} JSON block"
    fallback = _JSON_BLOCK.sub("", text or "").strip() or (text or "").strip()
    return fallback, None, error
