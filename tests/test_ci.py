"""Inspection tests of the CI workflow, lint config and coverage floor, plus view-level promises."""

import json
import os
import re
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def steps(job):
    return WF["jobs"][job]["steps"]


def runs(job):
    return "\n".join(s.get("run", "") for s in steps(job))


def uses(job):
    return [s["uses"] for s in steps(job) if "uses" in s]


def test_workflow_triggers_and_jobs():
    """TST-CI-01: CI runs on push and PR to main with test, core, lint, webui, secrets and sast jobs [REQ-CI-01]"""
    on = WF[True] if True in WF else WF["on"]  # YAML 1.1 reads the key `on` as True
    assert on["push"]["branches"] == ["main"] and on["pull_request"]["branches"] == ["main"]
    assert set(WF["jobs"]) == {"test", "core", "lint", "webui", "secrets", "sast"}


def test_lint_pinned_with_security_rules():
    """TST-CI-02: ruff is pinned in CI and the rule set includes bandit security checks [REQ-CI-02]"""
    pinned = WF["env"]["RUFF_VERSION"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned) and 'ruff@${RUFF_VERSION}' in runs("lint")
    ruff = tomllib.loads((ROOT / "ruff.toml").read_text())
    assert {"E9", "F", "B", "S"} <= set(ruff["lint"]["select"])
    assert pinned in (ROOT / "ruff.toml").read_text()   # the comment names the same version


def test_coverage_floor():
    """TST-CI-03: The test job runs every extra under branch coverage with a ratcheting floor and publishes the report [REQ-CI-03]"""
    assert "--all-extras" in runs("test") and "--cov" in runs("test") and "--cov-report=xml" in runs("test")
    cov = PYPROJECT["tool"]["coverage"]
    assert cov["run"]["branch"] is True and cov["report"]["fail_under"] >= 80
    assert "actions/upload-artifact@v4" in uses("test") and "GITHUB_STEP_SUMMARY" in runs("test")


def test_secret_scanning_full_history():
    """TST-CI-04: gitleaks scans the full history on every push and PR [REQ-CI-04]"""
    checkout = steps("secrets")[0]
    assert checkout["uses"].startswith("actions/checkout@") and checkout["with"]["fetch-depth"] == 0
    assert any(u.startswith("gitleaks/gitleaks-action@") for u in uses("secrets"))


def test_codeql_languages():
    """TST-CI-05: CodeQL analyses Python and JavaScript with security-extended queries [REQ-CI-05]"""
    job = WF["jobs"]["sast"]
    assert set(job["strategy"]["matrix"]["language"]) == {"python", "javascript-typescript"}
    assert job["permissions"]["security-events"] == "write"
    init = next(s for s in job["steps"] if s.get("uses", "").startswith("github/codeql-action/init@"))
    assert init["with"]["queries"] == "security-extended"


def test_core_job_proves_optional_tui():
    """TST-CI-06: The core job installs no extras, asserts textual is absent and checks the tui hint [REQ-CI-06]"""
    r = runs("core")
    assert "uv sync --locked\n" in r + "\n" and "--all-extras" not in r and "--extra" not in r
    assert "find_spec('textual')" in r and 'test "$code" -eq 3' in r
    assert PYPROJECT["project"]["optional-dependencies"]["tui"] == ["textual==8.2.8"]
    assert not any("textual" in d for d in PYPROJECT["project"]["dependencies"])


def test_webui_job():
    """TST-CI-07: The webui job runs npm ci, the node tests and the vite build [REQ-CI-07]"""
    r = runs("webui")
    for cmd in ("npm ci", "npm test", "npm run build", "test -f dist/index.html"):
        assert cmd in r
    pkg = json.loads((ROOT / "webui" / "package.json").read_text())
    assert pkg["scripts"]["test"].startswith("node --test") and (ROOT / "webui" / "package-lock.json").is_file()


def test_permissions_and_versions():
    """TST-CI-08: Read-only default permissions, versioned actions, locked installs [REQ-CI-08]"""
    assert WF["permissions"] == {"contents": "read"}
    for job in WF["jobs"]:
        for u in uses(job):
            assert re.search(r"@v\d+$", u), u
    assert "--locked" in runs("test") and "--locked" in runs("core")


def test_dashboard_skill():
    """TST-UI-17: /berkshire:dashboard starts the server, gives the URL and TUI command, and says orders stay in Claude [REQ-UI-12]"""
    body = (ROOT / "skills" / "dashboard" / "SKILL.md").read_text()
    assert "berkshire web" in body and "berkshire tui" in body and "/berkshire:approve" in body
    assert re.search(r"^allowed-tools: Bash\(berkshire \*\)$", body, re.MULTILINE)


def test_views_state_orders_live_in_claude():
    """TST-UI-18: Both views say orders are placed only with /berkshire:approve [REQ-UI-07]"""
    assert "/berkshire:approve" in (ROOT / "webui" / "src" / "App.jsx").read_text()
    assert "/berkshire:approve" in (ROOT / "berkshire" / "tui.py").read_text()


def test_auto_start(tmp_path):
    """TST-UI-01: `berkshire web` starts a real server when none runs, and reuses it next time [REQ-UI-11, REQ-UI-01]"""
    env = {**os.environ, "BERKSHIRE_HOME": str(tmp_path / "home")}
    cmd = [sys.executable, "-m", "berkshire", "web"]
    first = json.loads(subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30, check=True).stdout)
    try:
        assert first["url"].startswith("http://127.0.0.1:") and "?t=" in first["url"]
        second = json.loads(subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30, check=True).stdout)
        assert second == first
    finally:
        os.kill(first["pid"], signal.SIGTERM)
        for _ in range(50):
            if not (tmp_path / "home" / "server.json").exists():
                break
            time.sleep(0.1)
    assert not (tmp_path / "home" / "server.json").exists()   # the registry is removed on shutdown


@pytest.mark.parametrize("path", ["berkshire/server.py", "berkshire/client.py"])
def test_no_trading_logic_in_views(path):
    """TST-UI-19: Server and client import no order-placing code; views only read the queue [REQ-UI-01, REQ-UI-07]"""
    src = (ROOT / path).read_text()
    assert "Queue(" not in src or ".load()" in src
    assert not re.search(r"\.mark\(|\.enqueue\(|place-trade|place_trade|prepare-trade", src)
