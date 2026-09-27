"""Upstream ledger helper for the /upstream-scout skill (REQ-UP).

    python tools/upstream.py check                         # validate docs/upstream.md
    python tools/upstream.py worklist --prs prs.json       # what to (re)analyse this run
    python tools/upstream.py summary                       # counts by status

`prs.json` is `gh pr list -R TauricResearch/TradingAgents --state open --limit 500
--json number,title,headRefOid,updatedAt,isDraft,author`. The deep analysis is done by
the skill's agents; this file only decides what needs it and keeps the ledger honest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "upstream.md"
REQUIREMENTS = ROOT / "docs" / "requirements.md"
STATUSES = {"incorporated", "adapted", "planned", "candidate", "watch", "declined", "not-applicable"}
VERDICTS = {"adopt", "adapt", "watch", "decline"}
NEEDS_REQS = {"incorporated", "adapted"}


def _table(text: str, heading: str) -> list[dict]:
    """Rows of the first markdown table under `## heading`, as dicts keyed by header."""
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError(f"ledger has no '## {heading}' section")
    lines = [ln for ln in m.group(1).splitlines() if ln.startswith("|")]
    if len(lines) < 2:
        raise ValueError(f"'## {heading}' has no table")
    head = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows.append(dict(zip(head, cells + [""] * (len(head) - len(cells)), strict=False)))
    return rows


def load(path: Path = LEDGER) -> dict:
    text = path.read_text(encoding="utf-8")
    watermark = {r["Key"]: r["Value"] for r in _table(text, "Watermark")}
    return {"watermark": watermark, "features": _table(text, "Features"), "prs": _table(text, "Pull requests")}


def requirement_ids(path: Path = REQUIREMENTS) -> set[str]:
    return set(re.findall(r"^\| (REQ-[A-Z]+-\d+) \|", path.read_text(encoding="utf-8"), re.MULTILINE))


def _reqs(cell: str) -> list[str]:
    return [r.strip() for r in cell.split(",") if r.strip()]


def check(ledger: dict, reqs: set[str]) -> list[str]:
    """Problems in the ledger; empty when consistent (REQ-UP-03)."""
    problems = []
    for key in ("upstream", "last_reviewed_commit", "last_reviewed_release", "last_run"):
        if not ledger["watermark"].get(key):
            problems.append(f"watermark: missing {key}")
    seen = set()
    for row in ledger["features"]:
        fid = row.get("ID", "")
        if not re.fullmatch(r"UP-\d{3}", fid):
            problems.append(f"feature id {fid!r} is not UP-NNN")
        if fid in seen:
            problems.append(f"{fid}: duplicate id")
        seen.add(fid)
        problems += _check_row(fid, row, reqs)
    prs = set()
    for row in ledger["prs"]:
        pr = row.get("PR", "")
        if not re.fullmatch(r"#\d+", pr):
            problems.append(f"PR cell {pr!r} is not #NNN")
        if pr in prs:
            problems.append(f"{pr}: duplicate row")
        prs.add(pr)
        if row.get("Verdict") not in VERDICTS:
            problems.append(f"{pr}: verdict {row.get('Verdict')!r} not in {sorted(VERDICTS)}")
        if not re.fullmatch(r"[0-9a-f]{7,40}", row.get("Head", "")):
            problems.append(f"{pr}: head {row.get('Head')!r} is not a commit sha")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("Reviewed", "")):
            problems.append(f"{pr}: reviewed date {row.get('Reviewed')!r} is not YYYY-MM-DD")
        if not row.get("Rationale"):
            problems.append(f"{pr}: no rationale")
        problems += _check_row(pr, row, reqs)
    return problems


def _check_row(key: str, row: dict, reqs: set[str]) -> list[str]:
    out = []
    status = row.get("Status")
    if status not in STATUSES:
        out.append(f"{key}: status {status!r} not in {sorted(STATUSES)}")
    linked = _reqs(row.get("Berkshire", ""))
    if status in NEEDS_REQS and not linked:
        out.append(f"{key}: {status} but names no Berkshire requirement")
    out += [f"{key}: unknown requirement {r}" for r in linked if r not in reqs]
    if status in {"adapted", "declined", "planned", "watch", "candidate"} and not (row.get("Notes") or row.get("Rationale")):
        out.append(f"{key}: {status} needs a note saying why")
    return out


def worklist(ledger: dict, open_prs: list[dict]) -> dict:
    """Which open PRs are new, changed since their analysis, unchanged; which ledger PRs closed."""
    known = {int(r["PR"].lstrip("#")): r for r in ledger["prs"] if r.get("PR", "").startswith("#")}
    new, updated, unchanged = [], [], []
    for pr in sorted(open_prs, key=lambda p: p["number"]):
        row = known.get(pr["number"])
        item = {
            "number": pr["number"],
            "title": pr.get("title", ""),
            "head": pr.get("headRefOid", "")[:12],
            "draft": pr.get("isDraft", False),
            "updated": pr.get("updatedAt", "")[:10],
        }
        if row is None:
            new.append(item)
        elif not pr.get("headRefOid", "").startswith(row["Head"]):
            updated.append({**item, "previous_head": row["Head"], "previous_verdict": row["Verdict"]})
        else:
            unchanged.append(item["number"])
    open_numbers = {p["number"] for p in open_prs}
    closed = [n for n, r in known.items() if n not in open_numbers and r.get("Status") not in {"incorporated", "declined"}]
    return {"new": new, "updated": updated, "unchanged": unchanged, "closed_since": sorted(closed)}


def summary(ledger: dict) -> dict:
    count = lambda rows: {s: sum(r.get("Status") == s for r in rows) for s in sorted(STATUSES)}  # noqa: E731
    return {"watermark": ledger["watermark"], "features": count(ledger["features"]), "prs": count(ledger["prs"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check")
    w = sp.add_parser("worklist")
    w.add_argument("--prs", required=True, help="JSON from gh pr list (see module docstring)")
    sp.add_parser("summary")
    a = ap.parse_args(argv)
    ledger = load()
    if a.cmd == "check":
        problems = check(ledger, requirement_ids())
        print("\n".join(problems) or "ledger OK")
        return 1 if problems else 0
    if a.cmd == "worklist":
        print(json.dumps(worklist(ledger, json.loads(Path(a.prs).read_text(encoding="utf-8"))), indent=2))
    else:
        print(json.dumps(summary(ledger), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
