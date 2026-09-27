"""The upstream ledger, its worklist, and the /upstream-scout skill."""

import copy
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import upstream  # noqa: E402

SKILL = (ROOT / ".claude" / "skills" / "upstream-scout" / "SKILL.md").read_text()
BRIEF = (ROOT / ".claude" / "skills" / "upstream-scout" / "pr-brief.md").read_text()


@pytest.fixture
def ledger():
    return upstream.load()


def pr_row(**kw):
    row = {
        "PR": "#1404",
        "Title": "Jev debate gate",
        "Head": "abcdef123456",
        "Reviewed": "2026-09-25",
        "Verdict": "watch",
        "Status": "watch",
        "Berkshire": "",
        "Rationale": "Early-stop idea; needs evidence.",
    }
    return {**row, **kw}


def test_ledger_consistent(ledger):
    """TST-UP-01: The ledger is consistent and records the v0.5.1 baseline [REQ-UP-01, REQ-UP-05]"""
    assert upstream.check(ledger, upstream.requirement_ids()) == []
    assert ledger["watermark"]["upstream"] == "TauricResearch/TradingAgents"
    baseline = [r for r in ledger["features"] if r["Upstream"] == "v0.5.1"]
    assert len(baseline) >= 30
    assert {r["Status"] for r in baseline} >= {"incorporated", "adapted", "not-applicable"}
    assert upstream.main(["check"]) == 0


@pytest.mark.parametrize(
    "mutate,problem",
    [
        (lambda lg: lg["features"][0].update(Status="done"), "status 'done'"),
        (lambda lg: lg["features"][0].update(Berkshire=""), "incorporated but names no Berkshire requirement"),
        (lambda lg: lg["features"][0].update(Berkshire="REQ-NOPE-01"), "unknown requirement REQ-NOPE-01"),
        (lambda lg: lg["features"].append(dict(lg["features"][0])), "duplicate id"),
        (lambda lg: lg["features"][30].update(Notes=""), "needs a note"),
        (lambda lg: lg["watermark"].pop("last_reviewed_commit"), "missing last_reviewed_commit"),
        (lambda lg: lg["prs"].append(pr_row(Verdict="merge")), "verdict 'merge'"),
        (lambda lg: lg["prs"].append(pr_row(Head="HEAD")), "is not a commit sha"),
        (lambda lg: lg["prs"].append(pr_row(Reviewed="yesterday")), "not YYYY-MM-DD"),
        (lambda lg: lg["prs"].append(pr_row(Rationale="")), "no rationale"),
        (lambda lg: lg["prs"].extend([pr_row(), pr_row()]), "duplicate row"),
    ],
)
def test_check_catches(ledger, mutate, problem):
    """TST-UP-02: The ledger check rejects bad statuses, missing or unknown requirements, duplicates and bad PR rows [REQ-UP-01]"""
    bad = copy.deepcopy(ledger)
    mutate(bad)
    problems = upstream.check(bad, upstream.requirement_ids())
    assert any(problem in p for p in problems), problems


def test_worklist(ledger):
    """TST-UP-03: The worklist splits open PRs into new, head-moved and unchanged, and flags PRs that left the open list [REQ-UP-02]"""
    lg = copy.deepcopy(ledger)
    lg["prs"] = [
        pr_row(PR="#10", Head="aaaaaaaaaaaa"),
        pr_row(PR="#11", Head="bbbbbbbbbbbb"),
        pr_row(PR="#12", Head="cccccccccccc", Status="watch"),
        pr_row(PR="#13", Head="dddddddddddd", Status="declined"),
    ]
    open_prs = [
        {"number": 10, "title": "same", "headRefOid": "aaaaaaaaaaaa" + "0" * 28, "updatedAt": "2026-09-20T00:00:00Z"},
        {"number": 11, "title": "moved", "headRefOid": "eeeeeeeeeeee" + "0" * 28, "updatedAt": "2026-09-25T00:00:00Z"},
        {"number": 14, "title": "brand new", "headRefOid": "ffffffffffff" + "0" * 28, "isDraft": True},
    ]
    w = upstream.worklist(lg, open_prs)
    assert [p["number"] for p in w["new"]] == [14] and w["new"][0]["draft"] is True
    assert [(p["number"], p["previous_head"]) for p in w["updated"]] == [(11, "bbbbbbbbbbbb")]
    assert w["unchanged"] == [10]
    assert w["closed_since"] == [12]  # #13 was declined already; nothing left to decide


def test_skill_workflow():
    """TST-UP-04: The skill reviews commits since the watermark, fans out one agent per PR, and moves the watermark last [REQ-UP-03, REQ-UP-04]"""
    assert "W..origin/main" in SKILL and "CHANGELOG.md" in SKILL and "gh release list" in SKILL
    assert "one Agent per PR, all in one message" in SKILL and "pr-brief.md" in SKILL
    assert SKILL.index("## 4. Report") < SKILL.index("Update the Watermark")
    assert "It **proposes, it does not implement.**" in SKILL
    assert SKILL.index("AskUserQuestion (multiSelect)") < SKILL.index("set its ledger Status to `planned`")
    for placeholder in ("{N}", "{UPSTREAM}", "{BERKSHIRE}", "{REPORT}"):
        assert placeholder in BRIEF
    assert '"verdict": "adopt|adapt|watch|decline"' in BRIEF
    for section in ("**Soundness**", "**Value to Berkshire**", "**Proposed Berkshire change**"):
        assert section in BRIEF


def test_skill_is_read_only_upstream():
    """TST-UP-05: The skill may read upstream but has no permission to push, merge, comment or edit there [REQ-UP-04]"""
    tools = re.search(r"^allowed-tools: (.*)$", SKILL, re.MULTILINE).group(1)
    assert "Bash(gh *)" not in tools and "Bash(git *)" not in tools
    for forbidden in ("push", "commit", "merge", "comment", "review", "edit", "close", "reset", "checkout"):
        assert forbidden not in tools, forbidden
    assert "Bash(gh pr diff *)" in tools and "Bash(git -C * log *)" in tools
