# Upstream ledger: TauricResearch/TradingAgents

What TradingAgents offers, and what Berkshire has taken from it. Maintained by the
`/upstream-scout` skill (`.claude/skills/upstream-scout`). `tools/upstream.py check`
and `tests/test_upstream.py` keep this file consistent: statuses come from the fixed set
below, and every `incorporated` or `adapted` row names requirements that exist in
[requirements.md](requirements.md).

**Status** (features and PRs):
- `incorporated`: Berkshire does the same thing.
- `adapted`: Berkshire covers the need differently. The notes say how.
- `planned`: accepted, with work to do. The notes name the next step.
- `candidate`: worth doing, not yet decided with the user.
- `watch`: promising, but too early (unmerged, unstable, or unclear value).
- `declined`: assessed, and Berkshire should not take it. The notes say why.
- `not-applicable`: does not apply to a Claude Code plugin (e.g. LLM provider plumbing).

**Verdict** (PRs only): `adopt` (take the idea as is), `adapt` (take the idea, build it the
Berkshire way), `watch`, `decline`.

## Watermark

| Key | Value |
|---|---|
| upstream | TauricResearch/TradingAgents |
| last_reviewed_commit | 35543d0 |
| last_reviewed_release | v0.5.1 |
| last_run | 2026-09-27 |

## Features

Baseline: the v0.5.1 analysis in [tradingagents-analysis.md](tradingagents-analysis.md). Later
rows come from new upstream commits and releases.

| ID | Upstream | Feature | Status | Berkshire | Notes |
|---|---|---|---|---|---|
| UP-001 | v0.5.1 | Analyst team: market, social/sentiment, news, fundamentals | incorporated | REQ-ROLE-01, REQ-ROLE-03 | Subagents with the same data access. |
| UP-002 | v0.5.1 | Bull/bear investment debate with configurable rounds | incorporated | REQ-FLOW-03, REQ-FLOW-07 | |
| UP-003 | v0.5.1 | Research Manager structured investment plan | incorporated | REQ-OUT-01 | JSON block instead of provider-native structured output. |
| UP-004 | v0.5.1 | Trader proposal grounded in the technical report, absolute price levels (#1167, #1288) | incorporated | REQ-CTX-05, REQ-OUT-03 | |
| UP-005 | v0.5.1 | Three-way risk debate | incorporated | REQ-FLOW-04 | |
| UP-006 | v0.5.1 | Portfolio Manager 5-tier rating with anti-Hold guidance | incorporated | REQ-ROLE-05, REQ-OUT-04 | |
| UP-007 | v0.5.1 | REVIEW sentinel for unparseable decisions (#1170) | incorporated | REQ-OUT-05 | |
| UP-008 | v0.5.1 | Deterministic instrument identity in every prompt (#814) | incorporated | REQ-CTX-01 | |
| UP-009 | v0.5.1 | Absent-report and debate-opening markers (#1176) | incorporated | REQ-CTX-02, REQ-CTX-03 | |
| UP-010 | v0.5.1 | Verified market snapshot as source of truth (#830) | incorporated | REQ-DATA-02 | Indicators computed with pandas instead of stockstats. |
| UP-011 | v0.5.1 | Point-in-time clamping of every dated tool | incorporated | REQ-DATA-01 | |
| UP-012 | v0.5.1 | SEC EDGAR fundamentals "as filed" | adapted | REQ-DATA-04 | yfinance statements with a filing-lag cut-off. Restated figures are not reverted to first-reported values. |
| UP-013 | v0.5.1 | News and social look-ahead trimming with coverage-gap markers | adapted | REQ-DATA-05, REQ-DATA-07 | Yahoo news is trimmed; web sources are labelled as current instead. |
| UP-014 | v0.5.1 | FRED macro indicators tool | adapted | REQ-ROLE-03 | News Analyst looks FRED series up via web search; no dedicated tool. |
| UP-015 | v0.5.1 | Polymarket prediction-market odds tool | adapted | REQ-ROLE-03 | Via web search in the News Analyst. |
| UP-016 | v0.5.1 | StockTwits and Reddit sentiment sources | adapted | REQ-ROLE-03 | Sentiment Analyst fetches them with WebFetch/WebSearch. |
| UP-017 | v0.5.1 | Jev screening of social posts (TypeSafe) | adapted | REQ-ROLE-03 | No vendor or key: the Sentiment Analyst (Claude) screens the posts itself, dropping off-topic ones and reporting on-topic and stance counts per source. |
| UP-018 | v0.5.1 | Decision log, deferred reflection, regional alpha benchmarks | incorporated | REQ-MEM-01, REQ-MEM-03, REQ-MEM-04 | Same file format. |
| UP-019 | v0.5.1 | Point-in-time lessons for historical runs (#1251) | incorporated | REQ-MEM-05 | |
| UP-020 | v0.5.1 | Memory log rotation | incorporated | REQ-MEM-06 | |
| UP-021 | v0.5.1 | Checkpoint resume keyed by graph signature | adapted | REQ-CKPT-01, REQ-CKPT-02, REQ-CKPT-03, REQ-CKPT-04 | The run directory is the checkpoint; no SQLite. |
| UP-022 | v0.5.1 | Report tree and full states log | incorporated | REQ-RPT-01, REQ-RPT-02 | |
| UP-023 | v0.5.1 | Backtest over a ticker × date grid with per-rating scoring | incorporated | REQ-BT-01, REQ-BT-02, REQ-BT-03 | |
| UP-024 | v0.5.1 | Portfolio-aware runs (holdings and cash) | incorporated | REQ-CTX-04 | Also filled from the eToro account. |
| UP-025 | v0.5.1 | Localised output language | incorporated | REQ-CTX-07 | |
| UP-026 | v0.5.1 | Crypto asset mode | incorporated | REQ-FLOW-06 | |
| UP-027 | v0.5.1 | Interactive CLI with saved answers as defaults | adapted | REQ-IF-01 | AskUserQuestion steps in /berkshire:analyze. |
| UP-028 | v0.5.1 | Rich live progress panel | adapted | REQ-UI-05, REQ-IF-06 | Web and terminal views over the local API. |
| UP-029 | v0.5.1 | Env-var configuration with type coercion that fails loudly | incorporated | REQ-IF-05 | BERKSHIRE_* instead of TRADINGAGENTS_*. |
| UP-030 | v0.5.1 | Ticker path-traversal hardening | incorporated | REQ-SAFE-01 | |
| UP-031 | v0.5.1 | Vendor routing with fallback chains (yfinance, Alpha Vantage) | adapted | REQ-DATA-12 | No second vendor (Twelve Data declined, #794): the 400-day OHLCV frame is cached per (symbol, trade date) in the run dir, with bounded backoff on Yahoo rate limits. |
| UP-032 | v0.5.1 | Multi-provider LLM registry and model catalog | not-applicable | | Berkshire runs on Claude subagents; model choice is REQ-ROLE-02. |
| UP-033 | v0.5.1 | Provider reasoning/effort, temperature, retry and token knobs | not-applicable | | Handled by Claude Code. |
| UP-034 | v0.5.1 | Docker images and compose | not-applicable | | A Claude Code plugin. |

## Pull requests

Open (and recently closed) upstream PRs. `Head` is the PR head commit that was analysed; the
PR is re-analysed only when it changes. Reports: [upstream-reports/](upstream-reports/).

| PR | Title | Head | Reviewed | Verdict | Status | Berkshire | Rationale |
|---|---|---|---|---|---|---|---|
| #1406 | Point-in-time valuation snapshot with split adjustment | e48812009514 | 2026-09-25 | adapt | adapted | REQ-DATA-07, REQ-DATA-08 | Adapted on yfinance: past-dated fundamentals withhold live figures; new valuation tool (TTM or FY EPS, filed-by cutoff, one split basis checked). NVDA 2024-09-15 P/E 100, not the PR's ~11. |
| #835 | Earnings-context tool for catalyst awareness | 148b2b62f517 | 2026-09-25 | adapt | adapted | REQ-DATA-09, REQ-ROLE-03 | Adapted: earnings tool keyed on announcement dates, flag tied to the decision horizon, no later results or stale consensus. Open: gate rule to shrink/veto opens before earnings. |
| #819 | ETF analysis with holdings, drill-down and risk guidance | 0d6c16e20c89 | 2026-09-25 | adapt | adapted | REQ-FLOW-10, REQ-DATA-10, REQ-IF-04, REQ-ROLE-03, REQ-CTX-01 | Adapted: etf mode (quoteType / eToro type 6), fund prompts, leveraged decay warning, ETF risk axes; etf_profile tool, current-labelled, undisclosed holdings explicit. Drill-down skipped. |
| #673 | investment_horizon configuration parameter | b45c97e2ae0b | 2026-09-25 | adapt | adapted | REQ-CTX-08, REQ-MEM-03 | Adapted: the holding_period_days scoring window is stated in all 12 prompts and keyed into the run signature; no second horizon knob to drift from settlement. |
| #1408 | Market-data resilience, tool error shielding, doctor command | 888c6c10ca81 | 2026-09-25 | adapt | adapted | REQ-DATA-06 | Adapted: NO_DATA_AVAILABLE / DATA_UNAVAILABLE markers with a do-not-fabricate directive on every data tool; all analyst personas honour them. Doctor, yf fallback, catch-all shielding declined. |
| #1082 | Probability and risk/reward review on every Trader proposal | 1f2374963d51 | 2026-09-25 | adapt | adapted | REQ-OUT-01, REQ-OUT-03, REQ-OUT-07, REQ-RISK-09 | Adapted: optional target_price; the engine computes R/R only for correctly ordered levels and names inverted ones; the gate logs R/R. win_probability and bull/bear fields skipped. |
| #1087 | Calibrate lessons with a surprise ratio | 5f55c7db1ab6 | 2026-09-25 | adapt | adapted | REQ-MEM-08, REQ-MEM-04 | Adapted: the Reflector gets the PM target's implied move from the same start close as the return, with the horizon; no surprise ratio, no sign flip, log format unchanged. |
| #922 | Bluesky, Mastodon and Fear & Greed sentiment sources | 0588a2e52f67 | 2026-09-25 | adapt | adapted | REQ-ROLE-03, REQ-DATA-07 | Adapted: Bluesky only, via WebFetch on api.bsky.app with the run's since/until window (verified PIT); engagement labelled current; empty never lowers confidence. Mastodon, F&G declined. |
| #1404 | Optional Jev debate gate (early stop) | 78eb1adbc81c | 2026-09-25 | decline | declined |  | Token saving without quality gain; breaks deterministic routing (REQ-FLOW-08), adds a vendor, uncaught TypeError at debate_gate.py:68. |
| #584 | Pre-computed indicator interpretations | 90c06f0d316c | 2026-09-25 | decline | declined |  | Verified snapshot already gives deterministic indicators; labels are uncalibrated and the Bollinger rule is dead (compute.py:89). |
| #956 | Alternative method to get news data (Google News) | 21277d6738ff | 2026-09-26 | adapt | adapted | REQ-DATA-05, REQ-DATA-07, REQ-ROLE-03 | Google News RSS merged into `news`: after:/before: windowed, clamped, deduplicated, tagged headline-only; fails soft. English edition, no Malaysia defaults. |
| #1414 | Print the fundamentals percentages with their unit | 529048c94c02 | 2026-09-26 | adapt | adapted | REQ-DATA-11 | dividendYield rendered with %, a units note that margins/returns/growth are fractions; debtToEquity is not printed here. |
| #1413 | React frontend | 3f0bf51b4471 | 2026-09-26 | decline | declined | REQ-UI-06 | Declined (Stripe SaaS layer; unauthenticated path traversal at main.py:295-302). Idea taken: start_job refuses a duplicate running (ticker, date), REQ-UI-06. |
| #794 | Twelve Data as a third data vendor | 411257a41440 | 2026-09-26 | decline | declined |  | Keyed; no Yahoo-symbol, non-US or futures coverage; no news; fundamentals not PIT. For UP-031 cache yfinance calls and back off first. |
| #1407 | Sentiment Analyst: let the caller supply its data sources | 1ca16a2df0e7 | 2026-09-26 | decline | declined |  | Graph-injection plumbing with no archive to feed it; Berkshire's subagent fetches its own sources and labels non-PIT social data. PR bundles unrelated features. |
| #513 | Optional custom prompt support | 4fed0d3ee9ec | 2026-09-26 | decline | declined |  | Horizon covered by REQ-CTX-08; free text in all 12 roles skews debate and memory, bypasses the run signature, injects into the dashboard's claude -p string. |
| #359 | Factor rule analyst with manual rule injection | 2fb715915b34 | 2026-09-26 | decline | declined |  | Undated user priors break evidence-only and PIT rules; loads example rules by default, truncates debate history; stale and conflicting. |
| #302 | ACE - Agentic Context Engineer | c510a8721ada | 2026-09-26 | decline | declined |  | Self-graded skillbook ignores outcomes, no as_of filter, breaks on ace-framework 0.12. Berkshire's settled PIT lessons are better. |
| #1281 | Cache-friendly debate and analyst prompts | 5ed37446cffb | 2026-09-26 | decline | declined |  | Berkshire already splits static persona (agent file) from volatile context (prompt file); cross-debater prefix reuse can't work with subagents. Covers #878's idea. |
| #401 | Multi-LLM routing (stage and role based) | e5690d038813 | 2026-09-26 | decline | declined |  | Berkshire already routes Claude models per step (REQ-ROLE-02); the rest is multi-provider plumbing, out by D1; PR puts judges on the quick model. |
| #1421 | Stop an analyst that keeps calling tools before it ends the run | 503bca6c92fd | 2026-09-27 | adapt | planned | REQ-SCHED-05 | Next: add REQ-ROLE-07 + TST row, maxTurns: 40 on the 4 tool-using analysts, plugin test, pipeline-loop note; check what Agent returns at the limit. |
| #940 | Note model cutoff in reproducibility | 361b9339a78b | 2026-09-27 | adapt | planned | REQ-BT-03 | Next: add REQ-BT-05 + TST row; caveat in backtest render() and summarize(), dashboard Backtests view, skills/backtest cutoff note; test. |
| #1426 | akshare (Sina) market data vendor | 1613d56f4688 | 2026-09-27 | decline | declined |  | US (yfinance has it) plus A-shares (not on eToro); weaker PIT guards (bfill, no stale check). REQ-DATA-12 covers Yahoo 429s. Same for #1067, #1109. |
| #1183 | A-share market support via Eastmoney data adapter | ca322b86a13b | 2026-09-27 | decline | declined |  | eToro lists no A-shares; adapter not PIT; config drops yfinance/FRED/Polymarket for all; capital flow is not sentiment. |
| #702 | SearXNG as a self-hosted news vendor | 95b4dd68a8b8 | 2026-09-27 | decline | declined |  | time_range counts back from now and undated results are kept (searxng.py:124,166): future news leaks into past dates. WebSearch + Google News cover it. |
| #1074 | Retry an undecodable JSON response body | 5101813cbfd6 | 2026-09-27 | decline | declined |  | OpenAI transport retry; Claude Code retries the API. Failed steps already re-run once, bad JSON falls back to REVIEW (REQ-OUT-05). |
| #1265 | Env overrides for memory log, recursion limit, news parameters | eff1d94f779b | 2026-09-27 | decline | declined |  | Env aliases only; Berkshire config.json already sets these keys, max_recur_limit has no counterpart. |
| #1259 | Env overrides for news parameters | c0f921644525 | 2026-09-27 | decline | declined |  | Strict subset of #1265; same verdict. |
| #581 | Configurable metrics in report output | 9db0a0a04082 | 2026-09-27 | decline | declined |  | Toggles hide whole agent reports, not metrics (ignores #545); would weaken the REQ-RPT-01 audit trail; no tests. |
| #1416 | Make Jev screening endpoint pluggable | 03239407f718 | 2026-09-27 | decline | declined |  | Plumbing for a vendor Berkshire doesn't call; UP-017 already judges with Claude. Judge exceptions escape screen() (post_screen.py:78,152). |
| #813 | Per-model token attribution in StatsCallbackHandler | bc40785e1640 | 2026-09-27 | decline | declined |  | LangChain callback plumbing; the engine fixes each step's model and Claude Code logs usage per subagent. |
