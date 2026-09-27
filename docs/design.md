# Berkshire: design

How Berkshire is built. [requirements.md](requirements.md) says *what* it must do, decisions D1–D12 say *why*
the big choices were made, and this document says *where* each part lives and how the parts meet. For how
TradingAgents works and how its code maps here, see [tradingagents-analysis.md](tradingagents-analysis.md) §7.

## Shape

```
skills (orchestration, in Claude Code)          engine (berkshire/, Python, pytest-tested)
  /berkshire:analyze ─┐                            cli.py ── the only surface the skills call
  /berkshire:tick   ──┼── berkshire <cmd> ──────►  pipeline.py · decisions.py · memory.py
  /berkshire:backtest ┘         ▲                  data.py · orders.py · etoro.py · backtest.py
  /berkshire:approve ── eToro MCP (per-order approval)        config.py
          │                     │
          ▼                     │ prompt file / output file
  Agent(role) ── agents/*.md ───┘                  server.py ◄── client.py ◄── tui.py
     13 subagents                                        ▲
                                                         └── webui/ (React, a client of the API)
```

Three rules hold the design together:

1. **The engine decides, the agents write.** Routing, context, schema validation, rating, memory, sizing
   and the queue are deterministic Python. Agents only turn a prompt file into prose plus a JSON block.
2. **Agents never see what the engine hides.** Every dated data tool clamps to the run's trade date, and
   every prompt is assembled by the engine, so point-in-time rules cannot be skipped by a persona.
3. **Orders need a person.** Nothing in the engine, the tick or the views places an order. The risk gate
   only shrinks or vetoes, and `/berkshire:approve` asks for approval once per order (D2, D12).

## Engine modules

| Module | Responsibility | Requirements |
|---|---|---|
| `cli.py` | The `berkshire` command: `init`, `next`, `submit`, `status`, `stop`, `data`, `settle`, `gate`, `enqueue`, `queue`, `etoro-portfolio`, `universe`, `backtest`, `prefs`, `config`, `serve`, `web`, `tui`. Prints JSON for the skills; turns any data-tool exception into a `DATA_UNAVAILABLE` line. | REQ-IF, REQ-DATA-06 |
| `pipeline.py` | Run state and the graph: `init_run` (signature, checkpoint, lessons fixed at init), `next_steps` (TradingAgents routing), `build_prompt` (identity, portfolio, horizon, language, past lessons, absent-report markers), `submit` (fold output into state, structured schemas, signal from the typed rating), `finalize` (report tree, states log with `run_settings`, decision log entry), `stop_run`, progress rows. | REQ-FLOW, REQ-CTX, REQ-CKPT, REQ-RPT, REQ-OUT-04 |
| `decisions.py` | Five-tier ratings, the free-text rating parser (REVIEW when unclear), the JSON schemas for research plan, trader proposal, PM decision and sentiment, and their markdown renderers. | REQ-OUT |
| `memory.py` | The decision log in TradingAgents' file format, settlement (raw return and alpha against the regional benchmark over `holding_period_days`), reflection prompts, and point-in-time past context. | REQ-MEM |
| `data.py` | yfinance tools behind `berkshire data --run RUN`: OHLCV, indicators, verified snapshot, fundamentals (as filed), valuation, earnings, ETF profile, statements, insider rows, news (Yahoo + Google News RSS). Date clamping, `NO_DATA_AVAILABLE`/`DATA_UNAVAILABLE` markers, the per-run price cache with rate-limit backoff. | REQ-DATA |
| `orders.py` | The risk gate (rating → intent, capped by target gap, order and instrument caps, cash floor; stop from the Trader or ATR) and the approval queue with its state machine (`pending → approved → placed/failed/…`, supersede, expiry). | REQ-RISK, REQ-EXE-04 |
| `etoro.py` | Offline adapters over saved eToro MCP responses: the portfolio book, eToro → Yahoo symbols (incl. `.ZU`/`.NV`/`.RTH`), asset modes, the tick universe. | REQ-CTX-04, REQ-EXE-06/07, REQ-SCHED |
| `backtest.py` | Date grid, plan (skip cells already logged), and per-rating scoring with the look-ahead caveat. Cells run the normal pipeline under an isolated home. | REQ-BT |
| `config.py` | Defaults < `config.json` < `BERKSHIRE_*` < flags, validation of risk limits, `atomic_write`, `safe_component` for paths. | REQ-IF-05, REQ-SAFE-01/02 |
| `server.py` | Local HTTP + SSE API over the home: runs, decision log, queue, backtests, jobs. Starts headless `claude -p` analyses with an explicit tool boundary and a time limit; stops runs. Loopback only, token-guarded. | REQ-UI |
| `client.py` | API client: discovery via `server.json`, auto-start, JSON and SSE. | REQ-UI-01 |
| `tui.py` | Textual terminal view, a client of the API (optional `tui` extra). | REQ-UI-08 |

`webui/` is the React view, another API client. It holds no trading logic (REQ-UI-01).

## One analysis

1. `berkshire init TICKER DATE …` resolves the instrument, computes the run signature (analysts, depth, rounds,
   horizon), and creates or resumes `runs/<TICKER>/<DATE>/state.json`. Past lessons are fixed here, filtered to
   those resolved by the trade date.
2. Loop (`skills/analyze/pipeline-loop.md`): `berkshire next RUN` writes the due steps' prompts to
   `prompts/<step>.md` and returns their agent and model. The skill launches one subagent per step with
   *prompt file → output file*; the agent writes `outputs/<step>.md` and replies `DONE`. `berkshire submit RUN
   <step>` folds the output in. Analysts are offered together; the debates and judges run in TradingAgents
   order. A missing output fails the step (one retry).
3. When the Portfolio Manager is submitted, `finalize` writes `reports/` (the TradingAgents tree plus
   `complete_report.md`), `full_states_log_<DATE>.json`, and a pending entry in the decision log.
4. Optionally `berkshire gate RUN` sizes an intent (`orders.json` in the run) and `berkshire enqueue` puts it in
   the approval queue.

## Home layout (`~/.berkshire`, `BERKSHIRE_HOME`)

| Path | Contents |
|---|---|
| `config.json`, `last_run.json` | Settings, and the last interactive answers offered as defaults |
| `runs/<TICKER>/<DATE>/` | `state.json`, `prompts/`, `outputs/`, `cache/` (price history for this run), `reports/`, `full_states_log_<DATE>.json`, `orders.json` |
| `memory/trading_memory.md` | The decision log, with pending and resolved entries and reflections |
| `settlements/` | Settlement work files for the Reflector |
| `queue.json` | The approval queue |
| `tick/<DATE>/` | A tick's saved eToro responses, portfolio and quotes |
| `backtest/<RUN_ID>/` | An isolated home per backtest |
| `jobs/`, `server.json`, `server.log` | Dashboard jobs and the running API server |

## The daily tick

`/berkshire:tick` reads the eToro book and watchlist, builds the universe, settles and reflects on due decisions,
stops early (with a notification) when eToro or Yahoo is down or the market is closed, analyses each instrument
serially with `--checkpoint --skip-if-complete`, fetches quotes once, runs the gate, and queues intents for
`/berkshire:approve`. One instrument's failure never aborts the tick.

## Plan

The first build delivered every area in [requirements.md](requirements.md) in this order: roles and routing
(REQ-ROLE, REQ-FLOW), context and output (REQ-CTX, REQ-OUT), data (REQ-DATA), memory (REQ-MEM), checkpoint and
reports (REQ-CKPT, REQ-RPT), risk gate and execution (REQ-RISK, REQ-EXE), scheduling (REQ-SCHED), backtest
(REQ-BT), views (REQ-UI), CI (REQ-CI) and upstream tracking (REQ-UP). Further work comes from the upstream ledger
([upstream.md](upstream.md)) and the repository's issues; each change amends its requirements as described in
[AGENTS.md](../AGENTS.md).
