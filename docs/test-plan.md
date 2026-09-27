# Berkshire — test plan

Covers every requirement in [requirements.md](requirements.md). Test ids are
`TST-<AREA>-<NN>`. Every automated test function starts its docstring with
`TST-…: title [REQ-…, …]`, and `tests/test_traceability.py` (TST-SAFE-04) fails the build when:

* a requirement is not covered by any test in the table below,
* a table row names an unknown requirement,
* an automated (T/I) row has no test function, or the function's REQ links differ from the row,
* a test function's id is missing from this table, or
* the REQ → TST matrix at the end differs from the table.

## 1. Strategy

| Level | What | How | Where |
|---|---|---|---|
| **Unit (T)** | Deterministic engine logic: rating parser, schemas, coercion, decision log, settlement maths, indicators, date clamping, risk gate, queue, config, eToro adapters | pytest, table-driven (`parametrize`), boundary values | `tests/test_decisions.py`, `test_memory.py`, `test_data.py`, `test_orders.py`, `test_etoro.py`, `test_cli.py` |
| **Component (T)** | The whole graph engine without LLMs: routing, context assembly, structured-output folding, checkpointing, reports | A **canned-agent driver** (`conftest.run_all`) plays each role with fixed outputs and submits them exactly as the plugin does | `tests/test_pipeline.py`, `test_cli.py::test_cli_end_to_end` |
| **Inspection (I)** | Plugin artefacts: 13 role subagents, persona directives, tool boundaries, execution guardrails in the skills | pytest over the markdown and frontmatter | `tests/test_plugin.py` |
| **Traceability (T)** | REQ ↔ TST consistency | pytest parses both docs and all test docstrings | `tests/test_traceability.py` |
| **Views (T)** | The API server (guard, routes, SSE, jobs), the client, the Textual TUI (driven by Textual's pilot against a real server thread), and the web view's pure modules | pytest; `node --test` | `tests/test_server.py`, `test_tui.py`, `webui/test/web.test.js` |
| **Upstream ledger (T)** | The ledger in `docs/upstream.md`: fixed statuses, requirement ids that exist, the PR worklist, and the skill's ordering rules | pytest over the ledger and `tools/upstream.py` | `tests/test_upstream.py` |
| **CI config (I)** | The workflow, lint rules and coverage floor | pytest over the parsed YAML/TOML | `tests/test_ci.py` |
| **Manual (D)** | Behaviour that depends on live LLM agents, the Claude Code UI, or the eToro account | Documented procedures (§4), run against the **eToro demo account** | this document |

### Test environment

* **Offline and deterministic.** `conftest.py` pins "today" to 2026-09-24, isolates
  `BERKSHIRE_HOME` in a tmp dir, clears `BERKSHIRE_*` env vars, and replaces
  `yfinance.Ticker` with `FakeTicker` (a synthetic linear uptrend of 400 business
  days ending 2026-09-18, fixed statements, insider rows and news). No network, no LLM, no eToro.
* **Run:** `uv run --all-extras pytest` (about 8 s) and `cd webui && npm test`. Live smoke run: `bin/berkshire data --run <run> snapshot NVDA`.

### Design techniques used

* **Equivalence classes and boundaries.** Date formats (canonical, non-padded, impossible, future,
  today). Filing lag at exactly period end + 45 days. Stops above, at and below the ask. Sentiment
  score just outside 0–10. Every sizing cap made binding in turn.
* **Decision tables.** Rating × holding (held or flat) → intent kind for the risk gate. Queue state transitions.
* **State-transition testing.** Pipeline step order under 1/2/3 debate rounds and 1/2 risk rounds.
  Checkpoint resume vs. fresh start vs. skip-if-complete.
* **Negative testing.** Out-of-order submit, unknown analysts or indicators, path traversal,
  malformed JSON, failing vendors, invalid config.
* **Oracle by hand computation.** Indicator values on a linear series (SMA/VWMA = mean,
  ATR = high−low = 2, RSI = 0 on a monotone downtrend); settlement returns on an explicit series.
* **Mutation sanity.** Each guard (clamp, filing lag, not-due check, supersede, idempotent
  enqueue) was confirmed to fail its test when disabled during development.

## 2. Test cases

Type: T = automated test, I = automated inspection, D = manual demonstration.

| TST id | Title | Covers | Type | Design |
|---|---|---|---|---|
| TST-ROLE-01 | One valid subagent per TradingAgents role plus the Reflector | REQ-ROLE-01 | I | Glob `agents/*.md` = the 13 expected names; frontmatter name/description/model valid; DONE protocol present; plugin.json name. |
| TST-ROLE-02 | Judges get the deep model, all other roles the quick model | REQ-ROLE-02 | T | Run with deep=fable, quick=haiku; collect each step's `model`; only research_manager/portfolio_manager get fable. |
| TST-ROLE-03 | Analysts get their TradingAgents data sources | REQ-ROLE-03 | I | Tool sets per analyst; each analyst persona names its data tools (market: stock/indicators/snapshot; fundamentals: statements+insider; news: global_news/FRED/Polymarket; sentiment: StockTwits/Reddit). |
| TST-ROLE-04 | Researchers, debaters, managers and Trader have only Read/Write | REQ-ROLE-04 | I | For 9 decision roles: tools ⊆ {Read, Write}. |
| TST-ROLE-05 | Each persona keeps the TradingAgents prompt's substantive directives | REQ-ROLE-05 | I | Parametrised phrase table per role (focus points, stances, anti-Hold rule, absolute price levels, JSON field names, markdown table). |
| TST-ROLE-07 | Every analyst treats NO_DATA_AVAILABLE / DATA_UNAVAILABLE output as missing data, not a finding | REQ-DATA-06, REQ-ROLE-05 | I | The four analyst personas name both markers; the three data-tool personas forbid numeric claims and gap-filling. |
| TST-ROLE-06 | Market Analyst picks up to 8 indicators from the full catalogue | REQ-ROLE-06 | I | Persona lists every name in `data.INDICATORS` and the "up to 8" rule. |
| TST-ROLE-08 | The Sentiment Analyst queries Bluesky within the run's window, labels engagement as current, and an empty feed never lowers confidence | REQ-ROLE-03, REQ-DATA-07 | I | Persona text: endpoint with `%24` cashtag and since/until, current-engagement caveat, confidence rule; no Mastodon or Fear & Greed. |
| TST-ROLE-09 | For a fund, the Fundamentals Analyst uses etf_profile instead of company tools and never infers undisclosed concentration | REQ-ROLE-03, REQ-FLOW-10 | I | Persona text for the fund branch. |
| TST-ROLE-10 | The Sentiment Analyst drops off-topic social posts and reports on-topic and stance counts per source | REQ-ROLE-03 | I | Persona text: off-topic cases (list, spam, shared symbol), four stance classes incl. untagged posts, the count line, ratios and confidence on on-topic posts, StockTwits tag split kept separate. |
| TST-ROLE-11 | For an index, commodity or currency pair, the Fundamentals Analyst researches macro drivers on the web instead of calling company tools | REQ-ROLE-03, REQ-FLOW-11 | I | Persona: WebSearch/WebFetch tools, the no-company-tools rule, per-mode drivers, point-in-time rule; the trigger phrase matches the engine's context. |
| TST-ROLE-12 | Every analyst with data or web tools declares a turn bound, and the pipeline loop treats a stop without output as a failed step | REQ-ROLE-07, REQ-SCHED-05 | I | Agents whose tools include Bash, WebSearch or WebFetch have a positive integer `maxTurns`; decision roles have none; `pipeline-loop.md` names the turn limit in its failure rule. |
| TST-ROLE-13 | The News and Sentiment Analysts count a syndicated story once, not as independent confirmation | REQ-ROLE-03 | I | Both personas name wire copies and aggregators, and that repetition is not independent confirmation. |
| TST-FLOW-01 | A full run visits the teams in TradingAgents order | REQ-FLOW-01 | T | Canned run, default config; flattened step trace equals the expected 12-step sequence. |
| TST-FLOW-02 | Selected analysts are offered as one parallel batch; debate waits for all | REQ-FLOW-02 | T | First `next_steps` = 4 analysts; after 3 submits only the 4th is due. |
| TST-FLOW-03 | Bull opens and the debate alternates for 2 x rounds turns | REQ-FLOW-03 | T | Parametrised rounds 1/2/3; debate trace = bull_1, bear_2, … (2R entries). |
| TST-FLOW-04 | Risk debate rotates Aggressive, Conservative, Neutral for 3 x rounds turns | REQ-FLOW-04 | T | Parametrised rounds 1/2; speaker sequence = [A, C, N] × R. |
| TST-FLOW-05 | Unknown or empty analyst selections are rejected; order is canonical | REQ-FLOW-05 | T | Negative: unknown name, blank; positive: reorders to canonical order. |
| TST-FLOW-06 | Crypto drops the fundamentals analyst and is framed as an asset | REQ-FLOW-06 | T | BTC-USD run: asset_type crypto, no fundamentals, crypto sentence in context; fundamentals-only selection rejected. |
| TST-FLOW-07 | Depth maps to 1/3/5 rounds; explicit flags and env vars win | REQ-FLOW-07 | T | `depth_overrides` for shallow/medium/deep; flag override; env var suppresses depth for its key. |
| TST-FLOW-08 | Same persisted state -> same next step, across a reload | REQ-FLOW-08 | T | Submit 5 steps, reload state.json, compare `next_steps`. |
| TST-FLOW-09 | Submitting a step that is not due raises and leaves state unchanged | REQ-FLOW-09 | T | Submit `trader` first and an empty output; state on disk byte-identical. |
| TST-FLOW-10 | The shared loop dispatches due steps in parallel and submits each | REQ-FLOW-02, REQ-FLOW-08 | I | pipeline-loop.md requires one message for all due steps, submit per step, engine-owned order; all three skills reference it. |
| TST-FLOW-12 | A fund is detected from quoteType (or --asset-type etf), keeps its fund analyst, and its debates use fund wording and ETF risk axes | REQ-FLOW-10 | T | GLD-shaped identity through a full canned run; bull and risk prompts; the Trader and a stock run get no ETF axes. |
| TST-FLOW-13 | Indices, commodities and currency pairs are detected, keep the Fundamentals Analyst, and their debates use the right noun, the macro drivers report and their own risk axes | REQ-FLOW-11 | T | ^GSPC/INDEX, GC=F/FUTURE, EURUSD=X/CURRENCY, DX-Y.NYB known only by quoteType, and BZ=F and ^GDAXI without identity; full run: bull noun and label, mode axes (not ETF's) for the three risk debaters only, macro context in the analyst prompt. |
| TST-CTX-01 | Resolved identity + exact-ticker rule reach every prompt; past-date caveat; fail-open | REQ-CTX-01 | T | All 12 prompts contain `` `NVDA` `` and the company; caveat only for past dates; empty identity → ticker-only. |
| TST-CTX-02 | A report from an unselected analyst is an explicit 'not available' marker | REQ-CTX-02 | T | Market-only run; bull prompt contains the absent markers for news/fundamentals. |
| TST-CTX-03 | First speakers get an opening marker instead of an empty opponent argument | REQ-CTX-03 | T | bull_1 and aggressive_1 prompts contain opening markers. |
| TST-CTX-04 | Position held, flat book and not-provided render differently | REQ-CTX-04 | T | Three renderings compared; default run carries "not provided". |
| TST-CTX-05 | The Trader prompt carries the market report and grounding rule only when present | REQ-CTX-05 | T | With/without market analyst. |
| TST-CTX-06 | Past-decision lessons appear in the Portfolio Manager prompt only | REQ-CTX-06 | T | Inject marker into past_context; only the PM prompt contains it. |
| TST-CTX-07 | Non-English output language reaches every report-producing prompt | REQ-CTX-07 | T | German run; every prompt carries the instruction; English adds nothing. |
| TST-CTX-08 | An identity lookup error does not fail the run | REQ-CTX-01 | T | yfinance raises; init succeeds with ticker-only context. |
| TST-CTX-09 | A historical run only sees lessons resolved by its trade date; a live run sees all | REQ-MEM-05, REQ-CTX-06 | T | One lesson resolved before and one after the trade date; historical vs live init. |
| TST-CTX-10 | Every prompt states the scoring horizon from holding_period_days; the horizon is part of the run signature | REQ-CTX-08, REQ-MEM-03 | T | A 7-day horizon reaches all 12 prompts with the date; the signature changes with the horizon; a pre-horizon state falls back to 5 days. |
| TST-CTX-11 | Fund identity reads as a fund, with its category; leveraged/inverse funds carry the daily-reset warning | REQ-FLOW-10, REQ-CTX-01 | T | Plain, leveraged and inverse fund categories; a stock with a category is unaffected. |
| TST-CTX-12 | Index, commodity and currency identity read as such, with roll, tracking and direction caveats; an explicit --asset-type wins | REQ-FLOW-11, REQ-CTX-01 | T | Context strings per mode; `Name:` not `Company:`; a stock carries none of the macro wording. |
| TST-OUT-01 | Each schema validates its JSON and renders the TradingAgents headers | REQ-OUT-01 | T | Research plan, trader proposal (absent fields "not provided", FINAL TRANSACTION PROPOSAL line), PM decision. |
| TST-OUT-02 | With several JSON blocks the last one is used | REQ-OUT-01 | T | Draft + final block. |
| TST-OUT-03 | Missing, malformed or invalid JSON falls back to free text with an error | REQ-OUT-02 | T | Three negative inputs (none, broken JSON, enum violation). |
| TST-OUT-04 | Prices coerce; placeholders, percentages, ranges and hedges become null | REQ-OUT-03 | T | 12-row equivalence-class table. |
| TST-OUT-05 | Rating parser: the decision's own rating line, not a quoted one; legend skipped; bare word only if unique | REQ-OUT-04, REQ-OUT-05 | T | 15-row table incl. fullwidth colon, legend, two disagreeing rating lines → none, a label in prose, ratings quoted in a sentence, list, table and quote (TradingAgents #1383), "Operating margin: Sell-side", "Buyers/holding". |
| TST-OUT-11 | The Portfolio Manager's typed rating is the run signal and the logged rating; a rating its text quotes never replaces it | REQ-OUT-04 | T | Canned run: PM JSON Hold with "Street consensus rating: Buy" in the thesis → signal Hold, memory log Hold. |
| TST-OUT-06 | Sentiment score bounded 0-10; band and confidence restricted | REQ-OUT-06 | T | Out-of-range score, unknown band/confidence, N/A score; case-normalised valid payload. |
| TST-OUT-07 | Structured outputs render to TradingAgents markdown and the signal is parsed | REQ-OUT-01, REQ-OUT-04 | T | Full canned run: signal Buy, rendered headers, "$290.00" stop coerced, no warnings. |
| TST-OUT-08 | A final decision without a rating yields REVIEW and is logged as REVIEW | REQ-OUT-05, REQ-OUT-02 | T | PM emits prose without rating/JSON; signal and log tag REVIEW; warning recorded. |
| TST-OUT-09 | Risk/reward is computed only from correctly ordered levels; inverted or missing levels are named, never abs()-ed | REQ-OUT-07 | T | Ten cases: valid Buy and Sell, stop and target inverted in both directions, zero risk, a missing target, entry or stop, and Hold. |
| TST-OUT-10 | TraderProposal accepts target_price like the other levels and renders the engine's R/R line | REQ-OUT-01, REQ-OUT-03, REQ-OUT-07 | T | "$100" and "130.0" are coerced; a percentage target becomes null and R/R says why. |
| TST-MEM-01 | A decision is appended in the TradingAgents pending format | REQ-MEM-01 | T | Exact tag/body/separator text. |
| TST-MEM-02 | A second decision for the same ticker+date is a no-op, pending or settled | REQ-MEM-02 | T | Store twice before and after settlement. |
| TST-MEM-03 | Benchmark by override/suffix/default; returns need the full window | REQ-MEM-03 | T | Suffix map, dotted US ticker → SPY, override; the default map for European and Asian venues with no suffix shadowing a longer one; hand-computed raw/alpha; short series → None. |
| TST-MEM-04 | Due entries settle with a reflection and resolved tag; not-yet-traded stay pending | REQ-MEM-03, REQ-MEM-04 | T | Three entries (due, too recent, other ticker); resolved tag format; no temp file. |
| TST-MEM-05 | 5 same-ticker + 3 cross-ticker, newest first, point-in-time filtered | REQ-MEM-05 | T | 7 same + 4 cross entries; count/order; `as_of` cut-off includes only lessons resolved by then. |
| TST-MEM-06 | Rotation drops oldest resolved entries only | REQ-MEM-06 | T | max 2, three resolved + one pending. |
| TST-MEM-07 | analyze and tick settle/reflect before starting new runs | REQ-MEM-07 | I | In both skills `berkshire settle` precedes `berkshire init`; `--apply` present. |
| TST-MEM-08 | A price-fetch failure leaves the entry pending | REQ-MEM-03 | T | Closes fetcher raises. |
| TST-MEM-09 | The Reflector is told the PM target's implied move from the same start close as the return; no target, no line | REQ-MEM-08 | T | Buy target +20%, Sell target −20%, no target; a number in the prose, a quoted `**Price Target**:` mid-thesis and a free-text decision are not targets; exact prompt line. |
| TST-DATA-01 | Requested dates and windows are clamped to the trade date | REQ-DATA-01 | T | Future/None/garbage dates; window entirely after; OHLCV rows ≤ trade date. |
| TST-DATA-02 | Snapshot uses the last row on/before the trade date, fixed indicators, <=30 closes | REQ-DATA-02 | T | Request 2026-12-31 on a 2026-09-10 run. |
| TST-DATA-03 | Indicators match hand-computed values; unknown names list the valid ones | REQ-DATA-03 | T | Hand oracles on the linear series; all 12 compute; invalid names. |
| TST-DATA-04 | Statements need period end + filing lag <= trade date; later insider rows dropped | REQ-DATA-04 | T | Boundary 09-13 vs 09-14 for a 07-31 quarter; annual none filed; insider after date dropped. |
| TST-DATA-05 | News is trimmed to the window; an unobserved window is flagged, not called empty | REQ-DATA-05 | T | Old/in-window/future items across both yfinance news shapes; gap marker when the feed starts after the window start. |
| TST-DATA-06 | Failures are marked DATA_UNAVAILABLE (keeping the cause), empty sources NO_DATA_AVAILABLE, never a traceback | REQ-DATA-06 | T | Vendor raises → DATA_UNAVAILABLE with the exception; empty price history → NO_DATA_AVAILABLE; missing args stay a plain usage error. |
| TST-DATA-11 | Every tool's nothing-to-report answer starts with NO_DATA_AVAILABLE and the do-not-fabricate directive | REQ-DATA-06 | T | Empty stubs for stock, fundamentals, statements, insider, valuation; filed-by and on-or-before cutoffs; snapshot raises NoData. |
| TST-DATA-08 | Past-dated fundamentals show identity only; today's run shows the full profile | REQ-DATA-07 | T | A profile stub with valuation, growth and 52-week fields: none appear on a past date, all appear today. |
| TST-DATA-09 | Valuation uses the close on the date, 4 filed quarters of EPS and the newest filed balance sheet | REQ-DATA-08 | T | Yahoo-shaped statements; an unfiled quarter is excluded from TTM; P/E, market cap and P/B by hand. |
| TST-DATA-10 | Annual EPS when <4 quarters are filed; losses, negative equity, stale and mismatched inputs are explicit | REQ-DATA-08 | T | Annual fallback label; n/m for losses and negative equity; > 400-day input unavailable; a 10× EPS basis mismatch withholds P/E; 3 filed quarters use the annual EPS (no partial TTM); 4 stale quarters give no EPS; no close. |
| TST-DATA-12 | Earnings history uses announcements before the date only; a later result and today's consensus never leak into a past run | REQ-DATA-09 | T | Calendar stub with an event 2 trading days after the date whose result exists now; history cut, horizon flag, limit covers back-dates. |
| TST-DATA-13 | Same-day runs show consensus; the horizon flag follows holding_period_days; no calendar is NO_DATA_AVAILABLE | REQ-DATA-09, REQ-DATA-06 | T | Same-day consensus; 38 trading days counted by hand; horizon 1 vs 5; a same-day announcement is the next event; empty calendar raises NoData. |
| TST-DATA-14 | The CLI passes the run's holding_period_days to the earnings tool and marks a missing calendar | REQ-DATA-09, REQ-CTX-08 | T | Run with a 1-day horizon; `berkshire data earnings` output; empty calendar through the CLI. |
| TST-DATA-15 | etf_profile reports fees, mix, sectors and top-N concentration; undisclosed holdings and past dates are explicit | REQ-DATA-10, REQ-DATA-07 | T | SPY-, GLD- (no holdings), AGG- (cash line only) and leveraged-shaped stubs; the past-date caveat; a non-fund raises NoData. |
| TST-DATA-16 | Same-day fundamentals mark dividendYield in percent and state that the ratios are fractions | REQ-DATA-11 | T | Stub with dividendYield 2.41 and profitMargins 0.28: `2.41%`, `0.28` unchanged, units note; no dividendYield gives no row; past dates carry no units note. |
| TST-DATA-17 | Google News is queried inside the window by company name, clamped, deduplicated against Yahoo and tagged headline-only | REQ-DATA-05, REQ-DATA-07 | T | Stubbed RSS: `after:`/`before:` one day wide of the window, `+0200` date, items before, after and undated dropped, a Yahoo duplicate removed, publisher suffix stripped, count note, Yahoo items first under the limit; name-to-query cases incl. futures contract names. |
| TST-DATA-18 | A Google News failure adds an unavailable line and never fails the tool; both sources failing is DATA_UNAVAILABLE | REQ-DATA-05, REQ-DATA-06 | T | Google timeout keeps Yahoo items; Yahoo down keeps Google items with no recent-feed gap marker; both down raise (the CLI marks DATA_UNAVAILABLE). |
| TST-DATA-19 | One run downloads a symbol's price history once; slices match an uncached fetch; out-of-range requests bypass the cache | REQ-DATA-12 | T | Counting fake: snapshot, indicators, stock and valuation through the CLI make one history call; cache file in the run dir; cache off after the command; a 2024 window fetches directly. |
| TST-DATA-20 | Yahoo rate limits are retried with bounded backoff, then reported DATA_UNAVAILABLE | REQ-DATA-12, REQ-DATA-06 | T | Two rate-limit errors then success (waits 2 s, 4 s, recorded not slept); persistent limit gives DATA_UNAVAILABLE naming YFRateLimitError after 3 tries, nothing cached. |
| TST-DATA-07 | Profile data and analyst prompts are labelled non-point-in-time for past dates | REQ-DATA-07 | T | Fundamentals note past vs today; analyst prompt point-in-time rule. |
| TST-IF-01 | Interactive analyze walks the TradingAgents steps with previous answers as defaults | REQ-IF-01 | D | Manual procedure M1. |
| TST-IF-02 | init/next/submit/status drive a whole run from the CLI with TradingAgents flags | REQ-IF-02, REQ-IF-08 | T | Subprocess-free CLI calls through `main()`, writing canned outputs to the files named by `next`. |
| TST-IF-03 | Trade dates must be canonical and not in the future | REQ-IF-03 | T | Boundary: tomorrow rejected, today accepted. |
| TST-IF-05 | defaults < config.json < BERKSHIRE_* env < CLI flags; bad env values fail loudly | REQ-IF-05 | T | Layered overrides; "treu" boolean. |
| TST-IF-06 | status shows every agent grouped by team with pending/in progress/done | REQ-IF-06 | T | Fresh vs complete run tables. |
| TST-IF-07 | The final result shows signal, report path and the PM decision | REQ-IF-07 | D | Manual procedure M1, step 6. |
| TST-CKPT-01 | Each submit is on disk before the next step is offered | REQ-CKPT-01, REQ-SAFE-02 | T | Reload after one submit; no `.tmp` left. |
| TST-CKPT-02 | --checkpoint resumes a same-signature run; a changed signature starts fresh | REQ-CKPT-02 | T | Resume with same analysts; different analysts → fresh. |
| TST-CKPT-03 | No --checkpoint, or a completed run, starts fresh; --skip-if-complete returns the signal | REQ-CKPT-03, REQ-SCHED-03 | T | Three init variants on the same run. |
| TST-CKPT-04 | clear-checkpoints removes incomplete runs and keeps completed ones | REQ-CKPT-04 | T | One complete + one incomplete run. |
| TST-RPT-01 | A completed run writes the TradingAgents report tree and complete_report sections I-V | REQ-RPT-01, REQ-SAFE-03 | T | 12 files + 5 section headers + disclaimer. |
| TST-RPT-02 | full_states_log_<date>.json has the TradingAgents keys | REQ-RPT-02 | T | Exact key set incl. `run_settings`. |
| TST-RPT-03 | The report header and the states log record what produced the run | REQ-RPT-03 | T | Two-analyst canned run: header line with version, models, analysts, rounds, horizon; states log `run_settings` equals the expected dict exactly. |
| TST-BT-01 | Grid stops at today; plan uses an isolated home under backtest/ | REQ-BT-01 | T | Grid past today truncated; invalid grids; plan home; unsafe run id. |
| TST-BT-02 | Cells already in the backtest log are skipped | REQ-BT-02 | T | One logged cell of four. |
| TST-BT-03 | Summary counts resolved/pending/unscored and scores hit rate and mean alpha per rating | REQ-BT-03 | T | Hand-computed per-rating stats; Hold has no hit rate; render text. |
| TST-BT-04 | Runs under a backtest home are refused by enqueue | REQ-BT-04 | T | Intent file under backtest home → skipped. |
| TST-BT-05 | Backtest summaries carry the model look-ahead caveat, and the skill flags cells before the model's cutoff | REQ-BT-05 | T | `summarize()` has `caveat`; `render()` ends with it; `/api/backtests` passes it; the dashboard shows it; skill text names the knowledge cutoff. |
| TST-RISK-01 | Buy -> full target, Overweight -> half, Underweight -> close half, Sell -> close all, Hold/REVIEW -> none | REQ-RISK-01 | T | Decision table rating × held/flat. |
| TST-RISK-02 | Amount is the smallest of target gap, order cap, instrument cap and cash floor | REQ-RISK-02 | T | Each cap made binding in turn (4 parametrised cases). |
| TST-RISK-03 | Tiny amounts, unknown equity or no ask produce no order | REQ-RISK-02 | T | Negative inputs. |
| TST-RISK-04 | Stop = valid Trader stop, else ask - k*ATR, else veto | REQ-RISK-03 | T | Stop below/above ask; custom multiple; no ATR; stop ≤ 0. |
| TST-RISK-05 | Every opening intent is a leverage-1 buy; no rating produces a short | REQ-RISK-04 | T | All ratings on a flat instrument. |
| TST-RISK-06 | Take-profit is the PM price target only when above the ask | REQ-RISK-05 | T | Target above/below ask. |
| TST-RISK-07 | Queue takes at most max_orders, closes first, then strongest opens | REQ-RISK-06 | T | 4 intents, cap 3. |
| TST-RISK-08 | Close intents only target direct positions (mirrors excluded upstream) | REQ-RISK-07 | T | Summary with a mirror position row. |
| TST-RISK-09 | Limits are validated; defaults match the agreed conservative set | REQ-RISK-08 | T | Six invalid values; default tuple. |
| TST-RISK-10 | The gate result (intent or veto + reasons) is written to the run dir | REQ-RISK-09 | T | CLI `gate` with quote and book files; orders.json content. |
| TST-RISK-11 | An open with a take-profit records its reward/risk from ask, stop and take-profit; without one, none | REQ-RISK-09 | T | The gate with and without a PM price target. |
| TST-EXE-01 | Opens/closes go through prepare/place tools, never execute-write | REQ-EXE-01 | I | approve names the four tools and forbids execute-write; no skill pre-approves place-*/execute-write. |
| TST-EXE-02 | place-* only after a per-order AskUserQuestion; unattended skills never place | REQ-EXE-02 | I | Text order AskUserQuestion < place-trade; tick/analyze/backtest prohibitions. |
| TST-EXE-03 | Account defaults to demo; only demo/real accepted; the gate stamps it on intents | REQ-EXE-03 | T | Default, validation (TST-RISK-09 covers "live"), intent account. |
| TST-EXE-04 | pending -> approved -> placed; invalid transitions rejected; expiry and supersede | REQ-EXE-04 | T | State-transition table incl. TTL and supersede. |
| TST-EXE-05 | pending is never re-placed; unknown retries once with the same token | REQ-EXE-05 | I | approve outcome mapping text. |
| TST-EXE-06 | The eToro portfolio summary maps to equity, cash and direct positions | REQ-EXE-06 | T | Fixture shaped like `get-my-portfolio-summary`; CLI conversion; raw summary accepted as `--portfolio`. |
| TST-EXE-07 | eToro symbols map to Yahoo symbols; unmappable ones return None | REQ-EXE-07 | T | 14-row table over asset types from the live watchlist, incl. `.ZU`, `.NV` and `.RTH` venue spellings. |
| TST-EXE-08 | The approval confirmation names the account (DEMO/REAL) | REQ-EXE-03 | I | approve text. |
| TST-EXE-09 | Demo order end-to-end through /berkshire:approve | REQ-EXE-02, REQ-EXE-03 | D | Manual procedure M2. |
| TST-EXE-10 | eToro asset type 6 (ETF) becomes the etf asset mode without a network call | REQ-FLOW-10, REQ-EXE-07 | T | asset_kind for types 5, 6 and 10; a universe with SPY and EIMI.L. |
| TST-EXE-11 | eToro forex, commodity and index types become the fx, commodity and index modes without a network call | REQ-FLOW-11, REQ-IF-04 | T | Watchlist with GOLD, EuroOIL, EURUSD, SPX500, NVDA; every eToro kind is a pipeline asset type. |
| TST-SCHED-01 | Universe = holdings then named watchlist, de-duplicated, users/unmappable skipped | REQ-SCHED-01, REQ-IF-04 | T | Fixture from the live watchlist shape (users, commodities, forex, crypto, .DE). |
| TST-SCHED-02 | universe reports trading_day=false on weekends so the tick only settles | REQ-SCHED-02 | T | Fri/Sat/Sun. |
| TST-SCHED-03 | A run's intent is queued once; a repeated tick does not double-order | REQ-SCHED-03 | T | Enqueue the same run twice. |
| TST-SCHED-04 | max_tickers_per_tick caps the universe, holdings first | REQ-SCHED-04 | T | Cap 2. |
| TST-SCHED-05 | /loop tick on the demo account, with one failing instrument | REQ-SCHED-01, REQ-SCHED-05 | D | Manual procedure M3. |
| TST-SCHED-06 | universe reports whether Yahoo is reachable, and the tick stops before analysis with a notification when eToro or Yahoo is down | REQ-SCHED-06 | T | Probe None → yahoo_reachable false; True or False (no bars) → true; tick skill names both abort causes, settles first, and notifies. |
| TST-SAFE-01 | Suffixes survive; path-escaping tickers and run ids are rejected | REQ-SAFE-01, REQ-IF-04 | T | 9-row table. |
| TST-SAFE-02 | atomic_write replaces the file via rename, leaving no temp file | REQ-SAFE-02 | T | Two writes, directory listing. |
| TST-UI-01 | `berkshire web` starts a real server when none runs, and reuses it next time | REQ-UI-11, REQ-UI-01 | T | Subprocess with an isolated home: two calls return the same URL/pid; SIGTERM removes the registry. |
| TST-UI-02 | API needs loopback Host, X-WebUI and the token; no CORS | REQ-UI-02 | T | Truth table for `host_ok` / `authorized` (IPv4, IPv6, foreign host, missing/stale token, empty server token). |
| TST-UI-03 | Unauthenticated, cross-origin and rebinding requests get 403; page is ungated | REQ-UI-02 | T | Real socket: no headers, stale token, foreign Host, OPTIONS preflight, POST without guard; no Access-Control headers anywhere. |
| TST-UI-04 | The registry holds port, token and pid with 0600 permissions | REQ-UI-01, REQ-UI-02 | T | Stat the registry file; URL format. |
| TST-UI-05 | Runs list with progress summary; run detail with floor, sections, timeline, orders | REQ-UI-03, REQ-UI-05 | T | One complete + one partial run; detail payload; 404 and path-traversal inputs. |
| TST-UI-06 | Decision log, order queue and backtest summaries are exposed read-only | REQ-UI-03, REQ-UI-07 | T | Seed log/queue/backtest dir; every order-writing POST path is 404. |
| TST-UI-07 | POST /api/jobs validates input and spawns a headless /berkshire:analyze with an explicit boundary | REQ-UI-06 | T | Fake spawner records argv: `--permission-mode dontAsk`, `--strict-mcp-config`, web tools allowed, no `mcp__` or order tool; four invalid inputs rejected before any spawn; exit code → status. |
| TST-UI-08 | Snapshots detect new runs, submitted steps, log and queue changes | REQ-UI-04 | T | Pure `changed()` over snapshots before/after init, submit (mtime bumped), removal. |
| TST-UI-09 | /api/events sends hello, then a change event when a run appears | REQ-UI-04 | T | Real SSE stream via the client, 50 ms poll. |
| TST-UI-10 | Static files resolve inside dist only; traversal falls back to index.html | REQ-UI-02 | T | Plain, encoded and nested `..` paths. |
| TST-UI-11 | Without a built bundle the page explains how to build it or use the TUI | REQ-UI-10 | T | Server with a missing dist. |
| TST-UI-12 | The client finds the server via the registry and reads/writes through the API | REQ-UI-01 | T | discover() on live and dead-pid registries; ApiError carries the status. |
| TST-UI-13 | TUI lists runs and shows team progress, signal and the latest report | REQ-UI-08, REQ-UI-03 | T | Textual pilot against a real server thread; 12 progress rows; `r` refresh. |
| TST-UI-14 | A run created while the TUI is open appears through the SSE stream | REQ-UI-04, REQ-UI-08 | T | Start empty, create a run, wait for the SSE-driven refresh. |
| TST-UI-15 | 'n' opens the form and submitting starts a job through the API | REQ-UI-06, REQ-UI-08 | T | Pilot presses `n`, fills the ticker, clicks Start; spawner saw the analyze command. |
| TST-UI-16 | Without textual, `berkshire tui` explains the extra instead of a traceback | REQ-UI-09 | T | Import of textual forced to fail (and genuinely absent in the CI core job); exit code 3. |
| TST-UI-17 | /berkshire:dashboard starts the server, gives the URL and TUI command, and says orders stay in Claude | REQ-UI-12 | I | Skill text and allowed-tools. |
| TST-UI-18 | Both views say orders are placed only with /berkshire:approve | REQ-UI-07 | I | App.jsx and tui.py text. |
| TST-UI-19 | Server and client import no order-placing code; views only read the queue | REQ-UI-01, REQ-UI-07 | I | Source scan for queue writes and eToro placement names. |
| TST-UI-20 | Web and terminal walkthrough during a live analysis | REQ-UI-04, REQ-UI-05, REQ-UI-08, REQ-UI-13 | D | Manual procedure M4. |
| TST-WEB-01 | Report markdown parses to blocks the reader renders, tables included | REQ-UI-05 | T | node:test over md.js with a report containing every block type. |
| TST-WEB-02 | Inline markup becomes runs, never HTML; tags stay literal text | REQ-UI-05, REQ-UI-02 | T | Script/img injection strings stay text. |
| TST-WEB-03 | The SSE parser handles split chunks, comments and multi-event buffers | REQ-UI-04 | T | Event split across two chunks; keep-alive comment. |
| TST-WEB-04 | The ?t= token moves to sessionStorage and leaves the address bar | REQ-UI-02 | T | Fake location/storage/history. |
| TST-CI-01 | CI runs on push and PR to main with test, core, lint, webui, secrets and sast jobs | REQ-CI-01 | I | Parse ci.yml. |
| TST-CI-02 | ruff is pinned in CI, the rule set includes bandit security checks, and the format check runs | REQ-CI-02 | I | ci.yml env + ruff.toml + `ruff format --check .` in the lint job. |
| TST-CI-03 | The test job runs every extra under branch coverage with a ratcheting floor and publishes the report | REQ-CI-03 | I | ci.yml + [tool.coverage]. Floor ≥ 89 and the step that fails when coverage is ≥ 2 points above it. |
| TST-CI-04 | gitleaks scans the full history on every push to any branch and on every PR | REQ-CI-04 | I | fetch-depth 0, pinned gitleaks binary, `gitleaks git .` with no commit range. `secrets.yml` covers pushes to branches other than main with the same version and steps. |
| TST-CI-05 | CodeQL analyses Python and JavaScript with security-extended queries | REQ-CI-05 | I | sast matrix, permissions, `upload: always`, and a gate step that fails on any unreviewed SARIF result. |
| TST-CI-06 | The core job installs no extras, asserts textual is absent and checks the tui hint | REQ-CI-06 | I | core job commands; textual only in the extra. |
| TST-CI-07 | The webui job runs npm ci, the pinned linter, the node tests and the vite build | REQ-CI-07 | I | webui job + package.json (exact Biome version, `lint` script) + biome.json (recommended + hook rules as errors) + lockfile. |
| TST-CI-08 | Read-only default permissions, versioned actions, locked installs | REQ-CI-08 | I | Every `uses:` ends in `@vN`. |
| TST-CI-09 | First push to GitHub: every job green, coverage and CodeQL results published | REQ-CI-01, REQ-CI-03, REQ-CI-04, REQ-CI-05 | D | Manual procedure M5. |
| TST-CI-10 | main is protected and secret scanning with push protection is on | REQ-CI-09 | D | Manual procedure M8. |
| TST-FLOW-11 | A stopped run offers and accepts no steps; --checkpoint resumes it | REQ-UI-13 | T | Stop after one step; next/submit/CLI `next`; resume clears the flag; a complete run cannot be stopped. |
| TST-IF-10 | eToro-only names map to Yahoo; an unlisted instrument is refused before any agent runs | REQ-IF-10 | T | EUROOIL → BZ=F with the alias kept; empty Yahoo frame refused with no run dir created; Yahoo unreachable → fail-open. |
| TST-UI-21 | POST /api/runs/T/D/stop marks the run stopped and ends only its running job | REQ-UI-13 | T | Two jobs, one matching; fake killer records calls; idempotent; 404 unknown, 400 complete. |
| TST-UI-22 | The start form maps eToro names and refuses unlisted instruments before spawning | REQ-IF-10, REQ-UI-06 | T | EuroOil spawns BZ=F; unlisted → 400 naming symbol_map, nothing spawned. |
| TST-UI-23 | 's' asks first, then stops the selected running analysis; a finished one is refused | REQ-UI-13, REQ-UI-08 | T | Pilot: cancel keeps it running, confirm stops it via the API, a stopped run gets no dialog. |
| TST-UI-24 | The pipeline loop stops dispatching when the run was stopped | REQ-UI-13 | I | pipeline-loop.md text. |
| TST-UI-25 | A second start for a (ticker, date) whose job is still running is refused | REQ-UI-06 | T | Same ticker via its eToro alias → 400 naming the job, nothing spawned; another date spawns; after the job exits a restart spawns. |
| TST-UI-26 | A dashboard job past job_timeout_minutes is ended once, its run marked stopped, and a restart is accepted | REQ-UI-14 | T | Backdated job: fake killer called once, run stopped with the timeout reason, status timed out; a fresh job untouched; restart of the same ticker/date spawns. |
| TST-UI-27 | A headless claude -p with --strict-mcp-config loads no eToro tools | REQ-UI-06 | D | Manual procedure M7. |
| TST-UP-01 | The ledger is consistent and records the v0.5.1 baseline | REQ-UP-01, REQ-UP-05 | T | `tools/upstream.py check` on the real ledger; ≥ 30 baseline rows across statuses. |
| TST-UP-02 | The ledger check rejects bad statuses, missing or unknown requirements, duplicates and bad PR rows | REQ-UP-01 | T | Eleven single mutations of the real ledger, each named in the problems. |
| TST-UP-03 | The worklist splits open PRs into new, head-moved and unchanged, and flags PRs that left the open list | REQ-UP-02 | T | Four ledger rows × three open PRs; a declined PR is not revisited. |
| TST-UP-04 | The skill reviews commits since the watermark, fans out one agent per PR, and moves the watermark last | REQ-UP-03, REQ-UP-04 | I | Skill and brief text, order of report vs watermark, AskUserQuestion before `planned`. |
| TST-UP-05 | The skill may read upstream but has no permission to push, merge, comment or edit there | REQ-UP-04 | I | allowed-tools contains only read-only git/gh commands. |
| TST-UP-06 | A full /upstream-scout run against live upstream | REQ-UP-02, REQ-UP-03, REQ-UP-04 | D | Manual procedure M6. |
| TST-SAFE-04 | Requirements, test plan and test code are mutually traceable | REQ-SAFE-04 | T | `tests/test_traceability.py`. |
| TST-SAFE-05 | Every manual procedure id is defined once, and every manual test names one that exists | REQ-SAFE-04 | T | Procedure headings in §4 unique; each D row's design cell names an M-id defined there. |
| TST-SAFE-06 | AGENTS.md links every ground-truth document and states the change discipline; CLAUDE.md forwards to it | REQ-SAFE-05 | I | Every `docs/*.md` linked; the gate commands named; CLAUDE.md names AGENTS.md. |
| TST-SAFE-07 | The design document describes every engine module | REQ-SAFE-06 | I | One module-table row per `berkshire/*.py` (except `__init__`, `__main__`), so a new module cannot go undescribed. |
| TST-SAFE-08 | The test strategy names every test file, and the README states no requirement count that can drift | REQ-SAFE-07 | T | Every `tests/test_*.py` appears in §1; no `N requirements` in the README; the README links the ledger and names `/upstream-scout`. |
| TST-SAFE-09 | Every manual procedure not yet run links its tracking issue, and AGENTS.md names the tracker and its labels | REQ-SAFE-08 | T | Results-table rows marked `not yet run` carry `#N`; AGENTS.md links the issues and names the six labels. |
| TST-SAFE-10 | The requirements state the objective, its success criteria, the non-goals and the open questions | REQ-SAFE-09 | T | The three sections precede §1, and the non-goals name the recurring out-of-scope classes. |

## 3. Entry and exit criteria

* **Entry:** `uv sync` succeeds and `claude plugin validate .` passes.
* **Exit (automated):** every CI job is green. The test job has 0 skipped and 0 xfail; the core job skips only `tests/test_tui.py`, by design.
* **Exit (release):** M1–M3 executed on the demo account and their results recorded in the table in §4.

## 4. Manual procedures

Load the plugin: `claude --plugin-dir <path-to>/berkshire`, or
`/plugin marketplace add <path-to>/berkshire` then `/plugin install berkshire@berkshire-local`.

**M1 — interactive analysis (TST-IF-01, TST-IF-07).**
1. `/berkshire:analyze` with no arguments. Expect the steps in order: ticker, date, language,
   analysts, depth, models, portfolio.
2. Choose NVDA, today, English, all analysts, Shallow, opus/sonnet, no portfolio.
3. Expect the reflector to run first if there are due decisions, then "Starting fresh".
4. Expect four analyst agents launched in one batch, then bull → bear → Research Manager → Trader →
   aggressive → conservative → neutral → Portfolio Manager, with status tables between teams.
5. Run `/berkshire:analyze` again. Every step defaults to the previous answer.
6. Final output: status table, signal (5-tier or REVIEW), path to `complete_report.md`, the PM
   decision text, and the disclaimer.

**M2 — demo order end-to-end (TST-EXE-09).**
1. Finish M1 with a Buy/Overweight signal (or use `--portfolio etoro`) and accept "queue an eToro order".
2. `/berkshire:approve`. Expect `prepare-trade` on **demo**, and the confirmation block showing the
   account, amount, stop-loss and costs.
3. Answer *Reject*. The queue item becomes `rejected` and nothing is sent.
4. Queue again, answer *Place*. Expect `place-trade` exactly once and a status of `placed` or `pending_fill`.
   Check it with `get-my-portfolio-summary account=demo`.

**M3 — scheduled tick (TST-SCHED-05).**
1. Add an instrument that cannot be analysed to the configured watchlist (e.g. a delisted ticker).
2. `/berkshire:tick` once. Expect: universe listed, settlement, one pipeline per instrument, the bad
   instrument reported as failed while the others complete, the gate table, intents queued, and a
   PushNotification. No approval prompt and no `place-*` call.
3. Re-run `/berkshire:tick` the same day. Every instrument is skipped as "already analysed today"
   and no new queue items appear.
4. `/loop 24h /berkshire:tick` is accepted and scheduled.

**M4 — web and terminal views (TST-UI-20).**
1. `/berkshire:dashboard` and open the URL. Then `berkshire tui` in a terminal.
2. Start an analysis from the web form. The Jobs view shows it running with a log tail.
3. While it runs, both views update without a reload. The floor's seats fill team by team, the
   timeline grows, and the reader opens on the latest report.
4. Check at 375 px width (the floor wraps to two columns) and with the system in dark mode.
5. The Orders view and the TUI Orders tab list the queue read-only, and point to `/berkshire:approve`.
6. Start a second analysis and stop it with **Stop analysis** (web, two clicks) or `s` (TUI). The job ends
   within seconds, the run shows Stopped with its reason, and no further agents are started.

**M5 — first CI run (TST-CI-09).**
1. Push to the GitHub `main` branch. All six jobs pass.
2. The test job's summary shows the coverage table, and the `coverage` artifact has `coverage.xml`.
3. The sast jobs publish CodeQL SARIF artifacts, and report 0 unreviewed findings. Reviewed ones are listed with reasons in
   `.github/codeql-reviewed.json`. gitleaks reports no leaks over the full history. (The Security tab needs GitHub
   Code Security on a private repository. After enabling it, switch the analyze step to `upload: always`.)

**M6 — upstream scout (TST-UP-06).**
1. `/upstream-scout --max 5`. Expect: the commits since the watermark reviewed, the worklist computed,
   five PR agents launched in one batch, and `docs/upstream-reports/<date>/README.md` plus `pr-N.md` files.
2. The ledger gains five PR rows and a moved watermark, and `tools/upstream.py check` passes.
3. Run it again at once. No PR is re-analysed (all unchanged), and the next five of the backlog are taken.
4. Choose one recommendation. Its row becomes `planned`, and nothing else in the repo changes.

**M7 — headless job boundary (TST-UI-27).** From `$HOME`, with the eToro connector enabled, run
`claude -p "Reply with only the names of your available tools that contain 'eToro', or NONE." --permission-mode dontAsk`
once without and once with `--strict-mcp-config`. Without the flag it lists the eToro tools; with it,
`NONE`. Checked on Claude Code 2.1.283, 2026-09-27.

**M8 — merge protection (TST-CI-10).** Read the settings back:
`gh api repos/caius72/berkshire/branches/main/protection` lists the seven required checks, a required pull
request, `enforce_admins.enabled: true`, and force pushes and deletion disabled. `gh api repos/caius72/berkshire`
shows `secret_scanning` and `secret_scanning_push_protection` enabled.

| Procedure | Date | Result | Notes |
|---|---|---|---|
| M1 | | not yet run | #28 |
| M2 | | not yet run | #29 |
| M3 | | not yet run | #30 |
| M4 | | not yet run | #31 |
| M6 | | not yet run | #32 |
| M5 | 2026-09-25 | pass (run 36119571904) | The first three runs failed and were fixed: a clock mismatch, the Node 22 test glob, gitleaks-action on a first push, and CodeQL upload on a private repo. Coverage 87.7%. |
| M7 | 2026-09-27 | pass | Claude Code 2.1.283: eToro tools listed without the flag, `NONE` with it. |
| M8 | 2026-09-28 | pass | Settings applied and read back when the repository was made public (#14). |

## 5. Traceability matrix (REQ → TST)

Derived from §2. `test_traceability.py` fails if this section drifts from the table.

<!-- MATRIX:BEGIN -->
| Requirement | Tests |
|---|---|
| REQ-ROLE-01 | TST-ROLE-01 |
| REQ-ROLE-02 | TST-ROLE-02 |
| REQ-ROLE-03 | TST-ROLE-03, TST-ROLE-08, TST-ROLE-09, TST-ROLE-10, TST-ROLE-11, TST-ROLE-13 |
| REQ-ROLE-04 | TST-ROLE-04 |
| REQ-ROLE-05 | TST-ROLE-05, TST-ROLE-07 |
| REQ-ROLE-06 | TST-ROLE-06 |
| REQ-ROLE-07 | TST-ROLE-12 |
| REQ-FLOW-01 | TST-FLOW-01 |
| REQ-FLOW-02 | TST-FLOW-02, TST-FLOW-10 |
| REQ-FLOW-03 | TST-FLOW-03 |
| REQ-FLOW-04 | TST-FLOW-04 |
| REQ-FLOW-05 | TST-FLOW-05 |
| REQ-FLOW-06 | TST-FLOW-06 |
| REQ-FLOW-07 | TST-FLOW-07 |
| REQ-FLOW-08 | TST-FLOW-08, TST-FLOW-10 |
| REQ-FLOW-09 | TST-FLOW-09 |
| REQ-FLOW-10 | TST-CTX-11, TST-EXE-10, TST-FLOW-12, TST-ROLE-09 |
| REQ-FLOW-11 | TST-CTX-12, TST-EXE-11, TST-FLOW-13, TST-ROLE-11 |
| REQ-CTX-01 | TST-CTX-01, TST-CTX-08, TST-CTX-11, TST-CTX-12 |
| REQ-CTX-02 | TST-CTX-02 |
| REQ-CTX-03 | TST-CTX-03 |
| REQ-CTX-04 | TST-CTX-04 |
| REQ-CTX-05 | TST-CTX-05 |
| REQ-CTX-06 | TST-CTX-06, TST-CTX-09 |
| REQ-CTX-07 | TST-CTX-07 |
| REQ-CTX-08 | TST-CTX-10, TST-DATA-14 |
| REQ-OUT-01 | TST-OUT-01, TST-OUT-02, TST-OUT-07, TST-OUT-10 |
| REQ-OUT-02 | TST-OUT-03, TST-OUT-08 |
| REQ-OUT-03 | TST-OUT-04, TST-OUT-10 |
| REQ-OUT-04 | TST-OUT-05, TST-OUT-07, TST-OUT-11 |
| REQ-OUT-05 | TST-OUT-05, TST-OUT-08 |
| REQ-OUT-06 | TST-OUT-06 |
| REQ-OUT-07 | TST-OUT-09, TST-OUT-10 |
| REQ-MEM-01 | TST-MEM-01 |
| REQ-MEM-02 | TST-MEM-02 |
| REQ-MEM-03 | TST-CTX-10, TST-MEM-03, TST-MEM-04, TST-MEM-08 |
| REQ-MEM-04 | TST-MEM-04 |
| REQ-MEM-05 | TST-CTX-09, TST-MEM-05 |
| REQ-MEM-06 | TST-MEM-06 |
| REQ-MEM-07 | TST-MEM-07 |
| REQ-MEM-08 | TST-MEM-09 |
| REQ-DATA-01 | TST-DATA-01 |
| REQ-DATA-02 | TST-DATA-02 |
| REQ-DATA-03 | TST-DATA-03 |
| REQ-DATA-04 | TST-DATA-04 |
| REQ-DATA-05 | TST-DATA-05, TST-DATA-17, TST-DATA-18 |
| REQ-DATA-06 | TST-DATA-06, TST-DATA-11, TST-DATA-13, TST-DATA-18, TST-DATA-20, TST-ROLE-07 |
| REQ-DATA-07 | TST-DATA-07, TST-DATA-08, TST-DATA-15, TST-DATA-17, TST-ROLE-08 |
| REQ-DATA-08 | TST-DATA-09, TST-DATA-10 |
| REQ-DATA-09 | TST-DATA-12, TST-DATA-13, TST-DATA-14 |
| REQ-DATA-10 | TST-DATA-15 |
| REQ-DATA-11 | TST-DATA-16 |
| REQ-DATA-12 | TST-DATA-19, TST-DATA-20 |
| REQ-IF-01 | TST-IF-01 |
| REQ-IF-02 | TST-IF-02 |
| REQ-IF-03 | TST-IF-03 |
| REQ-IF-04 | TST-EXE-11, TST-SAFE-01, TST-SCHED-01 |
| REQ-IF-05 | TST-IF-05 |
| REQ-IF-06 | TST-IF-06 |
| REQ-IF-07 | TST-IF-07 |
| REQ-IF-08 | TST-IF-02 |
| REQ-IF-10 | TST-IF-10, TST-UI-22 |
| REQ-CKPT-01 | TST-CKPT-01 |
| REQ-CKPT-02 | TST-CKPT-02 |
| REQ-CKPT-03 | TST-CKPT-03 |
| REQ-CKPT-04 | TST-CKPT-04 |
| REQ-RPT-01 | TST-RPT-01 |
| REQ-RPT-02 | TST-RPT-02 |
| REQ-RPT-03 | TST-RPT-03 |
| REQ-BT-01 | TST-BT-01 |
| REQ-BT-02 | TST-BT-02 |
| REQ-BT-03 | TST-BT-03 |
| REQ-BT-04 | TST-BT-04 |
| REQ-BT-05 | TST-BT-05 |
| REQ-RISK-01 | TST-RISK-01 |
| REQ-RISK-02 | TST-RISK-02, TST-RISK-03 |
| REQ-RISK-03 | TST-RISK-04 |
| REQ-RISK-04 | TST-RISK-05 |
| REQ-RISK-05 | TST-RISK-06 |
| REQ-RISK-06 | TST-RISK-07 |
| REQ-RISK-07 | TST-RISK-08 |
| REQ-RISK-08 | TST-RISK-09 |
| REQ-RISK-09 | TST-RISK-10, TST-RISK-11 |
| REQ-EXE-01 | TST-EXE-01 |
| REQ-EXE-02 | TST-EXE-02, TST-EXE-09 |
| REQ-EXE-03 | TST-EXE-03, TST-EXE-08, TST-EXE-09 |
| REQ-EXE-04 | TST-EXE-04 |
| REQ-EXE-05 | TST-EXE-05 |
| REQ-EXE-06 | TST-EXE-06 |
| REQ-EXE-07 | TST-EXE-07, TST-EXE-10 |
| REQ-SCHED-01 | TST-SCHED-01, TST-SCHED-05 |
| REQ-SCHED-02 | TST-SCHED-02 |
| REQ-SCHED-03 | TST-CKPT-03, TST-SCHED-03 |
| REQ-SCHED-04 | TST-SCHED-04 |
| REQ-SCHED-05 | TST-ROLE-12, TST-SCHED-05 |
| REQ-SCHED-06 | TST-SCHED-06 |
| REQ-SAFE-01 | TST-SAFE-01 |
| REQ-SAFE-02 | TST-CKPT-01, TST-SAFE-02 |
| REQ-SAFE-03 | TST-RPT-01 |
| REQ-SAFE-04 | TST-SAFE-04, TST-SAFE-05 |
| REQ-SAFE-05 | TST-SAFE-06 |
| REQ-SAFE-06 | TST-SAFE-07 |
| REQ-SAFE-07 | TST-SAFE-08 |
| REQ-SAFE-08 | TST-SAFE-09 |
| REQ-SAFE-09 | TST-SAFE-10 |
| REQ-UI-01 | TST-UI-01, TST-UI-04, TST-UI-12, TST-UI-19 |
| REQ-UI-02 | TST-UI-02, TST-UI-03, TST-UI-04, TST-UI-10, TST-WEB-02, TST-WEB-04 |
| REQ-UI-03 | TST-UI-05, TST-UI-06, TST-UI-13 |
| REQ-UI-04 | TST-UI-08, TST-UI-09, TST-UI-14, TST-UI-20, TST-WEB-03 |
| REQ-UI-05 | TST-UI-05, TST-UI-20, TST-WEB-01, TST-WEB-02 |
| REQ-UI-06 | TST-UI-07, TST-UI-15, TST-UI-22, TST-UI-25, TST-UI-27 |
| REQ-UI-07 | TST-UI-06, TST-UI-18, TST-UI-19 |
| REQ-UI-08 | TST-UI-13, TST-UI-14, TST-UI-15, TST-UI-20, TST-UI-23 |
| REQ-UI-09 | TST-UI-16 |
| REQ-UI-10 | TST-UI-11 |
| REQ-UI-11 | TST-UI-01 |
| REQ-UI-12 | TST-UI-17 |
| REQ-UI-13 | TST-FLOW-11, TST-UI-20, TST-UI-21, TST-UI-23, TST-UI-24 |
| REQ-UI-14 | TST-UI-26 |
| REQ-CI-01 | TST-CI-01, TST-CI-09 |
| REQ-CI-02 | TST-CI-02 |
| REQ-CI-03 | TST-CI-03, TST-CI-09 |
| REQ-CI-04 | TST-CI-04, TST-CI-09 |
| REQ-CI-05 | TST-CI-05, TST-CI-09 |
| REQ-CI-06 | TST-CI-06 |
| REQ-CI-07 | TST-CI-07 |
| REQ-CI-08 | TST-CI-08 |
| REQ-CI-09 | TST-CI-10 |
| REQ-UP-01 | TST-UP-01, TST-UP-02 |
| REQ-UP-02 | TST-UP-03, TST-UP-06 |
| REQ-UP-03 | TST-UP-04, TST-UP-06 |
| REQ-UP-04 | TST-UP-04, TST-UP-05, TST-UP-06 |
| REQ-UP-05 | TST-UP-01 |
<!-- MATRIX:END -->
