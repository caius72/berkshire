# Upstream scout, 2026-09-27 (third run: deferred PRs)

The five PRs deferred by the [second run](README-2.md), plus three new ones and one update. TradingAgents `main` (`35543d0`) and `v0.5.2` (`9968bd8`) are unchanged since then.

## Summary

| | |
|---|---|
| Commits since the watermark | 0 on `main`, 0 on `v0.5.2` |
| PRs analysed | 9: the 5 previously deferred, 3 new (#1427, #1428, #1429), 1 updated (#1416) |
| Verdicts | 1 adapt (one prompt line only), 8 decline |
| Deferred | none |

Worth doing:

1. **Syndicated copies are not independent confirmation** (from #1429, S). `tool_news` drops exact-title duplicates, but not re-headlined wire copies, and no persona tells the News or Sentiment Analyst not to count one story reprinted by several outlets as several confirmations. Add one line to each persona, with an inspection test. The PR's data sources (NewsData, X, Truth Social) are declined: none of them can serve a past date.

## Pull requests

| PR | Title | Verdict | Status | Effort | Rationale | Report |
|---|---|---|---|---|---|---|
| #1429 | NewsData, X and Truth Social sources | adapt | planned | S | Take only the "don't count syndicated duplicates as independent confirmation" rule. The sources can't serve a past date: NewsData covers 48 h, X 7 days and is paid, Truth Social returns 20 posts or a 403. There is also an X `start_time` bug (`x_social.py:80`). | [pr-1429](pr-1429.md) |
| #1428 | Settle past decisions alongside the analysts | decline | declined | S | It only saves time; the lessons are unchanged. Berkshire settles once per tick with parallel Reflectors before any analysis and fixes the lessons in `state.json` at init. Running settlement alongside the analysts would lose same-day lessons. | [pr-1428](pr-1428.md) |
| #1416 | Make the Jev screening endpoint pluggable (new head) | decline | declined | S | The new commit only treats `TYPESAFE_BASE_URL` as a base URL. Judge exceptions still escape `screen()` (probed), and the output still says Jev. UP-017 already uses Claude as the judge. | [pr-1416](pr-1416.md) |
| #1427 | Make the Jev screening endpoint configurable | decline | declined | S | Near-duplicate of the endpoint half of #1416, by a different author. Its description names `JEV_API_URL`, which the code doesn't use. Vendor plumbing Berkshire doesn't call. | [pr-1427](pr-1427.md) |
| #1003 | Windows launcher | decline | declined | S | `bin/berkshire` plus `uv run` already creates and syncs the environment. The PR is broken on `main`. On Windows, the real blockers are POSIX calls in the server and client. | [pr-1003](pr-1003.md) |
| #731 | GitHub Copilot provider | decline | declined | S | Provider plumbing (D1). It also conflicts with `main`, and its bare model ids are likely rejected. | [pr-731](pr-731.md) |
| #1121 | MiMo (Xiaomi) provider | decline | declined | S | Provider plumbing (D1). Broken: `factory.py:56` raises. | [pr-1121](pr-1121.md) |
| #1418 | Meta (Muse Spark) provider | decline | declined | S | Provider plumbing (D1). No transferable idea. | [pr-1418](pr-1418.md) |
| #1149 | Ollama Modelfile guide | decline | declined | S | Ollama only. The fast/accurate idea is covered by research depth (REQ-FLOW-07) and the deep/quick model split. Its 4k "accurate" context silently truncates prompts. | [pr-1149](pr-1149.md) |

## Recommended Berkshire change

- `agents/news-analyst.md` and `agents/sentiment-analyst.md`: one rule each. The same story reprinted or re-headlined by several outlets (wire copies, aggregators) counts as one source, not as independent confirmation. Weigh a story by the independent reports behind it, not by how often it appears.
- REQ-ROLE-03 or REQ-ROLE-05: add the rule to the analyst directives.
- Add an inspection test (TST-ROLE) that checks both personas name the rule.

## Deferred

None.
