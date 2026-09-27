# Upstream scout, 2026-09-27 (second run)

Same day as [the first run](README.md). TradingAgents `main` is still at `35543d0` (v0.5.1). This run is the first to review the `v0.5.2` development branch (skill step 1.5, added this morning).

## Summary

| | |
|---|---|
| Commits on `main` since the watermark | 0 |
| Commits on `origin/v0.5.2` (unreleased) | 22, grouped into 12 features (UP-035 to UP-046) |
| Features | 4 candidate, 4 already incorporated or adapted, 1 declined, 4 not applicable |
| Open PRs | 48: 30 analysed before, 18 new. 10 analysed in depth, 3 covered by an earlier verdict, 5 deferred. |
| PR verdicts | 3 adapt, 7 decline |

The changes worth doing, most important first:

1. **The Portfolio Manager's rating can flip** (UP-035, from #1383, S). Berkshire reads the run's signal back out of the *rendered* decision, taking the last `Rating:` label. A thesis that quotes "Street consensus rating: Buy" turns a JSON `rating: Hold` into a **Buy** signal. Reproduced. That signal drives the order proposal, the decision log and backtest scoring. Fix: use the typed rating when the JSON block is valid, and in free text prefer the decision's own opening rating line.
2. **Lock down the dashboard's headless job** (from #806 and #1417, S). `claude -p … --allowedTools …` only pre-approves tools; it doesn't restrict them. The job runs from `$HOME` with your MCP servers loaded, eToro's `place-trade` included, and your `defaultMode` is `auto`. So D2 ("no order without approval") rests on the prompt text. WebSearch and WebFetch are also not allowed, so dashboard analyses can come back thinner than interactive ones. Fix: `--permission-mode dontAsk --strict-mcp-config`, plus the web tools in the allowlist. Add a wall-clock limit (default 180 min) so a hung job doesn't block its ticker and date for good.
3. **Benchmarks for more exchanges** (UP-036, from #1392, S). `.SW`, `.MI`, `.TW`, `.KS`, `.SI` and other European exchanges eToro sells (Madrid, Stockholm, Oslo, …) fall back to SPY, so their alpha and their lessons are measured against the wrong market.
4. **Tick preflight** (from #667, S). If eToro or Yahoo is unreachable, the tick should stop before analysis and send a notification naming the cause, instead of running every instrument into DATA_UNAVAILABLE.
5. **Record what produced a run** (UP-038, from #752, S). Put the Berkshire version, models, analysts and debate rounds in the `complete_report.md` header. The state holds only model aliases today.

## Upstream changes (v0.5.2 development branch)

- **UP-035, carry the PM's typed rating through the run (#1383), candidate.** Upstream stops re-parsing its own structured decision: the typed rating is the state's rating, and the text parser runs only for free-text answers. The parser now takes the first rating line that opens the decision, not a rating quoted in a list, table, quote or sentence, and "rating" has to start a word (so "Operating margin: Sell-side" doesn't count). Berkshire has both bugs: `pipeline.py:436` and `memory.py:29` parse the rendered text, and `decisions.extract_rating` takes the last label anywhere. All four of upstream's new test cases return the wrong rating in Berkshire. REQ-OUT-04 currently *specifies* "prefers the last labelled `Rating:` line", so it needs amending.
- **UP-036, benchmarks for Taiwan, Korea, Singapore, Switzerland and Milan (#1392), candidate.** It's a config map extension. Berkshire's map is missing the same suffixes. eToro offers Swiss, Italian, Spanish and Nordic shares, which currently score against SPY.
- **UP-037, a Yahoo rate limit reported as a rate limit (#1387), adapted.** Upstream moves from `yf.download` (which swallows the error into an empty frame, read as "no data") to `Ticker.history`. Berkshire already uses `Ticker.history` with bounded backoff, and an exhausted limit reaches the CLI's catch-all as DATA_UNAVAILABLE. The fundamentals `.info` call has no retry, but it still fails as DATA_UNAVAILABLE, not NO_DATA.
- **UP-038, run provenance in the report and state log (#752), candidate.** Berkshire's report header has the date and signal but not the version, models or analysts. Small, and it closes the gap REQ-BT-05 left open (which model generation produced a backtest cell).
- **UP-039 (parallel analysts, #1255), UP-040 (non-interactive flags, #1127/#1133) and UP-041 (atomic cache writes)** are already in Berkshire: REQ-FLOW-02, REQ-IF-02 and REQ-DATA-12.
- **UP-042, FRED change dates (#1397), declined.** Berkshire has no FRED tool; web figures carry their own dates.
- **UP-043 to UP-046, not applicable:** internal refactors and renames, Docker, a DeepSeek model flag, test-only hygiene.

## Pull requests

| PR | Title | Verdict | Status | Effort | Rationale | Report |
|---|---|---|---|---|---|---|
| #806 | Route through Claude Code and Codex CLIs | adapt | candidate | S | The provider itself is moot for Berkshire, but it exposes a gap: the dashboard's `claude -p` boundary depends on your permission mode, loads the eToro MCP and lacks the web tools. Add `dontAsk` and `--strict-mcp-config`. | [pr-806](pr-806.md) |
| #1417 | Configurable LLM request timeout | adapt | candidate | S | Claude Code already has a per-request timeout (`API_TIMEOUT_MS`). The idea belongs one level up: a dashboard job has no wall-clock limit, and a hung one blocks restarts of its ticker and date. | [pr-1417](pr-1417.md) |
| #667 | Ollama diagnostic check | adapt | candidate | S | The Ollama part is irrelevant. Take the preflight inside the tick: a Yahoo probe in `universe`, and abort with a notification when eToro or Yahoo is down. No doctor command. | [pr-667](pr-667.md) |
| #812 | Subscription CLI providers | decline | declined | S | Provider plumbing. Its `bind_tools` returns self, so analysts silently lose their tools. #806 is the fuller take. | [pr-812](pr-812.md) |
| #1136 | Anthropic prompt caching and token buffer | decline | declined | S | Caching was already declined (#1281). The token "floor" lowers `max_tokens` from 128k to 8–24k, which makes truncation worse, and the PR's own test fails. | [pr-1136](pr-1136.md) |
| #1195 | openai_codex provider | decline | declined | L | OpenAI-only provider on an undocumented endpoint, which the maintainer won't ship. Conflicts with D1. | [pr-1195](pr-1195.md) |
| #1422 | LangGraph InjectedState compatibility | decline | declined | S | LangGraph import plumbing. The fallback leaves `trade_date` empty, which silently turns off upstream's look-ahead clamp. | [pr-1422](pr-1422.md) |
| #1423 | Polish CLI dashboard | decline | declined | S | A Rich-panel restyle. Its team-only progress drops per-agent status, which Berkshire's views keep (REQ-UI-05). | [pr-1423](pr-1423.md) |
| #1424 | "Aditya's dev" | decline | declined | S | Fork dump: a truncated `cli/run.py` is a SyntaxError. Its unauthenticated `/ws/run` accepts a client `backend_url`, so any web page can exfiltrate the API key. | [pr-1424](pr-1424.md) |
| #941 | CONTRIBUTING.md | decline | declined | S | A generic guide with errors. Berkshire's REQ/TST traceability and CI already enforce the same. | [pr-941](pr-941.md) |
| #1067, #1109 | AKShare A-share vendors | decline | declined | – | Same problem as #1426 and #1183 (first run): eToro doesn't sell mainland A-shares. | [pr-1426](pr-1426.md) |
| #878 | Provider prompt caching across agents | decline | declined | – | Covered by the #1281 verdict: Berkshire already splits the static persona from the changing context. | [2026-09-26/pr-1281](../2026-09-26/pr-1281.md) |

## Recommended Berkshire changes

1. **Typed rating (UP-035).**
   - `pipeline.py`: set `signal` from the validated `pm_decision["rating"]` when the JSON block parsed, and parse the text only for free text.
   - `memory.store`: take the rating as an argument instead of re-parsing.
   - `decisions.extract_rating`: prefer the first rating line that opens a line, and require "rating" to start a word.
   - Amend REQ-OUT-04, and add upstream's quoted-rating cases to the TST-OUT tests.
   - It interacts with UP-038, which prints the signal in the header.
2. **Headless job boundary and limit (#806, #1417).**
   - `server.py`: `argv` gains `--permission-mode dontAsk --strict-mcp-config`, and `WebSearch WebFetch` in the allowlist.
   - `Api.job()` kills a running job older than `job_timeout_minutes` (new config key, default 180) through the REQ-UI-13 stop path, and reports it as timed out.
   - Amend REQ-UI-06 and add REQ-UI-14. Extend TST-UI-07 and add a timeout test.
   - Check by hand once that `--strict-mcp-config` also drops claude.ai connectors. If it doesn't, add `--disallowedTools` for eToro.
3. **Benchmarks (UP-036).**
   - Extend `config.benchmark_map`: `.SW ^SSMI`, `.MI FTSEMIB.MI`, `.TW`/`.TWO ^TWII`, `.KS ^KS11`, `.KQ ^KQ11`, `.SI ^STI`, and the eToro European venues (`.MC ^IBEX`, `.ST ^OMX`, `.OL OSEBX.OL`, `.CO ^OMXC25`, `.HE ^OMXH25`, `.BR ^BFX`, `.LS PSI20.LS`, `.VI ^ATX`, `.IR ^ISEQ`). Check each index symbol on Yahoo first.
   - Extend the TST-MEM benchmark test.
   - Open question: how eToro names Zurich and Amsterdam listings (for example `.ZU` or `.NV` rather than Yahoo's `.SW` and `.AS`). If eToro differs, `yf_symbol` has to translate them first.
4. **Tick preflight (#667).**
   - `berkshire universe` reports `yahoo_reachable`.
   - `skills/tick`: abort and notify when eToro or Yahoo is down.
   - Add REQ-SCHED-06 and amend REQ-SCHED-01 (notify on abort too).
5. **Provenance (UP-038).** Add a header line in `write_report_tree` (version, deep and quick models, analysts, rounds, horizon), and the same dict in the state log. Extend TST-RPT-01.

These are independent, apart from the note in 1 about UP-038.

## Deferred

Five PRs, all LLM-provider, launcher or docs plumbing with no transferable idea visible from the title and files: #731 (GitHub Copilot), #1003 (Windows launcher), #1121 (MiMo), #1149 (Ollama Modelfile docs), #1418 (Meta Muse Spark).
