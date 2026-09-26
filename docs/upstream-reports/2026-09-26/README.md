# Upstream scout, 2026-09-26

TauricResearch/TradingAgents is still at `35543d0` (v0.5.1). Second run.

## Summary

| | |
|---|---|
| Upstream commits since the watermark | 0 (no release, no changelog entry) |
| Open PRs | 41: 10 already analysed and unchanged, 31 new (the 30 deferred last run, plus #1414) |
| Analysed | 10: 2 adapt, 8 decline |
| Deferred | 21 (listed below) |

This batch was mostly plumbing and features that don't transfer. The changes worth doing:

1. **Google News for non-US instruments** (from #956, M). With a windowed query, RHM.DE gets 100 news items against 10 from Yahoo, and EIMI.L gets 24 against 0. The `after:`/`before:` operators keep it point-in-time. Merge it into the existing `news` tool.
2. **Fundamentals with units** (from #1414, S). On same-day runs, `fundamentals` prints `dividendYield` (in percent) without a unit, next to five ratios that are fractions.
3. **Refuse a duplicate running analysis** (prompted by #1413, S). `start_job` will spawn a second headless run for a (ticker, date) that is already running. Two orchestrators on one run directory then race on `state.json`.
4. **Fewer Yahoo calls per instrument, and backoff** (prompted by #794 and UP-031, S–M). Each `berkshire data` call re-downloads the same 400-day price history (`check_listed`, snapshot, indicators, ATR, valuation). Caching it once per run and retrying on rate limits protects the daily tick better than a second vendor.

**Security note on upstream #1413** (not a Berkshire issue). Its single-page-app catch-all route (`main.py:295-302`) has an unauthenticated path traversal, reproduced by the analysis, that can read API keys and the database. Berkshire's static route is traversal-safe and tested (TST-UI-10). Consider reporting it to the maintainers.

## Upstream changes

None: `origin/main` is unchanged since v0.5.1.

## Pull requests

| PR | Title | Verdict | Status | Effort | Rationale | Report |
|---|---|---|---|---|---|---|
| #956 | Alternative method to get news data (Google News) | adapt | candidate | M | Large gain for non-US names, and point-in-time with `after:`/`before:`. The PR skips both operators, filters client-side, reports failure as "no news" and forces a Malaysian default. | [pr-956](pr-956.md) |
| #1414 | Print the fundamentals percentages with their unit | adapt | candidate | S | Berkshire has the same ambiguity on same-day runs (`dividendYield` in percent, ratios as fractions). Label the unit and state that the ratios are fractions. | [pr-1414](pr-1414.md) |
| #1413 | React frontend | decline | declined | S | A Stripe SaaS layer with no decision value, plus an unauthenticated path traversal. The one idea taken is to refuse a duplicate running start (see recommendation 3). | [pr-1413](pr-1413.md) |
| #794 | Twelve Data as a third data vendor | decline | declined | L | The wrong fallback: it needs a key, doesn't cover Yahoo symbols, non-US listings or futures, has no news, and its fundamentals aren't point-in-time. Cache and backoff first (recommendation 4). | [pr-794](pr-794.md) |
| #1407 | Sentiment Analyst: let the caller supply its data | decline | declined | S | Graph-injection plumbing with no archive to feed it. Berkshire's subagent fetches its own sources and already labels social data that isn't point-in-time. | [pr-1407](pr-1407.md) |
| #513 | Optional custom prompt | decline | declined | M | REQ-CTX-08 already covers the horizon. Free text in all 12 roles skews the debate and memory, bypasses the run signature, and would inject into the dashboard's `claude -p` string. | [pr-513](pr-513.md) |
| #359 | Factor rule analyst with manual rules | decline | declined | M | Undated user priors break the evidence-only and point-in-time rules. The PR loads example rules by default and truncates debate history. | [pr-359](pr-359.md) |
| #302 | ACE (Agentic Context Engineer) | decline | declined | S | An ungrounded, self-graded skillbook: outcomes are ignored, there is no as-of filter, and it breaks on current ace-framework. Berkshire's settled point-in-time lessons are better. | [pr-302](pr-302.md) |
| #1281 | Cache-friendly debate and analyst prompts | decline | declined | S | Berkshire already separates the static persona (agent file) from the changing context (prompt file), which is #878's idea. Reusing a prompt prefix across debaters can't work with subagents. | [pr-1281](pr-1281.md) |
| #401 | Multi-LLM routing by stage and role | decline | declined | S | Berkshire already routes Claude models per step. The rest is multi-provider plumbing, ruled out by D1. The PR also puts the judges on the quick model. | [pr-401](pr-401.md) |

## Recommended Berkshire changes

1. **Google News in `news`** (#956, M). Add `_google_news_items(query, start, end)` to `berkshire/data.py`, querying Google News RSS with `after:`/`before:` widened by one day and clamped with `in_window`. Merge its results into `tool_news` with Yahoo's, removing duplicates by normalised title. Query by the resolved company name, tag each line with its source, and mark Google items as headline-only. The coverage-gap marker stays computed from Yahoo only. A Google failure adds a line and never fails the tool.
   - Requirements: amend REQ-DATA-05, REQ-ROLE-03 and REQ-DATA-07.
   - Tests: a stubbed RSS document, the window clamp, deduplication, and the failure line.
   - Interaction: it covers the same instruments as Bluesky's since/until query; both help point-in-time backtests.
2. **Units in `fundamentals`** (#1414, S). Render `dividendYield` with `%`, and add a footer saying margins, returns and growth are fractions.
   - Requirements: add REQ-DATA-11.
   - Tests: a same-day stub; a missing value gives no row.
3. **Duplicate-run guard** (S). In `Api.start_job`, refuse with an error when a job for the same resolved (ticker, date) is running. This reuses `stop_run`'s job matching. The web form and TUI show the error.
   - Requirements: amend REQ-UI-06.
   - Tests: a second start is refused, and a different date is still spawned.
4. **Yahoo cache and backoff** (S–M). Cache the 400-day OHLCV frame per (symbol, trade date) in the run directory, and add bounded backoff on yfinance's rate-limit error.
   - Requirements: a new REQ-DATA-12 (robustness), and update UP-031.
   - Tests: repeated tool calls hit the network once, and backoff gives up after N tries with `DATA_UNAVAILABLE`.

Suggested order: 3 (a correctness bug in the dashboard) → 2 → 1 → 4.

## Deferred (21)

LLM-provider plumbing (#667, #731, #806, #812, #1121, #1136, #1195), prompt caching (#878, which overlaps #1281 and is covered by the analysis above), A-share data vendors (#1067, #1109, #1183), SearXNG news (#702), docs and launchers (#940, #941, #1003, #1149), config knobs (#1259, #1265), report metrics (#581), per-model token stats (#813), and the JSON retry (#1074; Berkshire already falls back to free text).
