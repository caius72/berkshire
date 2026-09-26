# Berkshire — requirements

Berkshire is a Claude Code plugin that reproduces the TradingAgents multi-agent
framework (see [tradingagents-analysis.md](tradingagents-analysis.md)). It runs
on demand or in a `/loop`, and sends approved orders to eToro through the eToro MCP.

Each requirement has a stable id `REQ-<AREA>-<NN>`. Every requirement is
verified by at least one test in [test-plan.md](test-plan.md). The traceability check
(`tests/test_traceability.py`) fails if a requirement has no test, or if a test names an unknown requirement.

**Priority:** M = must, S = should.
**Verification:** T = automated test, I = inspection test (automated check of plugin files), D = manual demonstration (documented procedure).

## Decisions recorded with the user (2026-09-24)

| # | Decision |
|---|---|
| D1 | The deliverable is a Claude Code plugin. Roles are subagents, and deterministic logic is a Python package tested by pytest. |
| D2 | Execution goes to the eToro **demo** account by default. Every order needs explicit human approval: the tick queues orders, and `/berkshire:approve` places them. |
| D3 | Data comes from yfinance (bundled Python tools), eToro (quotes, portfolio, eligibility) and WebSearch/WebFetch (news, macro, social). |
| D4 | A scheduled run covers the current holdings plus one named eToro watchlist. |
| D5 | The risk limits are configurable, with conservative defaults. |
| D6 | Ratings map to target weights: Buy → full target, Overweight → half target, Hold/REVIEW → no order, Underweight → close half, Sell → close fully. |
| D7 | Scheduling is a local `/loop` running once per trading day. |
| D8 | The docs are markdown in the repo, with automated traceability. |

---

## 1. Roles (REQ-ROLE)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-ROLE-01 | M | The plugin shall provide one subagent per TradingAgents role: Market Analyst, Sentiment Analyst, News Analyst, Fundamentals Analyst, Bull Researcher, Bear Researcher, Research Manager, Trader, Aggressive Risk Analyst, Conservative Risk Analyst, Neutral Risk Analyst, Portfolio Manager, and Reflector. | I |
| REQ-ROLE-02 | M | The Research Manager and Portfolio Manager shall run on the deep model (default `opus`). All other roles shall run on the quick model (default `sonnet`). Both are configurable (`deep_think_llm`, `quick_think_llm`). | T |
| REQ-ROLE-03 | M | Each analyst shall have the data access of its TradingAgents counterpart. Market: OHLCV, indicators, verified snapshot. Fundamentals: profile, point-in-time valuation, earnings calendar, ETF profile for funds, balance sheet, cash flow, income statement, insider transactions. News: ticker news (Yahoo Finance and Google News), global news, and web search for macro data and prediction markets. Sentiment: news plus web search of StockTwits and Reddit, and Bluesky queried within the run's 7-day window. The Sentiment Analyst drops social posts that are not about the instrument and reports each social source's on-topic count and stance count, untagged posts included. | I |
| REQ-ROLE-04 | M | Researchers, debaters, managers and the Trader shall decide only on the evidence in their prompt. They are not given web or data tools. | I |
| REQ-ROLE-05 | M | Each role's persona shall keep the substantive directives of the TradingAgents prompt: the bull/bear focus points, the risk stances, the Trader's absolute price levels, the judges' rating scales and anti-Hold guidance, and the end-of-report markdown table for analysts. | I |
| REQ-ROLE-06 | S | The Market Analyst shall pick up to 8 complementary indicators from the TradingAgents indicator catalogue. | I |

## 2. Pipeline and routing (REQ-FLOW)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-FLOW-01 | M | A run shall execute in this order: selected analysts → investment debate → Research Manager → Trader → risk debate → Portfolio Manager. | T |
| REQ-FLOW-02 | M | Selected analysts are independent and shall be offered for parallel execution. The debate starts only after every selected analyst has reported. | T |
| REQ-FLOW-03 | M | The investment debate shall alternate, Bull first, for `2 × max_debate_rounds` turns, then hand over to the Research Manager. | T |
| REQ-FLOW-04 | M | The risk debate shall rotate Aggressive → Conservative → Neutral for `3 × max_risk_discuss_rounds` turns, then hand over to the Portfolio Manager. | T |
| REQ-FLOW-05 | M | Analyst selection shall accept any non-empty subset of {market, social, news, fundamentals}. An empty or unknown selection is rejected before the run starts. | T |
| REQ-FLOW-06 | M | For crypto the Fundamentals Analyst shall be dropped from the selection, and prompts shall treat the instrument as an asset, not a company. | T |
| REQ-FLOW-07 | M | Research depth shall map Shallow/Medium/Deep to 1/3/5 rounds for both debates. An explicit round-count override wins. | T |
| REQ-FLOW-08 | M | Routing shall be deterministic and computed from persisted state only, so the same state always yields the same next step. | T |
| REQ-FLOW-09 | M | Submitting output for a step that is not currently due shall be rejected without changing state. | T |
| REQ-FLOW-10 | M | Exchange-traded funds shall run in an `etf` mode, set by the vendor's quoteType, eToro asset type 6 or `--asset-type etf`. Prompts call it a fund, give its category, and ask for fund dimensions rather than company fundamentals. Leveraged and inverse funds carry the daily-reset warning, and the risk debaters get the ETF risk axes (tracking and premium/discount, liquidity, expense drag, concentration, decay). The Fundamentals Analyst stays selected. | T |

## 3. Context and grounding (REQ-CTX)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-CTX-01 | M | Instrument identity (name, sector/industry or fund category, exchange) shall be resolved once per run and injected into every prompt, with the exact-ticker directive. For a past date, a caveat shall say that the profile is current, not historical. If identity cannot be resolved, the run falls back to ticker-only context without failing. | T |
| REQ-CTX-02 | M | A missing analyst report shall be presented as an explicit "not available, not an empty finding" marker, never as a blank. | T |
| REQ-CTX-03 | M | A debater whose opponent has not spoken yet shall receive an explicit opening marker instead of an empty argument. | T |
| REQ-CTX-04 | M | Portfolio context shall distinguish three cases: a position held, a flat book, and not provided. "Not provided" shall tell the agent not to assume a flat book. | T |
| REQ-CTX-05 | M | The Trader shall receive the technical market report, when there is one, with the instruction to ground its entry and stop in it. | T |
| REQ-CTX-06 | M | Only the Portfolio Manager shall receive past-decision lessons. | T |
| REQ-CTX-07 | S | When `output_language` is not English, every report-producing prompt shall carry the instruction "Write your entire response in <lang>." | T |
| REQ-CTX-08 | M | Every report-producing prompt shall state the decision horizon: the `holding_period_days` window over which the decision's return and alpha are scored. It asks the agent to separate within-window drivers from longer-horizon ones, and to say so when its call rests on a longer horizon. The horizon is part of the run signature. | T |

## 4. Decisions and structured output (REQ-OUT)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-OUT-01 | M | The Research Manager, Trader, Portfolio Manager and Sentiment Analyst shall emit a JSON block matching their schema (ResearchPlan, TraderProposal, PortfolioDecision, SentimentReport). The engine renders it to the same markdown as TradingAgents. | T |
| REQ-OUT-02 | M | If the JSON block is missing or invalid, the engine shall fall back to the free-text output instead of failing the run. | T |
| REQ-OUT-03 | M | Optional price fields (entry, stop, target, price target) shall accept numbers and formatted prices (`"$1,234.50"` → 1234.5). Placeholders (`"N/A"`, `"none"`), percentages, ranges and hedged values become null. | T |
| REQ-OUT-04 | M | The run signal shall be one of Buy/Overweight/Hold/Underweight/Sell, parsed from the final decision. The parser prefers the last labelled `Rating:` line, ignores scale-legend lines, and accepts a bare rating word only when exactly one distinct rating appears. | T |
| REQ-OUT-05 | M | A final decision with no parseable rating shall produce the non-tradeable signal `REVIEW`, never Hold. | T |
| REQ-OUT-06 | M | The Sentiment score shall be bounded to 0–10, and band and confidence restricted to their enums. | T |
| REQ-OUT-07 | M | The Trader's proposal shall carry an optional target price. The engine shall compute reward/risk from entry, stop and target only when they are ordered correctly for the action (Buy: stop < entry < target; Sell: target < entry < stop). Missing, inverted or zero-risk levels are named as such, and Hold has none. The model never states the ratio itself. | T |

## 5. Memory and reflection (REQ-MEM)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-MEM-01 | M | Every completed run shall append `[date \| ticker \| rating \| pending]` + `DECISION:` to the markdown decision log, in the TradingAgents format. | T |
| REQ-MEM-02 | M | Storing a second decision for the same ticker and date shall be a no-op. | T |
| REQ-MEM-03 | M | Settlement shall compute raw return and alpha over `holding_period_days` trading days against the benchmark. The benchmark is chosen by explicit override, then by exchange suffix, then SPY. An entry whose window has not fully traded stays pending. The same `holding_period_days` is the horizon the agents are told (REQ-CTX-08). | T |
| REQ-MEM-04 | M | A settled entry shall get a 2–4 sentence Reflector reflection and the resolved tag `[date \| ticker \| rating \| raw \| alpha \| Nd \| resolved:YYYY-MM-DD]`, written atomically. | T |
| REQ-MEM-05 | M | Past context shall contain up to 5 same-ticker entries (full) and 3 cross-ticker reflections, most recent first. For a historical run only lessons resolved on or before the trade date are included. | T |
| REQ-MEM-06 | S | When `memory_log_max_entries` is set, the oldest resolved entries shall be rotated out. Pending entries are never pruned. | T |
| REQ-MEM-07 | M | A run shall settle the ticker's pending decisions before it starts. The scheduled tick shall settle every ticker it covers. | I |
| REQ-MEM-08 | S | When the settled decision states a price target, the reflection input shall give the move the target implied from the same start close the return is measured from, with the stated horizon. The Reflector judges the realised move against it: a partial move in a shorter window is not a failure. The target is read only from the engine-rendered decision line, and the log format is unchanged. | T |

## 6. Data tools (REQ-DATA)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-DATA-01 | M | Every dated data tool shall clamp the requested date or window to the run's trade date, whatever the agent asks for. | T |
| REQ-DATA-02 | M | The verified snapshot shall show the latest OHLCV row on or before the trade date, a fixed indicator set, and up to 30 recent closes, with the source-of-truth notice. | T |
| REQ-DATA-03 | M | Indicators shall cover close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi, boll, boll_ub, boll_lb, atr and vwma. Unknown names return an error text listing the valid ones. | T |
| REQ-DATA-04 | M | Financial statements shall omit periods not yet filed by the trade date (conservative filing lag: 45 days quarterly, 90 days annual). Insider transactions after the trade date shall be omitted. | T |
| REQ-DATA-05 | M | News shall be trimmed to the requested window. A window the feed could not observe shall produce an explicit "unavailable, not an absence" marker. The `news` tool merges Yahoo Finance news with Google News headlines for the company name, queried inside the window with date operators, clamped to it and deduplicated by title. One source failing adds an "unavailable" line; both failing is `DATA_UNAVAILABLE`. | T |
| REQ-DATA-06 | M | Data tool failures shall return a readable string, never a traceback. It starts with `DATA_UNAVAILABLE:` and keeps the cause for failures, or `NO_DATA_AVAILABLE:` when the source has nothing for the instrument and date. Either way it ends with a do-not-fabricate directive, and every analyst persona treats such output as missing data. Usage errors (unknown tool, missing arguments) are reported plainly. | T |
| REQ-DATA-07 | M | Non-point-in-time sources shall not leak into past-dated runs. The company profile's price- and period-derived figures (valuation, margins, growth, balance sheet, beta, 52-week range) are withheld on past dates, leaving identity only. Web search and social sources are labelled as current in tool output and in the analyst prompts. Google News items are labelled headline-only and dated to the day, from a current search index. | T |
| REQ-DATA-08 | M | A `valuation` tool shall give market cap, P/E and P/B as of the trade date: the close on or before the date, diluted EPS from four filed quarters (TTM) or else the latest filed fiscal year (never a single quarter), and shares and equity from the newest filed balance sheet. Every input must be ≤ 400 days old and on one split basis (checked via net income ÷ EPS ≈ shares). Losses and negative equity are reported as n/m, and each figure shows its basis and date. | T |
| REQ-DATA-09 | M | An `earnings` tool shall give earnings context keyed on announcement dates. History is only announcements strictly before the trade date, with the estimate and reported EPS. The next announcement shows about how many trading days away it is and whether it falls inside the decision horizon (`holding_period_days`). Its consensus appears only on a same-day run, and a later event's result is never shown. Instruments without a calendar get `NO_DATA_AVAILABLE`. | T |
| REQ-DATA-10 | M | An `etf_profile` tool shall report a fund's category, family, expense ratio, assets, asset mix, sector weights, and top holdings with their concentration, labelled "top N shown only". Holdings that are empty or only a cash line are reported as not disclosed, never as a concentration. Past-dated runs get the current-data caveat, and non-funds get `NO_DATA_AVAILABLE`. | T |
| REQ-DATA-11 | S | Profile values whose unit differs from their neighbours shall carry the unit in tool output (`dividendYield` with `%`), and the full profile shall state that margins, returns and growth are fractions. | T |

## 7. Interface parity (REQ-IF)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-IF-01 | M | `/berkshire:analyze` shall walk the TradingAgents steps interactively: ticker, date, output language, analysts, research depth, models. Previous answers are offered as defaults. | D |
| REQ-IF-02 | M | `/berkshire:analyze TICKER [DATE] [--analysts …] [--depth …] [--language …] [--portfolio FILE\|etoro] [--checkpoint] [--clear-checkpoints]` shall run non-interactively. | T |
| REQ-IF-03 | M | The trade date shall be canonical `YYYY-MM-DD` and not in the future. The default is today. | T |
| REQ-IF-04 | M | Tickers shall keep exchange suffixes (`.DE`, `.L`, `.T`, `-USD`) and be rejected if unsafe as a path component. Crypto is detected from the `-USD` suffix or from an eToro crypto asset type. A fund is detected from the vendor's `quoteType` ETF or from eToro asset type 6. | T |
| REQ-IF-05 | M | Configuration shall come from defaults, then `~/.berkshire/config.json`, then `BERKSHIRE_*` env vars, then CLI flags, each overriding the one before. Env values are coerced to the default's type, and invalid values fail loudly. | T |
| REQ-IF-06 | M | During a run the user shall see progress by team (pending, in progress, done) plus the current report, like the TradingAgents live panel. | T |
| REQ-IF-07 | M | At the end of a run the user shall see the signal and the path to the complete report, and a full report on request. | D |
| REQ-IF-08 | S | The same engine commands shall work outside Claude Code (`berkshire …` CLI) for scripting and tests. | T |
| REQ-IF-10 | M | A ticker that is an eToro-only name shall be mapped to its Yahoo symbol through `symbol_map` (e.g. EUROOIL → BZ=F, keeping EUROOIL as the eToro symbol), in `/berkshire:analyze` and the dashboard alike. An instrument without Yahoo prices up to the analysis date shall be refused before any agent runs, with the fix named. If Yahoo is unreachable, the run proceeds. | T |

## 8. Checkpoint and resume (REQ-CKPT)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-CKPT-01 | M | Every submitted step shall be persisted atomically before the next step is offered. | T |
| REQ-CKPT-02 | M | With `--checkpoint`, a run for the same ticker, date and signature (analysts, rounds, asset type, portfolio fingerprint) shall resume from the last completed step. A different signature starts fresh. | T |
| REQ-CKPT-03 | M | Without `--checkpoint`, or after the run completed, re-running shall start fresh. | T |
| REQ-CKPT-04 | S | `--clear-checkpoints` shall delete all incomplete runs. | T |

## 9. Reports (REQ-RPT)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-RPT-01 | M | A completed run shall write the TradingAgents report tree: `1_analysts/{market,sentiment,news,fundamentals}.md`, `2_research/{bull,bear,manager}.md`, `3_trading/trader.md`, `4_risk/{aggressive,conservative,neutral}.md`, `5_portfolio/decision.md`, and `complete_report.md` with sections I–V. | T |
| REQ-RPT-02 | M | A completed run shall write `full_states_log_<date>.json` with the TradingAgents keys. | T |

## 10. Backtest (REQ-BT)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-BT-01 | M | `/berkshire:backtest TICKERS --start --end [--every N] [--analysts] [--run-id]` shall run a grid of dates (never past today) into its own isolated home. The live decision log and queue are never touched. | T |
| REQ-BT-02 | M | Re-running with the same run id shall skip cells that are already in its log. | T |
| REQ-BT-03 | M | The summary shall report resolved/pending/unscored counts, and per rating: n, directional hit rate (none for Hold), and mean alpha. | T |
| REQ-BT-04 | M | Backtest cells shall never create orders. | T |

## 11. Risk gate and order mapping (REQ-RISK)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-RISK-01 | M | The rating shall map to an order intent per D6. Buy targets `target_weight` of equity, Overweight half of it. Underweight closes `underweight_close_fraction` of units, Sell closes all units. Hold and REVIEW create no order. | T |
| REQ-RISK-02 | M | An opening amount shall be the smallest of: (target value − current value), `max_order_pct` × equity, `max_instrument_pct` × equity − current value, and cash − `min_cash_pct` × equity. Below `min_order_amount` there is no order. | T |
| REQ-RISK-03 | M | Every opening order shall carry a stop-loss below the ask. Use the Trader's stop when valid, else ask − `atr_stop_multiple` × ATR. With neither available, the order is vetoed. | T |
| REQ-RISK-04 | M | Orders shall be long-only with leverage 1. The gate never produces a short or leveraged order. | T |
| REQ-RISK-05 | S | Take-profit shall be the Portfolio Manager's price target when it is above the ask. Otherwise none is set. | T |
| REQ-RISK-06 | M | At most `max_orders_per_run` intents are queued per tick. Opens are ranked by rating strength, and closes always go first. | T |
| REQ-RISK-07 | M | Closes shall target only directly held positions, never copy-trading mirrors. | T |
| REQ-RISK-08 | M | All limits shall be configurable and validated (fractions in (0,1], positive amounts). Defaults: target 5 %, max order 5 %, max instrument 15 %, min cash 10 %, 5 orders per run, $50 minimum, 2×ATR stop, close 50 % on Underweight. | T |
| REQ-RISK-09 | M | Every intent and every veto shall be recorded with its reasons in the run directory. An open with a take-profit also records its reward/risk from ask, stop and take-profit. | T |

## 12. Execution via eToro MCP (REQ-EXE)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-EXE-01 | M | Orders shall be placed only via `prepare-trade`/`place-trade` (open) and `prepare-close`/`place-close` (close), never via `execute-write`. | I |
| REQ-EXE-02 | M | `place-trade` and `place-close` shall be called only after the user explicitly approves that single order's confirmation block in the current session, one approval per call. Unattended runs never place orders. | I, D |
| REQ-EXE-03 | M | The account shall be `demo` unless the config sets `account: real`. Every confirmation shown to the user names the account. | T, I |
| REQ-EXE-04 | M | Queue entries shall move pending → approved/rejected → placed/failed, or pending → expired (after `queue_ttl_hours`) or superseded (a newer intent for the same instrument). Only pending entries are offered for approval. | T |
| REQ-EXE-05 | M | An `outcome: pending` or `unknown` from eToro shall be recorded as such and never re-placed automatically. A retry after `unknown` reuses the same token. | I |
| REQ-EXE-06 | M | Portfolio and cash for sizing shall be read from `get-my-portfolio-summary` on the configured account. | T |
| REQ-EXE-07 | M | eToro symbols shall map to yfinance symbols: stocks and ETFs as-is, crypto → `<SYM>-USD`, and the configured map for forex, commodities and indices. Unmappable instruments are skipped with a reason. | T |

## 13. Scheduling (REQ-SCHED)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-SCHED-01 | M | `/berkshire:tick` shall do one cycle: read the eToro portfolio and watchlist, build the universe (holdings ∪ watchlist, de-duplicated), settle due decisions, analyse each instrument, run the risk gate, queue intents, and notify. It shall be usable as `/loop 24h /berkshire:tick`. | T, D |
| REQ-SCHED-02 | M | On a weekend the tick shall settle only. It does not analyse or queue. | T |
| REQ-SCHED-03 | M | A tick shall be idempotent per trade date: an instrument already completed today is not re-analysed. | T |
| REQ-SCHED-04 | S | `max_tickers_per_tick` shall cap the universe (holdings first). | T |
| REQ-SCHED-05 | M | One instrument's failure shall not abort the tick. It is recorded and reported. | D |

## 14. Safety and quality (REQ-SAFE)

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-SAFE-01 | M | Paths built from tickers or run ids shall be validated so they cannot escape the Berkshire home. | T |
| REQ-SAFE-02 | M | All state, log and queue writes shall be atomic (temp file + rename). | T |
| REQ-SAFE-03 | M | Every report shall carry the research disclaimer: "not financial advice". | T |
| REQ-SAFE-04 | M | The traceability matrix shall be complete: every REQ is covered by ≥ 1 TST, and every automated TST exists in `tests/`. | T |

## 15. Web and terminal views (REQ-UI)

Architecture follows matlab-engine-mcp / matlab-tui: one server process owns the
state, and every view is a client of its HTTP + SSE API. Recorded with the user on
2026-09-24 (D9–D12 below).

| # | Decision |
|---|---|
| D9 | CI runs on GitHub Actions. |
| D10 | The web view uses React + Vite (like matlab-engine-mcp's `webui/`). |
| D11 | The terminal view is a Textual app in this repo, an optional `tui` extra (like mtui, but not a separate repo). |
| D12 | The views watch and start runs. Placing orders stays with `/berkshire:approve` in Claude Code. |

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-UI-01 | M | `berkshire serve` shall own all view state access. The web page and the terminal UI shall be clients of its HTTP API and hold no trading logic. Clients find the server through `~/.berkshire/server.json` (port, token, pid). | T |
| REQ-UI-02 | M | The server shall bind to 127.0.0.1 and send no CORS headers. It refuses a non-loopback Host, and requires the `X-WebUI: 1` header and the per-process token on every `/api` request. The registry file is 0600. The page moves the `?t=` token to sessionStorage. Static files never resolve outside the bundle, and report text is never rendered as HTML. | T |
| REQ-UI-03 | M | Both views shall show the runs (signal and progress), the decision log, the order queue and backtest summaries. | T |
| REQ-UI-04 | M | Both views shall update live: the server emits an SSE `change` event within about 1 s of a run, log, queue or job changing. The web view reconnects with backoff. | T |
| REQ-UI-05 | M | A run's detail view shall show what the TradingAgents live panel shows: every agent's status by team, the report of each finished agent (latest by default), the step timeline, and the order proposal with the risk gate's reasons. | T |
| REQ-UI-06 | M | Both views shall let the user start an analysis (ticker, date, analysts, depth). Input is validated by the engine's rules, and a headless `claude -p /berkshire:analyze …` job is started, unless a job for the same resolved ticker and date is still running. Job status and log tail are shown. | T |
| REQ-UI-07 | M | The API shall have no endpoint that places, approves, rejects or modifies orders. The views state that orders are placed with `/berkshire:approve`. | T |
| REQ-UI-08 | M | `berkshire tui` shall provide the terminal view (runs, progress, reports, decisions, orders, jobs), with keys n (new analysis), r (refresh) and q (quit). | T |
| REQ-UI-09 | M | Textual shall be optional. The engine, server and web view work without it, and `berkshire tui` without it prints how to install the extra (exit code 3) instead of a traceback. | T |
| REQ-UI-10 | S | Without a built web bundle, the page shall say how to build it and point to `berkshire tui`. | T |
| REQ-UI-11 | M | `berkshire web` and `berkshire tui` shall start the server in the background when none is running, then print the URL or attach. | T |
| REQ-UI-12 | S | `/berkshire:dashboard` shall start the server if needed and give the user the web URL and the TUI command. | I |
| REQ-UI-13 | M | Both views shall let the user stop an unfinished analysis after a confirmation. The run is marked stopped (with time and reason), the engine then offers and accepts no further steps, and the pipeline loop reports it. A running dashboard job for that run has its process group ended. Stopped runs show as Stopped; `--checkpoint` resumes one. | T |

## 16. Continuous integration (REQ-CI)

Modelled on matlab-tui's `.gitlab-ci.yml`, as GitHub Actions (D9).

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-CI-01 | M | A workflow shall run on every push and pull request to `main` with these jobs: test, core (no extras), lint, webui, secrets, sast. | I |
| REQ-CI-02 | M | Lint shall use a pinned ruff version and the explicit rule set in `ruff.toml`, including the bandit (`S`) security rules. | I |
| REQ-CI-03 | M | The test job shall install every extra and measure branch coverage. It fails below the floor in `pyproject.toml` (a ratchet), and publishes `coverage.xml` plus a summary. | I |
| REQ-CI-04 | M | Secret-leak detection (gitleaks) shall scan the full git history on every push and pull request. | I |
| REQ-CI-05 | M | Static analysis (CodeQL) shall cover Python and JavaScript. | I |
| REQ-CI-06 | M | A job without the optional extras shall assert textual is absent and run the suite, proving REQ-UI-09 rather than assuming it. | I |
| REQ-CI-07 | M | The web view shall be checked by `npm ci`, the node unit tests and `vite build`. | I |
| REQ-CI-08 | M | The workflow shall run with read-only default permissions, use versioned actions, and fail on the first broken job. | I |

## 17. Upstream tracking (REQ-UP)

Berkshire follows TradingAgents deliberately: each upstream change or open PR is assessed and the
verdict recorded, maintained by the `/upstream-scout` skill (`.claude/skills/upstream-scout`).

| ID | Pri | Requirement | Ver |
|---|---|---|---|
| REQ-UP-01 | M | `docs/upstream.md` shall record every assessed upstream feature and pull request with a status from a fixed set. `incorporated` and `adapted` rows name existing requirement ids, every other non-final status gives its reason, and the watermark (last reviewed commit and release, last run) is present. | T |
| REQ-UP-02 | M | Each run shall analyse only open PRs that are new to the ledger or whose head commit moved since their analysis, and shall revisit ledger PRs that are no longer open. | T |
| REQ-UP-03 | M | `/upstream-scout` shall review upstream commits, releases and changelog since the watermark, and deep-analyse PRs with one agent per PR in parallel. Each agent follows a fixed brief (mechanism, soundness, maturity, value to Berkshire, fit, cost) and gives a verdict of adopt, adapt, watch or decline, with a report file. | I |
| REQ-UP-04 | M | The skill shall change only the ledger and its reports until the user chooses changes, and shall move the watermark only after the report is written. It has read-only access to the upstream repository. | I |
| REQ-UP-05 | S | The ledger shall record the v0.5.1 baseline Berkshire was built from, feature by feature. | T |
