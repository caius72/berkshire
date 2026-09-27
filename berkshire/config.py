"""Configuration: defaults < ~/.berkshire/config.json < BERKSHIRE_* env < CLI flags (REQ-IF-05)."""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

DEFAULTS: dict = {
    # Models (REQ-ROLE-02): Agent-tool aliases.
    "deep_think_llm": "opus",
    "quick_think_llm": "sonnet",
    "output_language": "English",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "checkpoint_enabled": False,
    "memory_log_max_entries": None,
    "holding_period_days": 5,
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS": "^NSEI",
        ".BO": "^BSESN",
        ".T": "^N225",
        ".HK": "^HSI",
        ".L": "^FTSE",
        ".TO": "^GSPTSE",
        ".AX": "^AXJO",
        ".SS": "000001.SS",
        ".SZ": "399001.SZ",
        ".SA": "^BVSP",
        ".DE": "^GDAXI",
        ".PA": "^FCHI",
        ".AS": "^AEX",
        # TradingAgents #1392, plus the other European venues eToro lists (Yahoo symbols checked 2026-09-27)
        ".TW": "^TWII",
        ".TWO": "^TWII",
        ".KS": "^KS11",
        ".KQ": "^KQ11",
        ".SI": "^STI",
        ".SW": "^SSMI",
        ".MI": "FTSEMIB.MI",
        ".MC": "^IBEX",
        ".ST": "^OMX",
        ".OL": "OSEBX.OL",
        ".CO": "^OMXC25",
        ".HE": "^OMXH25",
        ".BR": "^BFX",
        ".LS": "PSI20.LS",
        "": "SPY",
    },
    "news_article_limit": 20,
    "global_news_article_limit": 10,
    "global_news_lookback_days": 7,
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # Execution (REQ-EXE-03)
    "account": "demo",
    "watchlist_name": "My Watchlist",
    "max_tickers_per_tick": 10,
    "queue_ttl_hours": 24,
    "job_timeout_minutes": 180,  # a dashboard job still running after this is ended (REQ-UI-14)
    # Risk gate (REQ-RISK-08)
    "target_weight": 0.05,
    "max_order_pct": 0.05,
    "max_instrument_pct": 0.15,
    "min_cash_pct": 0.10,
    "max_orders_per_run": 5,
    "min_order_amount": 50.0,
    "atr_stop_multiple": 2.0,
    "underweight_close_fraction": 0.5,
    # eToro symbol -> yfinance symbol for non-equity assets (REQ-EXE-07)
    "symbol_map": {
        "GOLD": "GC=F",
        "SILVER": "SI=F",
        "PLATINUM": "PL=F",
        "OIL": "CL=F",
        "EUROOIL": "BZ=F",
        "NATGAS": "NG=F",
        "COPPER": "HG=F",
        "SPX500": "^GSPC",
        "NSDQ100": "^NDX",
        "DJ30": "^DJI",
        "GER40": "^GDAXI",
        "UK100": "^FTSE",
        "JPN225": "^N225",
    },
}

# env var -> key; type comes from the default (REQ-IF-05)
_ENV = {
    "BERKSHIRE_DEEP_THINK_LLM": "deep_think_llm",
    "BERKSHIRE_QUICK_THINK_LLM": "quick_think_llm",
    "BERKSHIRE_OUTPUT_LANGUAGE": "output_language",
    "BERKSHIRE_MAX_DEBATE_ROUNDS": "max_debate_rounds",
    "BERKSHIRE_MAX_RISK_ROUNDS": "max_risk_discuss_rounds",
    "BERKSHIRE_CHECKPOINT_ENABLED": "checkpoint_enabled",
    "BERKSHIRE_BENCHMARK_TICKER": "benchmark_ticker",
    "BERKSHIRE_HOLDING_PERIOD_DAYS": "holding_period_days",
    "BERKSHIRE_ACCOUNT": "account",
    "BERKSHIRE_WATCHLIST_NAME": "watchlist_name",
    "BERKSHIRE_TARGET_WEIGHT": "target_weight",
    "BERKSHIRE_MAX_ORDER_PCT": "max_order_pct",
    "BERKSHIRE_MAX_INSTRUMENT_PCT": "max_instrument_pct",
    "BERKSHIRE_MIN_CASH_PCT": "min_cash_pct",
    "BERKSHIRE_MAX_ORDERS_PER_RUN": "max_orders_per_run",
    "BERKSHIRE_MIN_ORDER_AMOUNT": "min_order_amount",
    "BERKSHIRE_ATR_STOP_MULTIPLE": "atr_stop_multiple",
}

_TRUE, _FALSE = ("true", "1", "yes", "on"), ("false", "0", "no", "off")
_FRACTIONS = ("target_weight", "max_order_pct", "max_instrument_pct", "underweight_close_fraction")


def home() -> Path:
    return Path(os.environ.get("BERKSHIRE_HOME") or Path.home() / ".berkshire").expanduser()


def _coerce(value: str, reference):
    if isinstance(reference, bool):
        v = value.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
        raise ValueError(f"expected a boolean, got {value!r}")
    if isinstance(reference, int):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def validate(cfg: dict) -> dict:
    """Reject limits that would make the risk gate meaningless (REQ-RISK-08)."""
    for key in _FRACTIONS:
        if not 0 < float(cfg[key]) <= 1:
            raise ValueError(f"{key} must be in (0, 1], got {cfg[key]!r}")
    if not 0 <= float(cfg["min_cash_pct"]) < 1:
        raise ValueError(f"min_cash_pct must be in [0, 1), got {cfg['min_cash_pct']!r}")
    for key in (
        "max_orders_per_run",
        "min_order_amount",
        "atr_stop_multiple",
        "holding_period_days",
        "max_tickers_per_tick",
        "queue_ttl_hours",
        "job_timeout_minutes",
    ):
        if float(cfg[key]) <= 0:
            raise ValueError(f"{key} must be positive, got {cfg[key]!r}")
    for key in ("max_debate_rounds", "max_risk_discuss_rounds"):
        if int(cfg[key]) < 1:
            raise ValueError(f"{key} must be at least 1, got {cfg[key]!r}")
    if cfg["account"] not in ("demo", "real"):
        raise ValueError(f"account must be 'demo' or 'real', got {cfg['account']!r}")
    return cfg


def load(overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    path = home() / "config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    for env, key in _ENV.items():
        raw = os.environ.get(env)
        if raw:
            try:
                cfg[key] = _coerce(raw, DEFAULTS[key]) if DEFAULTS[key] is not None else raw
            except ValueError as exc:
                raise ValueError(f"Invalid value for {env}: {exc}") from exc
    cfg.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return validate(cfg)


# --- paths (REQ-SAFE-01) ---------------------------------------------------

_SAFE = re.compile(r"^[A-Za-z0-9^=][A-Za-z0-9._^=-]{0,31}$")


def safe_component(value: str) -> str:
    """A ticker / run id usable as one path segment; rejects traversal."""
    v = str(value).strip()
    if not _SAFE.match(v) or ".." in v:
        raise ValueError(f"unsafe name for a path component: {value!r}")
    return v


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a crash never leaves a torn file (REQ-SAFE-02)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
