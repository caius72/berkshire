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
| last_run | 2026-09-25 |

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
| UP-017 | v0.5.1 | Jev screening of social posts (TypeSafe) | candidate | | Needs a TypeSafe key and an extra vendor; value unproven for Berkshire. |
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
| UP-031 | v0.5.1 | Vendor routing with fallback chains (yfinance, Alpha Vantage) | watch | | yfinance only today; a fallback matters if Yahoo rate-limits scheduled ticks. |
| UP-032 | v0.5.1 | Multi-provider LLM registry and model catalog | not-applicable | | Berkshire runs on Claude subagents; model choice is REQ-ROLE-02. |
| UP-033 | v0.5.1 | Provider reasoning/effort, temperature, retry and token knobs | not-applicable | | Handled by Claude Code. |
| UP-034 | v0.5.1 | Docker images and compose | not-applicable | | A Claude Code plugin. |

## Pull requests

Open (and recently closed) upstream PRs. `Head` is the PR head commit that was analysed; the
PR is re-analysed only when it changes. Reports: [upstream-reports/](upstream-reports/).

| PR | Title | Head | Reviewed | Verdict | Status | Berkshire | Rationale |
|---|---|---|---|---|---|---|---|
| #1406 | Point-in-time valuation snapshot with split adjustment | e48812009514 | 2026-09-25 | adapt | planned | REQ-DATA-07, REQ-ROLE-03 | Planned: withhold price-derived fields on past dates (amend REQ-DATA-07), then a PIT valuation tool with split reconciliation (REQ-DATA-08). Report A1. |
| #835 | Earnings-context tool for catalyst awareness | 148b2b62f517 | 2026-09-25 | adapt | planned | REQ-ROLE-03, REQ-DATA-07 | Planned: earnings tool on get_earnings_dates keyed on announcement date, consensus only for same-day runs (REQ-DATA-09). Gate rule deferred. Report A2. |
| #819 | ETF analysis with holdings, drill-down and risk guidance | 0d6c16e20c89 | 2026-09-25 | adapt | candidate | REQ-FLOW-06, REQ-IF-04, REQ-ROLE-03, REQ-CTX-01, REQ-DATA-07 | Watchlist ETFs are analysed as companies. Add etf mode (quoteType / eToro type 6) and a current-only etf_profile; skip drill-down and Alpha Vantage. |
| #673 | investment_horizon configuration parameter | b45c97e2ae0b | 2026-09-25 | adapt | planned | REQ-MEM-03 | Planned: horizon_instruction(holding_period_days) in every prompt and the run signature (REQ-CTX-08, amend REQ-MEM-03). Report B1. |
| #1408 | Market-data resilience, tool error shielding, doctor command | 888c6c10ca81 | 2026-09-25 | adapt | planned | REQ-DATA-06 | Planned: NO_DATA_AVAILABLE / DATA_UNAVAILABLE sentinel with a do-not-fabricate line in cmd_data, honoured by all analyst personas (amend REQ-DATA-06). Report C. |
| #1082 | Probability and risk/reward review on every Trader proposal | 1f2374963d51 | 2026-09-25 | adapt | candidate | REQ-OUT-01, REQ-OUT-03, REQ-RISK-09 | Engine-computed R/R from entry/stop/target with a direction check (PR's abs() hides inverted levels). Skip uncalibrated win_probability and bull/bear fields. |
| #1087 | Calibrate lessons with a surprise ratio | 5f55c7db1ab6 | 2026-09-25 | adapt | candidate | REQ-MEM-04 | Ratio compares a months-long target with a 5-day return and flips downside signs. Give the Reflector the target-implied move from the trade-date close. |
| #922 | Bluesky, Mastodon and Fear & Greed sentiment sources | 0588a2e52f67 | 2026-09-25 | adapt | candidate | REQ-ROLE-03 | Take Bluesky only, via WebFetch with since/until (point-in-time capable). The PR leaks look-ahead on all three feeds; F&G is the crypto index; Mastodon is noise. |
| #1404 | Optional Jev debate gate (early stop) | 78eb1adbc81c | 2026-09-25 | decline | declined |  | Token saving without quality gain; breaks deterministic routing (REQ-FLOW-08), adds a vendor, uncaught TypeError at debate_gate.py:68. |
| #584 | Pre-computed indicator interpretations | 90c06f0d316c | 2026-09-25 | decline | declined |  | Verified snapshot already gives deterministic indicators; labels are uncalibrated and the Bollinger rule is dead (compute.py:89). |
