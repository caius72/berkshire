# TradingAgents v0.5.1 — analysis

Source analysed: `../TradingAgents` at commit `35543d0` (v0.5.1, ~11.6k lines of Python,
LangGraph). This document records what Berkshire has to reproduce and why.

## 1. Shape of the system

TradingAgents mirrors a trading firm as a fixed LangGraph `StateGraph` over one
`AgentState`. One run analyses one instrument on one date:

```
START
  └─ Analyst team (selected subset, in order market → social → news → fundamentals)
       each: agent ⇄ tool node until no tool calls, then "Msg Clear" (message reset)
  └─ Investment debate: Bull ⇄ Bear   (2 × max_debate_rounds turns, Bull opens)
  └─ Research Manager  (deep model, structured ResearchPlan)
  └─ Trader            (quick model, structured TraderProposal)
  └─ Risk debate: Aggressive → Conservative → Neutral (3 × max_risk_discuss_rounds turns)
  └─ Portfolio Manager (deep model, structured PortfolioDecision)
END → signal = 5-tier rating (or REVIEW)
```

| Team | Role | Model | Input | Output (state key) |
|---|---|---|---|---|
| Analysts | Market (technical) | quick | OHLCV, indicators, verified snapshot tools | `market_report` |
| | Sentiment ("social") | quick | pre-fetched news + StockTwits + Reddit (no tools) | `sentiment_report` (structured SentimentReport) |
| | News | quick | ticker news, global news, FRED macro, Polymarket | `news_report` |
| | Fundamentals | quick | fundamentals, balance sheet, cash flow, income stmt, insider tx | `fundamentals_report` |
| Research | Bull researcher | quick | 4 reports + debate history + last bear argument | `investment_debate_state` |
| | Bear researcher | quick | 4 reports + debate history + last bull argument | `investment_debate_state` |
| | Research Manager (judge) | deep | debate history | `investment_plan` (ResearchPlan) |
| Trading | Trader | quick | plan + market report + portfolio | `trader_investment_plan` (TraderProposal) |
| Risk | Aggressive / Conservative / Neutral | quick | trader plan + 4 reports + portfolio + other two's last args | `risk_debate_state` |
| Portfolio | Portfolio Manager (judge) | deep | plan, trader proposal, risk history, past lessons, portfolio | `final_trade_decision` (PortfolioDecision) |
| Memory | Reflector | quick | settled decision + raw/alpha return | reflection text in decision log |

Two model tiers: `deep_think_llm` for the two judges, `quick_think_llm` for everyone else.

## 2. Routing (conditional_logic.py)

* Investment debate: ends when `count >= 2 × max_debate_rounds`, otherwise the speaker
  alternates on the prefix of `current_response` ("Bull…" → Bear, else Bull).
* Risk debate: ends when `count >= 3 × max_risk_discuss_rounds`, otherwise
  Aggressive → Conservative → Neutral → Aggressive, keyed on `latest_speaker`.
* Every router target appears in the path map, so an unexpected label cannot crash the run (#1088).
* CLI "research depth" sets both round counts: Shallow = 1, Medium = 3, Deep = 5.

## 3. The "intelligence": what keeps the output honest

The prompts are ordinary. Most of the quality comes from guard rails added one issue at a time:

1. **Instrument identity grounding (#814).** Company name, sector, industry and exchange
   are resolved once per run from the vendor and injected into every prompt. The
   prompt says: "use this exact ticker…, do not substitute a different company". For
   a historical date it adds a caveat that the profile describes the company as it is today.
2. **Point-in-time integrity.** Each dated tool clamps the requested date to the run's
   `trade_date` (`as_of`, `as_of_window`), so a model cannot ask for future data.
   Fundamentals are served as filed, news and social feeds are trimmed to the window,
   and decision-log lessons are filtered to those resolved by the trade date (#1251).
3. **Verified market snapshot (#830).** A deterministic table (latest OHLCV row,
   indicators, last 30 closes) that the market analyst must fetch before making any
   exact numeric claim, and must treat as the source of truth.
4. **Absence is not a finding (#1176).** A missing report becomes "(No X report in this
   run: it is not available, not an empty finding.)". An opponent who has not spoken
   yet becomes "(The bear analyst has not spoken yet — open the debate with your own case.)".
5. **Anti-Hold bias.** Both judges are told: "conflict alone is not a reason to Hold;
   commit to the stronger side, sized by how decisively it wins; weigh on merits,
   independent of speaking order".
6. **Structured output with a graceful fallback.** The Research Manager, Trader, Portfolio
   Manager and Sentiment Analyst use typed schemas. If parsing fails the agent falls back
   to free text and a heuristic rating parser. Numeric fields accept `"N/A"`, `"$1,234"`
   and similar, while percentages and ranges are nulled rather than failing the whole decision (#1058, #1288).
7. **REVIEW sentinel (#1170).** A decision with no parseable rating is `REVIEW`. It is
   never silently turned into Hold. The parser takes the last labelled `Rating: X`, skips
   scale legends, and accepts a bare rating word only when exactly one distinct rating appears.
8. **Trader price grounding (#1167).** The Trader sees the technical report so its
   entry and stop are real levels. Stops must be absolute prices, never percentages.
9. **Portfolio awareness.** The run can carry cash and positions. "Not provided" is kept
   distinct from "flat book" and is never treated as flat.
10. **No external tools for the judges** (`NO_EXTERNAL_TOOLS`). They decide only on the evidence in the prompt.
11. **Output language.** Reports can be localised, while the internal debate stays in English.

## 4. Memory and learning loop (decision_log.py, settlement.py, reflection.py)

* An append-only markdown log (`~/.tradingagents/memory/trading_memory.md`) holds entries tagged
  `[date | ticker | rating | pending]`, separated by `<!-- ENTRY_END -->`.
* Idempotent: a second entry for the same ticker and date is refused.
* **Settlement** at the start of the next run for the same ticker: once `holding_period_days`
  (5) trading days have traded, it computes the raw return and alpha against a regional
  benchmark (suffix map: `.T` → ^N225, `.L` → ^FTSE, default SPY), asks the Reflector for
  2–4 sentences, and rewrites the tag to
  `[date | ticker | rating | +x% | +y% | 5d | resolved:YYYY-MM-DD]` with an atomic write.
* **Past context** for the Portfolio Manager: up to 5 same-ticker entries (decision and reflection)
  plus 3 cross-ticker reflections, point-in-time filtered.
* Optional rotation of the oldest resolved entries (`memory_log_max_entries`). Pending entries are never pruned.

## 5. Interfaces

* **Interactive CLI** (`tradingagents`). Eight steps: ticker, date, output language, analysts,
  research depth, LLM provider, models, provider thinking knobs. The previous answers are
  offered as defaults, and `TRADINGAGENTS_*` env vars skip steps. A live Rich panel shows
  per-agent status, messages and tool calls, and the current report. Flags: `--checkpoint`,
  `--clear-checkpoints`, `--portfolio FILE`.
* **`tradingagents backtest TICKERS --start --end --every --analysts --asset-type --portfolio --run-id`**
  runs over a grid, keeps its own decision log, resumes by skipping finished cells, and
  summarises hit rate and mean alpha per rating.
* **Python API**: `TradingAgentsGraph(selected_analysts, debug, config).propagate(ticker, date,
  asset_type, portfolio) -> (final_state, signal)`, plus `save_reports()`.
* **Outputs**: the report tree `1_analysts/ 2_research/ 3_trading/ 4_risk/ 5_portfolio/
  complete_report.md`, `full_states_log_<date>.json`, and the decision log.
* **Checkpoint resume**: a per-ticker SQLite saver keyed by ticker, date and graph signature
  (analysts, rounds, asset type, portfolio fingerprint), cleared on success.
* **Config**: `DEFAULT_CONFIG` plus `TRADINGAGENTS_*` env overrides with type coercion that
  fails loudly on bad input.

## 6. What TradingAgents deliberately does *not* do

It never places orders. The README's "simulated exchange" is not implemented, and
`backtest.py` says explicitly that it is not a portfolio simulator. Execution, sizing
to an account, risk limits and scheduling are the parts Berkshire adds.

## 7. Mapping to Berkshire

| TradingAgents | Berkshire |
|---|---|
| LangGraph nodes (LLM) | Claude Code subagents `agents/*.md` (role persona) |
| LangGraph edges and conditional logic | `berkshire.pipeline.next_steps()` (deterministic, tested) |
| `AgentState` | `state.json` in the run directory |
| SqliteSaver checkpoint | The run directory itself: each completed step is persisted before the next starts |
| Provider-native structured output | A fenced JSON block validated by `berkshire.decisions` with a free-text fallback |
| LangChain tools + yfinance/AV/FRED/Polymarket | `berkshire data …` (yfinance, date-clamped) plus WebSearch/WebFetch |
| Rich live CLI | `/berkshire:analyze` skill with `berkshire status` progress tables |
| `propagate()` return `(state, signal)` | `berkshire submit` of the final step prints `{signal, report}`; `state.json` is the final state |
| (none) | Risk gate, rating→order map, approval queue, eToro MCP execution, `/loop` tick |
