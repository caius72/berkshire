# Berkshire pipeline loop (shared by analyze, tick and backtest)

The engine (`berkshire`) owns routing and state. You are the dispatcher: run the
step it names, hand the output back, and repeat. Never decide the order yourself,
and never read reports into your own context mid-run (they are large and the
agents read them from disk).

Given `RUN` (the `run_dir` from `berkshire init`) and an optional env prefix `ENV`
(for example `BERKSHIRE_HOME=… ` in a backtest; empty otherwise):

1. `ENV berkshire next RUN` prints `{"done", "signal", "steps": [...]}`.
2. If `done` is true, stop. The run is complete, or `stopped` says the user stopped it (from the
   dashboard or `berkshire stop`). A stopped run: say so, with the reason, and dispatch nothing more.
3. Launch **one Agent call per step, all in the same message** so that independent
   analysts run in parallel. For each step:
   - `subagent_type`: the step's `agent` (e.g. `berkshire:market-analyst`)
   - `model`: the step's `model`
   - `description`: `<TICKER> <step id>`
   - `prompt`:
     ```
     Step: <id>
     Prompt file: <prompt_file>
     Output file: <output_file>
     Read the prompt file, do your role's job, write the complete answer to the output file, then reply `DONE <output file>`.
     ```
4. After each agent returns, run `ENV berkshire submit RUN <id>`.
   - An error saying the run was stopped means the user stopped it mid-step. Stop dispatching and report it.
   - An `{"error": …}` saying there is no output file means the agent failed, including an analyst
     that stopped at its turn limit (`maxTurns`) before writing its file. Re-run that
     one step once. If it fails again, stop and report it. The state is kept, so
     `--checkpoint` resumes from here.
   - Any `warnings` (e.g. structured JSON fell back to free text) are shown in the final summary.
5. When a team finishes (all analysts done, Research Manager done, Trader done, risk
   debate done), print `ENV berkshire status RUN` so the user sees progress by team.
6. Go to 1.

The Portfolio Manager's `submit` result carries `signal` (Buy / Overweight / Hold /
Underweight / Sell, or REVIEW) and `report` (path to `complete_report.md`).
