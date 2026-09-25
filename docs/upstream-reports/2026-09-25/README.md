# Upstream scout, 2026-09-25

TauricResearch/TradingAgents at `35543d0` (v0.5.1). First run, so every open PR was new.

## Summary

| | |
|---|---|
| Upstream commits since the watermark | 0. v0.5.1 is still `main`, so no feature rows were added. |
| Open PRs | 40, all new |
| Analysed | 10: 8 adapt, 2 decline, 0 adopt as is |
| Deferred | 30 (listed below) |

No PR is worth taking as it is. Every adapt verdict found a real bug or a look-ahead leak in the PR itself, and proposes the idea rebuilt the Berkshire way. The changes worth doing:

1. **Stop leaking today's valuation into past-dated runs.** Found via #1406. `tool_fundamentals` prints live `marketCap` and the P/E ratios (`berkshire/data.py:214`) on backtest dates, only labelled as current. Withhold them on past dates (S), then add a point-in-time valuation tool reconciled for splits (M).
2. **Tell every role the horizon it is graded on.** From #673. `holding_period_days` becomes a line in every prompt and part of the run signature (S).
3. **Say "no data" instead of inviting a guess.** From #1408. Data-tool failures carry a `NO_DATA_AVAILABLE` / `DATA_UNAVAILABLE` sentinel and a do-not-fabricate instruction, which the analysts are told to honour (S).
4. **Know when earnings are due.** From #835. A point-in-time earnings tool keyed on announcement dates (M). An optional follow-up rule would shrink or veto opens inside the earnings window.
5. **Analyse ETFs as funds.** From #819. GLD, SPY, AGG and EIMI.L on your watchlist are analysed as companies today. Add an `etf` mode and an `etf_profile` tool (M).

## Upstream changes

None. `origin/main` is unchanged since v0.5.1 (`35543d0`), with no new release and no changelog entry.

## Pull requests

| PR | Title | Verdict | Status | Effort | Rationale | Report |
|---|---|---|---|---|---|---|
| #1406 | Point-in-time valuation snapshot with split adjustment | adapt | candidate | M | Berkshire leaks live market cap and P/E into backtests. The PR's own P/E is not split-reconciled. | [pr-1406](pr-1406.md) |
| #835 | Earnings-context tool for catalyst awareness | adapt | candidate | M | A real gap. The PR leaks EPS actuals by filtering on fiscal quarter end, not the report date. Rebuild on `get_earnings_dates`. | [pr-835](pr-835.md) |
| #819 | ETF analysis with holdings, drill-down and risk guidance | adapt | candidate | M | Watchlist ETFs are analysed as companies. Add an etf mode and a current-only `etf_profile`; skip drill-down and Alpha Vantage. | [pr-819](pr-819.md) |
| #673 | `investment_horizon` configuration parameter | adapt | candidate | S | The PR is broken (a SyntaxError at `default_config.py:45`) and covers the analysts only. Derive the horizon from `holding_period_days` for every role. | [pr-673](pr-673.md) |
| #1408 | Market-data resilience, tool error shielding, doctor command | adapt | candidate | S | Take only the no-data sentinel and a do-not-fabricate line. Berkshire already never crashes on tool errors. | [pr-1408](pr-1408.md) |
| #1082 | Probability and risk/reward review on every Trader proposal | adapt | candidate | S | Compute R/R in the engine from entry, stop and target, checking the direction (the PR's `abs()` hides inverted levels). Skip the uncalibrated win probability. | [pr-1082](pr-1082.md) |
| #1087 | Calibrate lessons with a surprise ratio | adapt | candidate | S | The ratio compares a months-long target with a 5-day return, and a regex flips downside signs. Give the Reflector the target-implied move instead. | [pr-1087](pr-1087.md) |
| #922 | Bluesky, Mastodon and Fear & Greed sentiment sources | adapt | candidate | S | Take Bluesky only, through WebFetch with a since/until window (point-in-time capable). The other feeds leak look-ahead or are noise. | [pr-922](pr-922.md) |
| #1404 | Optional Jev debate gate (early stop) | decline | declined | M | It saves tokens but adds no quality. It breaks deterministic routing (REQ-FLOW-08), adds a vendor, and has an uncaught TypeError at `debate_gate.py:68`. | [pr-1404](pr-1404.md) |
| #584 | Pre-computed indicator interpretations | decline | declined | S | The verified snapshot already has deterministic indicators. The labels are uncalibrated, and the Bollinger rule is dead code (`compute.py:89`). | [pr-584](pr-584.md) |

## Recommended Berkshire changes

Several PRs proposed "REQ-DATA-08". The numbering below makes the new ids distinct.

**A. Point-in-time fundamentals** (#1406, #835 and #819 all touch `data.py`, `cli.py` and `agents/fundamentals-analyst.md`, so build them together):
- **A1** (#1406, S then M). In `tool_fundamentals`, withhold the price-derived fields (market cap, P/E, P/B, EPS, dividend yield, 52-week range) when `trade_date < today`, and amend **REQ-DATA-07** from "label" to "withhold". Then add a `valuation` tool that computes market cap, P/B and TTM P/E from the trade-date close and the filed statements, with every per-share input reconciled to one split basis through `Ticker.splits` (**REQ-DATA-08**). Tests cover a split between the EPS period and the price date, a split between the share count and the price date, stale inputs, and negative EPS or equity.
- **A2** (#835, M). An `earnings` tool built on `get_earnings_dates`. It reports the next event (an estimate, labelled current on past dates), the last 4 surprises announced by the trade date, and consensus only on same-day runs (**REQ-DATA-09**). The persona states earnings proximity. An optional **REQ-RISK-10** would halve or veto opens inside the earnings window; that changes what the ratings mean for orders (decision D6), so it is a separate decision.
- **A3** (#819, M). An `etf` asset mode, detected from `quoteType == "ETF"` or eToro asset type 6. It brings fund wording in the instrument context, a warning about daily-reset decay for leveraged and inverse ETFs, ETF risk axes for the risk debaters, and an `etf_profile` tool labelled current-only with a top-N note (**REQ-FLOW-10**, **REQ-DATA-10**, and amendments to REQ-IF-04, REQ-ROLE-03 and REQ-CTX-01).

**B. Horizon and target** (#673, #1082 and #1087 all rest on the holding window and the price target):
- **B1** (#673, S). A `horizon_instruction(holding_period_days)` line in every prompt, and the horizon in `state["config"]` and `signature()` (**REQ-CTX-08**, amend REQ-MEM-03). This comes first, because B2 and B3 refer to the stated horizon.
- **B2** (#1082, S). An optional `target_price` in TraderProposal. A **Risk/Reward** line is computed in `decisions.py` only when the levels are ordered correctly, otherwise it reads "n/a", and the gate's reasons carry R/R (amend REQ-OUT-01, REQ-OUT-03 and REQ-RISK-09).
- **B3** (#1087, S). `settle_candidates` passes `target_move` from the trade-date close to the Reflector. The reflector persona judges the move against the target and horizon (**REQ-MEM-08**). The decision-log format is unchanged.

**C. Data honesty** (#1408, S). `cmd_data` prefixes failures with `NO_DATA_AVAILABLE:` or `DATA_UNAVAILABLE:` plus a do-not-fabricate line, and all four analyst personas honour it (amend **REQ-DATA-06**). It makes A1–A3's "unavailable" paths explicit, so it fits naturally before A.

**D. Bluesky** (#922, S, low priority). A fourth sentiment source through WebFetch, with the run's since/until window. Confidence rules stay unchanged when it is empty (amend REQ-ROLE-03).

Suggested order: A1-withhold (the leak fix) → C → B1 → A2 / A3 → B2 / B3 → D.

## Deferred (30)

Not analysed this run: mostly LLM-provider plumbing (#401, #731, #806, #812, #1121, #1136, #1195), prompt caching (#878, #1281), CLI and docs (#581, #667, #813, #940, #941, #1003, #1149), A-share and other data vendors (#702, #794, #956, #1067, #1109, #1183), config knobs (#1259, #1265), and others (#302 ACE, #359 factor rules, #513 custom prompt, #1074 JSON retry, #1407 caller-supplied sentiment data, #1413 React frontend). The next `/upstream-scout` run picks them up. The next three in line: #1407 (caller-supplied sentiment data, relevant to point-in-time backtests), #513 (custom prompt) and #359 (factor rules).
