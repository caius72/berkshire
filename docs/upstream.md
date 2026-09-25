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
