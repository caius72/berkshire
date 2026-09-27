# Upstream scout, 2026-09-27

A second run the same day, the first to cover the upstream v0.5.2 development branch, is in [README-2.md](README-2.md).

TauricResearch/TradingAgents `main` is still at `35543d0` (v0.5.1). Third run.

## Summary

| | |
|---|---|
| Upstream commits on `main` since the watermark | 0 (no release, no changelog entry) |
| Features added | 0 |
| Open PRs | 48: 19 already analysed and unchanged, 29 new |
| Analysed | 10 in depth: 2 adapt, 8 decline. #1259 is covered by #1265's analysis (a strict subset). |
| Deferred | 18 (listed below) |

Two changes are worth doing, both small:

1. **Bound the analyst subagents' turns** (from #1421, S). No Berkshire analyst sets `maxTurns`. An analyst that keeps calling tools never returns, so it stalls the serial tick for every later instrument. REQ-SCHED-05 ("one failure never aborts the tick") only holds for failures that return. Add `maxTurns` to the four tool-using analysts, and keep the existing rule that a missing report fails the instrument.
2. **Warn that backtests aren't free of model look-ahead** (from #940, S). The point-in-time guards limit the data the agents see, not what Claude learned in training. No backtest surface says so: the CLI summary, `--json`, the dashboard and the skill all show hit rate and alpha without the caveat. Add it to each of them.

**Blind spot: upstream develops on a `v0.5.2` branch.** `origin/v0.5.2` carries 22 unreleased commits that are not on `main`, so the watermark doesn't see them. Several touch areas Berkshire mirrors: the rating carried through the run (#1383), benchmarks for Taiwan, Korea, Singapore and the main European exchanges (#1392, cf. REQ-MEM-04), the dates a FRED change spans (#1397), reporting a Yahoo rate limit as a rate limit (#1387), run provenance in reports (#752), and parallel analysts (#1255). #1421 targets that branch. They'll show up on `main` at the v0.5.2 release. The skill now tracks the development branch too (step 1.5), and the next run reviews these commits.

## Upstream changes

None: `origin/main` is unchanged since v0.5.1. See the `v0.5.2` note above.

## Pull requests

| PR | Title | Verdict | Status | Effort | Rationale | Report |
|---|---|---|---|---|---|---|
| #1421 | Stop an analyst that keeps calling tools | adapt | candidate | S | Berkshire analysts have no `maxTurns`, so a looping subagent stalls the serial tick. Take the bound. Skip upstream's silent empty report, which still feeds a decision. | [pr-1421](pr-1421.md) |
| #940 | Note model cutoff in reproducibility | adapt | candidate | S | The data guards don't cover what the model already knows, and Berkshire is Claude-only (Opus showed recall in the #805 audit). Add the caveat to every backtest surface. | [pr-940](pr-940.md) |
| #1426 | akshare (Sina) market data vendor | decline | declined | M | Adds US prices, which yfinance already serves, and mainland A-shares, which eToro doesn't offer. Its point-in-time guards (bfill, no stale check) are weaker than yfinance's. REQ-DATA-12 covers Yahoo 429s. | [pr-1426](pr-1426.md) |
| #1183 | A-share support via Eastmoney | decline | declined | L | eToro offers no A-shares, and the adapter isn't point-in-time. It turns off yfinance, FRED and Polymarket for everyone. Capital flow isn't sentiment. | [pr-1183](pr-1183.md) |
| #702 | SearXNG as a self-hosted news vendor | decline | declined | M | The time range counts back from now and undated results are kept, so future news leaks into past dates. WebSearch and Google News already cover it. | [pr-702](pr-702.md) |
| #1074 | Retry an undecodable JSON response | decline | declined | S | An OpenAI transport retry. Claude Code handles API retries. Failed steps already re-run once, and a broken JSON block falls back to REVIEW. | [pr-1074](pr-1074.md) |
| #1265 | Env overrides: memory log, recursion limit, news | decline | declined | S | Env aliases only. Berkshire's config.json already sets these keys, and the recursion limit has no counterpart. #1259 is a strict subset. | [pr-1265](pr-1265.md) |
| #1259 | Env overrides: news parameters | decline | declined | S | A strict subset of #1265, with the same verdict. | [pr-1265](pr-1265.md) |
| #581 | Configurable metrics in report output | decline | declined | S | Its toggles hide whole agent reports, not metrics, which isn't what #545 asked for. That would weaken the audit trail (REQ-RPT-01). No tests. | [pr-581](pr-581.md) |
| #1416 | Make the Jev screening endpoint pluggable | decline | declined | S | Plumbing for a vendor Berkshire doesn't call. UP-017 already uses Claude as the judge. Exceptions from the injected judge escape `screen()`. | [pr-1416](pr-1416.md) |
| #813 | Per-model token attribution | decline | declined | S | LangChain callback plumbing. The engine fixes each step's model, and Claude Code already logs usage per subagent. | [pr-813](pr-813.md) |

The two A-share PRs (#1426, #1183) solve the same problem, and so do the deferred #1067 and #1109. The decline applies to all four for the same reason: eToro doesn't list mainland A-shares.

## Recommended Berkshire changes

### 1. Turn bound on analyst subagents (#1421)

- `agents/market-analyst.md`, `news-analyst.md`, `fundamentals-analyst.md`, `sentiment-analyst.md`: `maxTurns: 40` in the frontmatter. That's about twice the heaviest normal path, following upstream's reasoning. The debate and decision roles have only Read and Write, and need no bound.
- New **REQ-ROLE-07**: every analyst with data or web tools declares `maxTurns`. An analyst that stops without its output file fails the step through the existing no-output path: one retry, then the run stops, and a tick records the instrument as failed and moves on.
- `skills/analyze/pipeline-loop.md:28`: an agent that stopped at its turn limit counts as failed.
- Test: a `tests/test_plugin.py` check that every agent with Bash, WebSearch or WebFetch has a positive integer `maxTurns`. Add a TST row.
- Open: check once, by hand, what the Agent tool returns when the limit is hit, and that the loop sees "no output file" rather than a false DONE. Then tune the 40 from real turn counts.

### 2. Model look-ahead caveat on backtests (#940)

- New **REQ-BT-05**: every backtest summary (CLI render, `--json`, dashboard) states that the point-in-time guards limit the data, not the model's training. Cells before the model's cutoff are historically grounded simulations, not causal backtests.
- `berkshire/backtest.py`: add the sentence to `render()`'s closing caveat, and a `caveat` field to `summarize()`, which `/api/backtests` then carries. `webui/src/App.jsx`: show the caveat under the Backtests heading. `skills/backtest/SKILL.md`: when the grid starts before the session model's stated cutoff, say which cells fall before it.
- Test: the caveat appears in `render()` and in the `summarize()` dict, plus a skill inspection check. Add a TST-BT row.
- Out of scope for now: a "blind mode" that hides the ticker and dates from the debaters and judges (ai-hedge-fund #721). Revisit if a backtest shows alpha before the cutoff that disappears after it.

The two changes are independent.

## Deferred

Not analysed this run, all low relevance to Berkshire. Most are LLM-provider plumbing (not applicable under REQ-ROLE-02), or UI and docs:

- Providers and LLM plumbing: #667 (Ollama diagnostics), #731 (GitHub Copilot), #806 (route through Claude Code/Codex CLIs), #812 (subscription CLI providers), #878 (provider prompt caching; the idea is already covered by the #1281 verdict), #1121 (MiMo), #1136 (Anthropic prompt caching), #1149 (Ollama Modelfile docs), #1195 (openai_codex), #1417 (LLM request timeout), #1418 (Meta Muse Spark), #1422 (LangGraph InjectedState compatibility).
- A-share vendors: #1067, #1109 (same verdict as #1426/#1183 above).
- UI, docs and tooling: #941 (CONTRIBUTING), #1003 (Windows launcher), #1423 (CLI dashboard polish), #1424 ("Aditya's dev": a 6.8k-line web UI dump with a PDF).
