"""Requirements <-> test plan <-> test code traceability.

`python tests/test_traceability.py --write` regenerates the REQ -> TST matrix in
docs/test-plan.md from the test-case table.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ_DOC, PLAN_DOC = ROOT / "docs" / "requirements.md", ROOT / "docs" / "test-plan.md"
BEGIN, END = "<!-- MATRIX:BEGIN -->", "<!-- MATRIX:END -->"


def requirements() -> list[str]:
    return re.findall(r"^\| (REQ-[A-Z]+-\d+) \|", REQ_DOC.read_text(), re.MULTILINE)


def plan_rows() -> dict[str, dict]:
    rows = {}
    for m in re.finditer(r"^\| (TST-[A-Z]+-\d+) \| ([^|]+) \| ([^|]+) \| ([TID]) \|", PLAN_DOC.read_text(), re.MULTILINE):
        rows[m.group(1)] = {"title": m.group(2).strip(), "reqs": {r.strip() for r in m.group(3).split(",")},
                            "type": m.group(4)}
    return rows


def code_tests() -> dict[str, set]:
    found = {}
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        for m in re.finditer(r'"""(TST-[A-Z]+-\d+): [^\n]*?\[([^\]]+)\]', f.read_text()):
            assert m.group(1) not in found, f"duplicate test id {m.group(1)}"
            found[m.group(1)] = {r.strip() for r in m.group(2).split(",")}
    return found


def matrix(rows: dict) -> str:
    by_req = defaultdict(list)
    for tid, row in rows.items():
        for r in row["reqs"]:
            by_req[r].append(tid)
    lines = ["| Requirement | Tests |", "|---|---|"]
    lines += [f"| {r} | {', '.join(sorted(by_req[r]))} |" for r in requirements()]
    return "\n".join(lines)


def test_traceability():
    """TST-SAFE-04: Requirements, test plan and test code are mutually traceable [REQ-SAFE-04]"""
    reqs, rows, code = set(requirements()), plan_rows(), code_tests()
    assert len(reqs) == len(requirements()), "duplicate requirement ids"
    covered = set().union(*(r["reqs"] for r in rows.values()))
    assert not (reqs - covered), f"requirements without tests: {sorted(reqs - covered)}"
    assert not (covered - reqs), f"plan references unknown requirements: {sorted(covered - reqs)}"
    automated = {t: r for t, r in rows.items() if r["type"] in "TI"}
    assert not (set(automated) - set(code)), f"planned tests missing in code: {sorted(set(automated) - set(code))}"
    assert not (set(code) - set(rows)), f"tests missing from the plan: {sorted(set(code) - set(rows))}"
    manual_in_code = {t for t, r in rows.items() if r["type"] == "D"} & set(code)
    assert not manual_in_code, f"manual tests implemented in code: {manual_in_code}"
    for tid, reqs_in_code in code.items():
        assert reqs_in_code == rows[tid]["reqs"], f"{tid}: code links {sorted(reqs_in_code)} != plan {sorted(rows[tid]['reqs'])}"
    text = PLAN_DOC.read_text()
    current = text.split(BEGIN)[1].split(END)[0].strip()
    assert current == matrix(rows), "traceability matrix is stale: run python tests/test_traceability.py --write"


if __name__ == "__main__" and "--write" in sys.argv:
    text = PLAN_DOC.read_text()
    head, rest = text.split(BEGIN)
    PLAN_DOC.write_text(f"{head}{BEGIN}\n{matrix(plan_rows())}\n{END}{rest.split(END)[1]}")
    print("matrix written")
