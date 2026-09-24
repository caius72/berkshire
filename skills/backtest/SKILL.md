---
name: backtest
description: Run the Berkshire pipeline over a grid of tickers and dates in an isolated home, then score decisions by rating (hit rate and mean alpha). Never creates orders.
arguments: [args]
allowed-tools: Bash(berkshire *) Bash(BERKSHIRE_HOME=* berkshire *) Read Agent
---

# /berkshire:backtest

Mirrors `tradingagents backtest`:

```
/berkshire:backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 [--every 7]
                    [--analysts market,news] [--depth shallow] [--asset-type stock] [--run-id ID]
```

Arguments: `$ARGUMENTS`

1. `berkshire backtest plan TICKERS --start S --end E --every N [--run-id ID]` returns `run_id`, `home`,
   the `cells` still to run, and the `skipped` count (cells already done under this run id). Tell the user
   how many cells will run. Every cell is a full multi-agent run, so warn if there are more than 20.
2. For every cell, prefix **every** engine call with `ENV = "BERKSHIRE_HOME=<home> "`, so the live decision
   log and order queue are never touched:
   - `ENV berkshire init <ticker> <date> [--analysts …] [--depth …] [--asset-type …]`
   - then follow `${CLAUDE_PLUGIN_ROOT}/skills/analyze/pipeline-loop.md` with that `ENV`.
   - If a cell fails, record it and continue with the next.
3. Settle: `ENV berkshire settle --all`. Launch a `berkshire:reflector` agent for each item, then
   `ENV berkshire settle --apply`. Cells whose holding window has not traded yet stay pending.
4. `berkshire backtest summary <run_id>` prints resolved, pending and unscored counts, and per rating:
   n, hit rate and mean alpha. Show it with the failures.

Never run `gate`, `enqueue`, or any eToro tool in a backtest. Re-running with the same `--run-id` resumes.
