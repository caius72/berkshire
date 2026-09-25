# Brief: deep analysis of TradingAgents PR #{N} for Berkshire

You are reviewing an open pull request on TauricResearch/TradingAgents (the upstream clone is
at `{UPSTREAM}`), to decide whether Berkshire (`{BERKSHIRE}`) should take the idea. Berkshire is
a Claude Code plugin that re-implements TradingAgents: roles are Claude subagents (`agents/*.md`),
and a deterministic Python engine (`berkshire/`) does routing, context, schemas, memory, data,
the risk gate, and human-approved eToro execution. Read `{BERKSHIRE}/docs/tradingagents-analysis.md`
§7 and the decisions table at the top of `{BERKSHIRE}/docs/requirements.md` first.

Your judgement is the product. Do not echo the PR description. Work out what the change really does,
whether it is sound, and what it would be worth to Berkshire.

## Gather

1. `gh pr view {N} -R TauricResearch/TradingAgents --json number,title,body,author,createdAt,updatedAt,headRefOid,isDraft,labels,additions,deletions,files,reviews,comments,statusCheckRollup,mergeable`
2. `gh pr diff {N} -R TauricResearch/TradingAgents`. For a large diff, read the core files fully
   and skim tests and generated files.
3. For context, the upstream files it touches, at `{UPSTREAM}` (`git -C {UPSTREAM} show origin/main:<path>`),
   and any issue it references (`gh issue view <n> -R TauricResearch/TradingAgents`).
4. The Berkshire counterpart of the code it touches (see the map in the skill; `grep -rn` the concept
   in `{BERKSHIRE}/berkshire`, `agents`, `skills`), and the related `REQ-*` rows in `docs/requirements.md`.
   Check whether Berkshire already covers it.

## Assess

- **What it does**: the mechanism in two or three sentences, and the problem it solves (the issue, or the
  failure mode it guards against).
- **Soundness**: correctness, edge cases, point-in-time and look-ahead safety, and failure behaviour.
  Name any concrete bug you find, with file and line.
- **Quality and maturity**: tests added, CI status, review activity, maintainer response, and draft or
  stale state. How likely is it to merge, and how likely to change?
- **Value to Berkshire**: does it improve decision quality, grounding, honesty about data, learning from
  outcomes, robustness of scheduled ticks, or risk control? Or is it provider plumbing, CLI chrome, or
  docs that do not transfer? Is Berkshire already better or worse here?
- **Fit**: conflicts with a Berkshire decision (no autonomous order placement, Claude-only models,
  demo-first eToro execution, the engine/agent split). Licence: upstream is Apache-2.0, and Berkshire
  re-implements ideas rather than copying large code.
- **Cost**: the Berkshire change (files, `REQ-*` to add or amend, tests), effort S (< 2 h), M (a day),
  L (more), and the risk of the change.

## Verdict

`adopt` (take the idea as is), `adapt` (take the idea, build it the Berkshire way), `watch` (promising,
not ready or unclear), or `decline` (not worth it for Berkshire, with the reason). Be decisive: a
`watch` needs a concrete trigger that would change it.

## Output

Write `{REPORT}` with these sections: **Summary** (verdict and one sentence), **What it does**,
**Soundness**, **Quality and maturity**, **Value to Berkshire**, **Proposed Berkshire change**
(or "none", with why), **Effort and risk**, **Open questions**. Cite files as `path:line`.

Then reply with exactly one JSON line and nothing else:

{"pr": {N}, "head": "<headRefOid, first 12 chars>", "title": "<title>", "verdict": "adopt|adapt|watch|decline", "berkshire": "<comma-separated REQ ids affected, or empty>", "effort": "S|M|L", "rationale": "<= 200 characters, specific>", "report": "{REPORT}"}
