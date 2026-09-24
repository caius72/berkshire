---
name: approve
description: Review Berkshire's queued eToro order proposals one by one and, only on explicit approval of each eToro confirmation block, place them with place-trade / place-close.
allowed-tools: Bash(berkshire *) Bash(mkdir *) Read Write AskUserQuestion
---

# /berkshire:approve

Human-in-the-loop execution. **One approval per order, and one approval per eToro call.**
Never batch approvals, never place without an answer in this session, and never use
`execute-write` for opening or closing positions.

`ACCOUNT` = `account` from `berkshire config` (default `demo`). `R = ~/.berkshire/tmp/approve`.

1. `berkshire queue list` shows the pending items (expired ones are dropped automatically). If there are none, say so and stop.
2. For each item, show: ticker, rating, account, amount or units, stop-loss and take-profit,
   the gate `reasons`, and `reports/5_portfolio/decision.md` from its run (read the file).

### Opening (`intent.kind == "open"`)
3. Call `prepare-trade` with `account: ACCOUNT`, `symbol: intent.etoro_symbol` (or `instrumentId`),
   `direction: "buy"`, `amount: intent.amount`, `stopLossRate: intent.stop_loss_rate`,
   `takeProfitRate: intent.take_profit_rate` (omit when null). Never pass leverage.
4. If the verdict is `rejected`, save the response to `R/<id>.json` and run
   `berkshire queue mark <id> rejected --result-file R/<id>.json`. Show the reasons and move on.
5. Otherwise show eToro's confirmation block **verbatim**: instrument, direction, amount, estimated units,
   live quote, costs, balance impact, warnings, and **the account (DEMO or REAL)**. Ask with
   AskUserQuestion: *Place this order* / *Reject* / *Skip for now*.
   - **Place:** `berkshire queue mark <id> approved`, then `place-trade` with the token. Save the
     result to `R/<id>.json`, then map the eToro outcome to a queue status:
     `executed` or `partiallyFilled` → `placed`; `pending` → `pending_fill` (do NOT place again);
     `rejected`, `cancelled` or `expired` → `failed`; `unknown` → `unknown` (retry `place-trade`
     once with the **same token**, which is idempotent, then record the final outcome).
     Run `berkshire queue mark <id> <status> --result-file R/<id>.json`.
   - **Reject:** `berkshire queue mark <id> rejected`.
   - **Skip:** leave it pending.
   - If the token expired before approval, run `prepare-trade` again and ask again.

### Closing (`intent.kind == "close"`)
6. For each entry in `intent.closes`: call `prepare-close` with `account: ACCOUNT`, `positionId`, and
   `unitsToDeduct` (omit when null, which means a full close). Show the confirmation (units, open rate,
   current rate, unrealized P&L, account) and ask as above. On approval, call `place-close` with that
   token. This is one approval per position. Record the outcome with the same mapping.

7. Finish with a summary table of placed, rejected, skipped and failed orders, and note the account.
