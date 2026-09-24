"""Shared fixtures: an isolated BERKSHIRE_HOME, a pinned 'today', an offline
yfinance fake, and a canned-agent driver that runs a whole pipeline without LLMs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from berkshire import backtest, config, data, pipeline
from berkshire.memory import DecisionLog

TODAY = "2026-09-24"


def bars(end="2026-09-18", n=400, start_price=100.0, step=0.5):
    idx = pd.bdate_range(end=end, periods=n)
    close = pd.Series([start_price + i * step for i in range(n)], index=idx)
    return pd.DataFrame({"Open": close - 0.5, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": 1_000_000.0}, index=idx)


class FakeTicker:
    """Minimal stand-in for yfinance.Ticker."""

    frames: dict = {}
    info_by_symbol: dict = {}
    news_items: list = []

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, start, end, auto_adjust=False):
        df = self.frames.get(self.symbol, bars())
        return df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))]

    @property
    def info(self):
        return self.info_by_symbol.get(self.symbol, {"longName": f"{self.symbol} Corp", "sector": "Technology",
                                                     "industry": "Semiconductors", "exchange": "NMS",
                                                     "trailingPE": 30.5})

    @property
    def news(self):
        return self.news_items

    @property
    def quarterly_income_stmt(self):
        cols = [pd.Timestamp(d) for d in ("2026-07-31", "2026-04-30", "2026-01-31")]
        return pd.DataFrame([[3.0, 2.0, 1.0]], index=["Net Income"], columns=cols)

    quarterly_balance_sheet = quarterly_cashflow = quarterly_income_stmt
    income_stmt = balance_sheet = cashflow = quarterly_income_stmt

    @property
    def insider_transactions(self):
        return pd.DataFrame({"Insider": ["A", "B"], "Start Date": ["2026-09-01", "2026-09-20"]})


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BERKSHIRE_HOME", str(tmp_path / "home"))
    for var in list(__import__("os").environ):
        if var.startswith("BERKSHIRE_") and var != "BERKSHIRE_HOME":
            monkeypatch.delenv(var)
    monkeypatch.setattr(data, "today", lambda: TODAY)
    monkeypatch.setattr(backtest, "today", lambda: TODAY)
    FakeTicker.frames, FakeTicker.info_by_symbol, FakeTicker.news_items = {}, {}, []
    monkeypatch.setattr(data, "_ticker", FakeTicker)
    return tmp_path


@pytest.fixture
def cfg():
    return config.load()


@pytest.fixture
def log(tmp_path):
    return DecisionLog(tmp_path / "home" / "memory" / "trading_memory.md")


def new_run(cfg, log, ticker="NVDA", date="2026-09-18", **kw):
    res = pipeline.init_run(ticker, date, cfg, results_dir=config.home() / "runs", memory_log=log,
                            identity=kw.pop("identity", {"company_name": "NVIDIA Corporation"}), **kw)
    return pipeline.load_state(Path(res["run_dir"]))


def js(obj) -> str:
    return "Reasoning in prose.\n\n```json\n" + json.dumps(obj) + "\n```"


CANNED = {
    "analyst_market": "Market report: price 299.5, support 290, ATR 2.0.",
    "analyst_social": js({"overall_band": "Mildly Bullish", "overall_score": 6.0, "confidence": "medium",
                          "narrative": "StockTwits 70/30 bullish."}),
    "analyst_news": "News report: export rules eased.",
    "analyst_fundamentals": "Fundamentals report: margins expanding.",
    "bull": "Growth is strong.",
    "bear": "Valuation is stretched.",
    "research_manager": js({"recommendation": "Overweight", "rationale": "Bull case stronger.",
                            "strategic_actions": "Add gradually."}),
    "trader": js({"action": "Buy", "reasoning": "Trend intact.", "entry_price": 299.5,
                  "stop_loss": "$290.00", "position_sizing": "5% of portfolio"}),
    "aggressive": "Go bigger.", "conservative": "Protect capital.", "neutral": "Balance it.",
    "portfolio_manager": "**Rating**: Buy\n\n" + js({"rating": "Buy", "executive_summary": "Buy on dips.",
                                                    "investment_thesis": "Earnings momentum.",
                                                    "price_target": 340, "time_horizon": "3-6 months"}),
}


def canned(step_id: str) -> str:
    return CANNED.get(step_id) or CANNED[step_id.split("_")[0]]


def run_all(state, log, outputs=canned, trace=None):
    """Drive a run to completion, returning the final state; `trace` collects step batches."""
    while True:
        steps = pipeline.write_prompts(state)
        if not steps:
            return state
        if trace is not None:
            trace.append([s["id"] for s in steps])
        for s in steps:
            state = pipeline.submit(state, s["id"], outputs(s["id"]), log)
