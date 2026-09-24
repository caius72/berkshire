---
name: analyze
description: Run the Berkshire multi-agent trading analysis (TradingAgents-style analyst team, bull/bear debate, trader, risk debate, portfolio manager) for one ticker and date. Interactive with no arguments. Optionally queues an eToro order for approval.
arguments: [args]
allowed-tools: Bash(berkshire *) Bash(date *) Read Agent AskUserQuestion mcp__claude_ai_eToro__get-my-portfolio-summary mcp__claude_ai_eToro__get-my-watchlists mcp__claude_ai_eToro__get-instruments-overview
---

# /berkshire:analyze

Usage mirrors the `tradingagents` CLI:

```
/berkshire:analyze                                   # interactive, previous answers as defaults
/berkshire:analyze TICKER [YYYY-MM-DD] [--analysts market,social,news,fundamentals]
                   [--depth shallow|medium|deep] [--language L]
                   [--deep-model opus] [--quick-model sonnet]
                   [--portfolio FILE|etoro] [--checkpoint] [--clear-checkpoints]
```

Arguments: `$ARGUMENTS`

## 1. Collect the run settings

If `$ARGUMENTS` names a ticker, parse the flags and skip to step 2.

Otherwise, walk the TradingAgents steps with AskUserQuestion. Load defaults with
`berkshire prefs get` and put the previous answer first in each question:

1. **Ticker.** Offer the previous ticker. The user types another via "Other". Keep exchange suffixes (`RHM.DE`, `7203.T`, `BTC-USD`).
2. **Analysis date.** Offer today (`date +%F`) and the previous date. Must be YYYY-MM-DD and not in the future.
3. **Output language.** English, or another language.
4. **Analyst team** (multiSelect): Market, Social (sentiment), News, Fundamentals.
5. **Research depth**: Shallow (1 round), Medium (3), Deep (5).
6. **Models**: deep thinker for the Research Manager and Portfolio Manager (default opus), quick thinker for everyone else (default sonnet).
7. **Portfolio context**: none, eToro (configured account), or a JSON file.

Save the answers: `berkshire prefs set '<json>'`.

## 2. Prepare

- `--clear-checkpoints`: run `berkshire clear-checkpoints` first.
- `--portfolio etoro`: call `get-my-portfolio-summary` with `account` = `berkshire config` → `account` and
  `includePositions: true`. Write the raw JSON to `~/.berkshire/tmp/etoro_summary.json`, then run
  `berkshire etoro-portfolio ~/.berkshire/tmp/etoro_summary.json --out ~/.berkshire/tmp/portfolio.json`
  and pass `--portfolio ~/.berkshire/tmp/portfolio.json`.
- **Settle past decisions first** (the learning loop): run `berkshire settle TICKER`. For each item in
  `to_reflect`, launch the `berkshire:reflector` agent (in parallel) with its prompt and output file,
  then run `berkshire settle --apply`.

## 3. Run

`berkshire init TICKER DATE [flags]` returns `run_dir`, and `resumed` if a checkpoint was picked up.
Say "Resuming the saved run" or "Starting fresh". Then follow
`${CLAUDE_PLUGIN_ROOT}/skills/analyze/pipeline-loop.md` (read it now) with `RUN = run_dir`.

## 4. Present the result

- Show `berkshire status RUN`, the **signal**, and the path to `complete_report.md`.
- Read `RUN/reports/5_portfolio/decision.md` and show it. Offer the full report (Read `complete_report.md`) on request.
- A `REVIEW` signal means no rating could be parsed. Say it needs a human look, and never treat it as Hold.
- Mention any `warnings`.
- End with the disclaimer: research output, not financial advice.

## 5. Optional: queue an eToro order

Ask whether to turn the decision into an eToro order proposal. If yes:
1. Call `get-instruments-overview` with the symbol and write the JSON to `RUN/quote.json`.
   With an eToro portfolio file from step 2, pass it as `--portfolio-file`.
2. `berkshire gate RUN --quote-file RUN/quote.json [--portfolio-file …]` shows the intent or veto with its reasons.
3. If there is an intent: `berkshire enqueue RUN --tag analyze-<date>`, then tell the user to run
   `/berkshire:approve`, or offer to start it now. Never call `place-trade` or `place-close` from this skill.
