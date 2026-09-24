# Berkshire

A Claude Code plugin that runs a [TradingAgents](../TradingAgents)-style trading firm as
Claude subagents: an analyst team, a bull/bear research debate, a trader, a three-way risk
debate and a portfolio manager. It keeps a decision log that settles and reflects on past
calls, and puts a deterministic risk gate in front of **human-approved** order execution on
eToro through the eToro MCP.

> Research tooling, not financial advice. Every order needs your explicit approval, and the default account is **demo**.

## Commands

| Command | What it does | TradingAgents equivalent |
|---|---|---|
| `/berkshire:analyze [TICKER] [DATE] [--analysts …] [--depth shallow\|medium\|deep] [--language L] [--portfolio FILE\|etoro] [--checkpoint] [--clear-checkpoints]` | One multi-agent analysis. Interactive when run without arguments. Can queue an order at the end. | `tradingagents` CLI / `propagate()` |
| `/berkshire:tick` | One scheduled cycle over eToro holdings plus your watchlist: settle → analyse → risk gate → queue → notify | *(new)* |
| `/loop 24h /berkshire:tick` | Run the cycle once per day | *(new)* |
| `/berkshire:approve` | Review queued orders; `prepare-trade` / `place-trade` one approval at a time | *(new)* |
| `/berkshire:backtest TICKERS --start --end [--every N] [--run-id ID]` | Grid run in an isolated home, scored by rating | `tradingagents backtest` |

## How it works

```
/berkshire:analyze ──► berkshire init ──► loop: berkshire next ─► Agent(role) ×N ─► berkshire submit
                                                   ▲                                   │
                                                   └───────────── state.json ◄─────────┘
 roles (agents/*.md)                   engine (berkshire/, pytest-tested)
 market · sentiment · news · fundamentals   routing = TradingAgents conditional logic
 bull ⇄ bear → research manager (opus)      context grounding (identity, absent reports, openings)
 trader → aggressive → conservative → neutral  JSON schemas + REVIEW-safe rating parser
 portfolio manager (opus) · reflector      decision log + settlement, point-in-time data
                                            risk gate → approval queue → eToro MCP
```

* The **engine** (`berkshire` CLI, Python) owns everything that must be exact: routing,
  prompts/context, schema validation, the decision log, date clamping, sizing, and the queue.
* The **roles** are Claude subagents. The engine writes each role's context to a prompt file,
  and the agent writes its answer to an output file. The orchestrating skill only dispatches.
* **Data** comes from yfinance through `berkshire data --run RUN …`, clamped to the analysis date.
  Web search covers news, macro and social sources. eToro supplies live quotes, the portfolio and eligibility.

## Rating → order (risk gate, all limits in `~/.berkshire/config.json` or `BERKSHIRE_*`)

| Rating | Order |
|---|---|
| Buy / Overweight | Buy toward 100 % / 50 % of `target_weight` (5 %). Capped by `max_order_pct` 5 %, `max_instrument_pct` 15 %, and the `min_cash_pct` 10 % floor. Stop-loss = the Trader's stop, else ask − 2×ATR, else veto. Take-profit = the PM's price target. |
| Hold / REVIEW | No order (REVIEW is flagged for you) |
| Underweight / Sell | Close 50 % / 100 % of directly held positions |

Long only, leverage 1, at most 5 orders per tick. Queue items expire after 24 h.

## Install

```bash
# uv is required; the engine's environment is created on first use
claude --plugin-dir /Users/kai/repos/ai/berkshire          # dev
# or: /plugin marketplace add /Users/kai/repos/ai/berkshire ; /plugin install berkshire@berkshire-local
```

State lives in `~/.berkshire/`: `runs/<TICKER>/<DATE>/` (state, prompts, outputs, reports),
`memory/trading_memory.md` (same format as TradingAgents), `queue.json`, and `config.json`.

## Docs and tests

* [docs/tradingagents-analysis.md](docs/tradingagents-analysis.md): analysis of the source framework
* [docs/requirements.md](docs/requirements.md): 85 requirements (`REQ-*`) and the recorded design decisions
* [docs/test-plan.md](docs/test-plan.md): strategy, test cases (`TST-*`), manual procedures, and the REQ→TST matrix

```bash
uv run pytest      # offline, ~1 s; includes the traceability check
```
