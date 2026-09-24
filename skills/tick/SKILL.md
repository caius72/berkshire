---
name: tick
description: One scheduled Berkshire cycle. Reads the eToro portfolio and watchlist, settles and reflects on past decisions, analyzes every holding and watchlist instrument, runs the risk gate, and queues order proposals for human approval. Run it as `/loop 24h /berkshire:tick`.
allowed-tools: Bash(berkshire *) Bash(date *) Bash(mkdir *) Read Write Agent PushNotification mcp__claude_ai_eToro__get-my-portfolio-summary mcp__claude_ai_eToro__get-my-watchlists mcp__claude_ai_eToro__get-instruments-overview
---

# /berkshire:tick

One cycle, safe to repeat. This skill **never places orders**: eToro's
`place-trade` and `place-close` need a human approval per order, which
`/berkshire:approve` collects. Scheduling: `/loop 24h /berkshire:tick`.

`W = ~/.berkshire/tick/<date>` (create it). `DATE = $(date +%F)`. `ACCOUNT` = `account` from `berkshire config`.

1. **Read the book.** Call `get-my-portfolio-summary` with `account: ACCOUNT` and
   `includePositions: true`. Save the raw JSON to `W/etoro_summary.json`. Then call
   `get-my-watchlists` and save it to `W/watchlists.json`.
2. **Portfolio context:** `berkshire etoro-portfolio W/etoro_summary.json --out W/portfolio.json`.
3. **Universe:** `berkshire universe --portfolio-file W/portfolio.json --watchlists-file W/watchlists.json --date DATE`
   returns `instruments` (holdings first, then the configured watchlist, capped), `skipped` and `trading_day`.
4. **Settle and reflect** on every due decision: `berkshire settle --all`. Launch one
   `berkshire:reflector` agent per item in `to_reflect` (in parallel), then run `berkshire settle --apply`.
5. **Weekend or holiday:** if `trading_day` is false, notify "settled N decisions, markets closed"
   and stop.
6. **Analyze** each instrument, one at a time:
   `berkshire init <ticker> DATE --asset-type <asset_type> --etoro-symbol <etoro_symbol> --instrument-id <instrument_id> --portfolio W/portfolio.json --checkpoint --skip-if-complete`
   - `skipped: true` means it was already analysed today. Keep its `run_dir` and move on.
   - Otherwise follow `${CLAUDE_PLUGIN_ROOT}/skills/analyze/pipeline-loop.md` with `RUN = run_dir`.
   - If one instrument fails, record it and continue with the next. A failure never aborts the tick.
7. **Quotes:** call `get-instruments-overview` once, with every analysed `instrument_id`
   (batch; never one call per instrument). Save it to `W/quotes.json`.
8. **Risk gate:** for each completed run, run `berkshire gate RUN --quote-file W/quotes.json --portfolio-file W/portfolio.json`.
9. **Queue:** `berkshire enqueue --tag tick-DATE <all run dirs>`. Runs that were already queued are skipped.
10. **Report and notify.** Print a table (ticker, signal, intent or veto reason) plus failures and
    skipped instruments. Send a PushNotification: "Berkshire DATE: N analysed, K orders awaiting /berkshire:approve".

Ask the user nothing during a tick. It must run unattended.
