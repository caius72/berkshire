---
name: upstream-scout
description: Scout TauricResearch/TradingAgents for Berkshire. Reviews upstream commits and releases since the last run, deep-analyses new or changed open PRs with parallel agents, assesses each for inclusion in Berkshire, writes a dated report, and keeps the upstream ledger (docs/upstream.md) of what is available and what is incorporated. Use for "check upstream", "what's new in TradingAgents", "review TradingAgents PRs", "upstream scout".
arguments: [args]
allowed-tools: Bash(gh auth status) Bash(gh repo clone TauricResearch/TradingAgents *) Bash(gh pr list *) Bash(gh pr view *) Bash(gh pr diff *) Bash(gh release list *) Bash(gh issue view *) Bash(git -C * fetch *) Bash(git -C * log *) Bash(git -C * show *) Bash(git -C * diff *) Bash(git -C * rev-parse *) Bash(uv run python tools/upstream.py *) Bash(uv run pytest *) Bash(date *) Bash(mkdir *) Read Write Edit Grep Glob Agent AskUserQuestion
---

# /upstream-scout

Berkshire mirrors TradingAgents (see `docs/tradingagents-analysis.md`). This skill keeps it
that way on purpose, not by accident: it looks at what changed upstream, judges each change
**on its merits for Berkshire**, and records the verdict in `docs/upstream.md`.

Arguments: `$ARGUMENTS`
- `--max N`: deep-analyse at most N PRs this run (default 10). The rest wait for the next run.
- `--all`: no cap.
- `--pr N [N …]`: analyse only these PRs, even if unchanged.
- `--commits-only` / `--prs-only`: skip the other half.

It **proposes, it does not implement.** Nothing outside `docs/upstream.md` and
`docs/upstream-reports/` changes without the user choosing it in step 7.

## 0. Preconditions

- `gh auth status` succeeds.
- `U` is the upstream clone: `../TradingAgents` next to this repo. If it doesn't exist, clone it there
  with `gh repo clone TauricResearch/TradingAgents ../TradingAgents`.
- `uv run python tools/upstream.py check` prints `ledger OK`. If not, fix the ledger first.
- `D = $(date +%F)`. `R = docs/upstream-reports/D`. Create `R`.

## 1. Upstream commits and releases since the watermark

1. `git -C U fetch --tags origin`. `W` = `last_reviewed_commit` from the ledger's Watermark table.
2. `git -C U log --oneline --no-merges W..origin/main` for the commits, and
   `gh release list -R TauricResearch/TradingAgents --limit 10` for the releases. Also check
   `git -C U diff W..origin/main -- CHANGELOG.md`: it names features and issue numbers.
3. Group the commits into features, one per changelog line or issue. For each feature, read its diff
   (`git -C U show <sha>`) and the Berkshire code it would touch (map below). Then decide, on your own
   assessment, a status from the ledger's list and add a row `UP-NNN` to **Features** (next free
   number), with `Upstream` = the release or short sha. `incorporated`/`adapted` need requirement ids;
   every other status needs a note saying why.
4. A merged PR that is already in the ledger's Pull requests table becomes a feature row.
   Update its PR row: keep the verdict, and set Status to reflect the decision on the feature.

## 2. Open PRs: what to analyse

1. `gh pr list -R TauricResearch/TradingAgents --state open --limit 500 --json number,title,headRefOid,updatedAt,isDraft,author > R/prs.json`
2. `uv run python tools/upstream.py worklist --prs R/prs.json` returns `new`, `updated` (the head moved
   since its analysis), `unchanged` and `closed_since`.
3. The work is `new` + `updated` (or the `--pr` list). With more than `--max` items, triage first:
   read each title and `gh pr view N --json body,files` briefly, and take the most relevant to Berkshire
   (decision quality, point-in-time honesty, grounding, memory and learning, data robustness, risk)
   ahead of provider plumbing, UI chrome and docs. Say which were deferred.
4. For each PR in `closed_since`: `gh pr view N -R TauricResearch/TradingAgents --json state,mergedAt`.
   Merged goes to step 1.4. Closed unmerged: set Status `declined` if its verdict was `watch` or
   `candidate`, noting "closed upstream unmerged". Keep the row.

## 3. Deep analysis, one agent per PR, in parallel

Read `${CLAUDE_SKILL_DIR}/pr-brief.md`. Launch **one Agent per PR, all in one message**:
`subagent_type: general-purpose`, `model: opus`, `description: "TradingAgents PR #N"`, and the
brief with `{N}`, `{UPSTREAM}` (= `U`), `{BERKSHIRE}` (= this repo's root) and `{REPORT}` (=
`R/pr-N.md`) filled in. Each agent writes its analysis to `{REPORT}` and replies with one JSON line.
If an agent fails, re-run it once. After that, record the PR as `watch` with the rationale "analysis
failed: …".

Then **review the verdicts yourself**. The agents see one PR each, and you see all of them:
- If two PRs solve the same problem, pick one, and point the other's rationale at it.
- Downgrade an `adopt` that conflicts with a Berkshire decision (D1–D12 in `docs/requirements.md`),
  e.g. anything that places orders without per-order approval, or adds an LLM provider.
- Keep verdicts about the idea's value to Berkshire. Upstream merge status only affects urgency.

## 4. Report

Write `R/README.md`:
1. **Summary**: counts (commits, features added, PRs analysed, deferred), and the three to five changes
   worth doing, each one line with its effort (S/M/L).
2. **Upstream changes**: one paragraph per feature row added: what it is, and the verdict with the reason.
3. **Pull requests**: a table (PR, title, verdict, status, effort, one-line rationale, link to
   `pr-N.md`), ordered adopt → adapt → watch → decline.
4. **Recommended Berkshire changes**: for each `adopt`/`adapt`, the concrete change (files,
   requirement ids to add or amend, tests), and how it interacts with the others.
5. **Deferred**: the PRs not analysed this run.

## 5. Ledger

In `docs/upstream.md`:
- Add or replace a Pull requests row per analysed PR:
  `| #N | title | head (12 chars) | D | verdict | status | REQ-… | rationale (≤ 200 chars) |`.
  Status for a fresh verdict: `adopt`/`adapt` → `candidate`, `watch` → `watch`, `decline` → `declined`.
  Status becomes `planned`, `incorporated` or `adapted` only through step 7.
- Update the Watermark: `last_reviewed_commit` = `git -C U rev-parse --short origin/main`,
  `last_reviewed_release` = the newest release, and `last_run` = D. Only now, after the report exists,
  so an interrupted run is redone rather than skipped.
- `uv run python tools/upstream.py check` must print `ledger OK`, and
  `uv run pytest tests/test_upstream.py tests/test_traceability.py -q` must pass.

## 6. Present

Show the report summary and the PR table, and give the report path.

## 7. Decide with the user

Ask with AskUserQuestion (multiSelect) which of the recommended changes to take up. Offer at most 4;
list the rest in the question text. For each chosen one: set its ledger Status to `planned`, with the
next step in its rationale. Implementing is separate work that follows the repo's discipline: add or
amend the `REQ-*` in `docs/requirements.md`, add `TST-*` rows and tests, and update the matrix
(`uv run python tests/test_traceability.py --write`). Only when that is done does Status become
`incorporated` or `adapted`, with the requirement ids.

## Where TradingAgents code maps into Berkshire

| TradingAgents | Berkshire |
|---|---|
| `tradingagents/agents/**` (prompts) | `agents/*.md` (personas) + `berkshire/pipeline.py` `build_prompt` (context) |
| `agents/schemas.py`, `rating.py`, `structured.py` | `berkshire/decisions.py` |
| `graph/setup.py`, `conditional_logic.py`, `propagation.py` | `berkshire/pipeline.py` (`next_steps`, state) |
| `graph/reflection.py`, `settlement.py`, `decision_log.py` | `berkshire/memory.py`, `agents/reflector.md` |
| `dataflows/**` | `berkshire/data.py` (yfinance) + web search in `agents/news-analyst.md`, `sentiment-analyst.md` |
| `portfolio.py` | `berkshire/etoro.py` |
| `backtest.py` | `berkshire/backtest.py`, `skills/backtest` |
| `cli/**` | `skills/analyze`, `berkshire/server.py`, `tui.py`, `webui/` |
| `llm_clients/**`, provider config | not applicable: Claude subagents (REQ-ROLE-02) |
| (none upstream) | risk gate, order queue, eToro execution (`orders.py`, `skills/approve`, `skills/tick`) |
