# Berkshire: instructions for agents

Berkshire is a Claude Code plugin that re-implements TradingAgents: the roles are subagents (`agents/*.md`),
the skills orchestrate (`skills/`), and a deterministic Python engine (`berkshire/`) owns routing, context,
schemas, memory, data, the risk gate and the approval queue. Orders are placed only through
`/berkshire:approve`, one human approval per order.

## Documents

| Document | What it holds |
|---|---|
| [docs/requirements.md](docs/requirements.md) | The contract: decisions D1–D12 and every `REQ-*` |
| [docs/design.md](docs/design.md) | How the engine is built: modules, the run lifecycle, the home layout, the tick |
| [docs/test-plan.md](docs/test-plan.md) | Test strategy and environment, every `TST-*`, the manual procedures (M1…) and the REQ→TST matrix |
| [docs/tradingagents-analysis.md](docs/tradingagents-analysis.md) | How TradingAgents works, and how it maps into Berkshire (§7) |
| [docs/upstream.md](docs/upstream.md) | The upstream ledger: what TradingAgents offers and what Berkshire took, with reports in [docs/upstream-reports/](docs/upstream-reports/) |
| [README.md](README.md) | Commands, install, views and CI jobs |

## Change discipline

Every behaviour change lands in one commit with:

1. the `REQ-*` it implements, added or amended in `docs/requirements.md` (never renumber an id; retire it);
2. a `TST-*` row in `docs/test-plan.md` citing those REQ ids, and a test whose docstring starts
   `TST-…: title [REQ-…]` with exactly the row's REQ ids;
3. the matrix regenerated: `uv run python tests/test_traceability.py --write`.

Expected values come from the requirement, not from the code. Write the failing test first.

## Local gates (the same as CI)

```bash
uv run --all-extras pytest -q --cov    # tests, traceability, coverage floor in pyproject.toml
uvx ruff@0.16.5 check .                # the version pinned in .github/workflows/ci.yml
cd webui && npm run lint && npm test && npm run build  # web view
uv run python tools/upstream.py check  # the upstream ledger, when docs/upstream.md changes
```

gitleaks and CodeQL run only in CI. Never weaken a gate to get green: no lower coverage floor, new ruff ignore,
or skipped test.

## Releases and merges

- Bump the version in `pyproject.toml`, `berkshire/__init__.py` and `.claude-plugin/plugin.json` (then `uv lock`)
  in a separate "Version x.y.z" commit on the branch.
- Changes reach `main` through a pull request, merged with a merge commit once every CI job is green.
- Upstream TradingAgents is reviewed with `/upstream-scout`, which records verdicts in `docs/upstream.md`.
