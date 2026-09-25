---
name: dashboard
description: Open the Berkshire dashboard. Starts the local server if needed and gives the web URL (live progress, reports, decision log, order queue, backtests) and the terminal view command.
allowed-tools: Bash(berkshire *)
---

# /berkshire:dashboard

1. Run `berkshire web`. It starts `berkshire serve` in the background if none is running, and prints
   `{"url": …, "pid": …}`.
2. Give the user the `url`. It carries a one-time session token (`?t=…`), so tell them to open it as
   printed, and that they need a fresh URL (run this again) after the server restarts.
3. Mention the terminal view: `berkshire tui` (needs the `tui` extra: `uv sync --extra tui`).
4. Say plainly what the dashboard can and cannot do. It shows runs live and can start an analysis, but
   it cannot place orders: queued orders are placed only here, with `/berkshire:approve`.

If the web page says the UI is not built, run `npm ci && npm run build` in `${CLAUDE_PLUGIN_ROOT}/webui`.
