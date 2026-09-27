"""Local API server: guard, routes, jobs, SSE change detection, static serving, client."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import new_run, run_all

from berkshire import config, server
from berkshire.client import ApiError, Client, discover


class FakeProc:
    pid = 4242

    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


@pytest.fixture
def spawned():
    return []


@pytest.fixture
def killed():
    return []


@pytest.fixture
def api(spawned, killed):
    def spawn(argv, log):
        spawned.append(argv)
        Path(log).write_text("analysis started\n")
        return FakeProc()
    return server.Api(config.home(), spawn=spawn, kill=lambda job: killed.append(job["id"]))


@pytest.fixture
def live(api, tmp_path):
    """A real server on an ephemeral port; yields (info, client)."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=root>berkshire page</div>")
    httpd, info = server.serve(port=0, api=api, poll=0.05, dist=dist)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield info, Client(info)
    httpd.shutdown()
    httpd.server_close()


def raw(info, path, headers=None, method="GET", body=None):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    out = resp.status, dict(resp.getheaders()), resp.read()
    conn.close()
    return out


def test_guard_rules():
    """TST-UI-02: API needs loopback Host, X-WebUI and the token; no CORS [REQ-UI-02]"""
    assert server.host_ok("127.0.0.1:8787") and server.host_ok("localhost") and server.host_ok("[::1]:8787")
    assert not server.host_ok("evil.example:8787") and not server.host_ok(None)
    ok = {"X-WebUI": "1", "X-WebUI-Token": "tok"}
    assert server.authorized(ok, "tok")
    assert not server.authorized({**ok, "X-WebUI": "0"}, "tok")
    assert not server.authorized({**ok, "X-WebUI-Token": "bad"}, "tok")
    assert not server.authorized(ok, "")


def test_guard_over_http(live):
    """TST-UI-03: Unauthenticated, cross-origin and rebinding requests get 403; page is ungated [REQ-UI-02]"""
    info, _ = live
    good = {"X-WebUI": "1", "X-WebUI-Token": info["token"]}
    assert raw(info, "/api/runs")[0] == 403
    assert raw(info, "/api/runs", {"X-WebUI": "1", "X-WebUI-Token": "stale"})[0] == 403
    assert raw(info, "/api/runs", {**good, "Host": "attacker.example"})[0] == 403
    status, headers, _ = raw(info, "/api/runs", method="OPTIONS")
    assert status == 403 and not any(h.lower().startswith("access-control") for h in headers)
    status, headers, _ = raw(info, "/api/runs", good)
    assert status == 200 and not any(h.lower().startswith("access-control") for h in headers)
    assert raw(info, "/api/jobs", method="POST", body=b"{}")[0] == 403
    assert b"berkshire page" in raw(info, "/")[2]


def test_registry_file(live):
    """TST-UI-04: The registry holds port, token and pid with 0600 permissions [REQ-UI-01, REQ-UI-02]"""
    info, _ = live
    reg = server.registry_path()
    assert json.loads(reg.read_text())["token"] == info["token"]
    assert oct(reg.stat().st_mode & 0o777) == "0o600"
    assert info["url"] == f"http://127.0.0.1:{info['port']}/?t={info['token']}"


def test_run_routes(cfg, log, api):
    """TST-UI-05: Runs list with progress summary; run detail with floor, sections, timeline, orders [REQ-UI-03, REQ-UI-05]"""
    run_all(new_run(cfg, log), log)
    partial = new_run(cfg, log, ticker="AAPL", analysts=["market"])
    from berkshire import pipeline
    pipeline.submit(partial, "analyst_market", "Market report")
    status, runs = server.route("GET", "/api/runs", None, api)
    assert status == 200 and sorted(r["ticker"] for r in runs) == ["AAPL", "NVDA"]
    nvda = next(r for r in runs if r["ticker"] == "NVDA")
    assert (nvda["signal"], nvda["done"], nvda["total"], nvda["complete"]) == ("Buy", 12, 12, True)
    aapl = next(r for r in runs if r["ticker"] == "AAPL")
    assert aapl["current"] == ["bull_1"] and aapl["done"] == 1
    status, d = server.route("GET", "/api/runs/NVDA/2026-09-18", None, api)
    assert status == 200 and len(d["progress"]) == 12 and d["sections"][-1]["agent"] == "Portfolio Manager"
    assert [t["step"] for t in d["timeline"]][:2] == ["analyst_market", "analyst_social"]
    assert {r["agent"] for r in d["progress"] if r["team"] == "Analyst Team"} >= {"Sentiment", "Market"}
    assert server.route("GET", "/api/runs/NVDA/2020-01-01", None, api)[0] == 404
    assert server.route("GET", "/api/runs/..%2F..%2Fetc/x", None, api)[0] == 400
    assert server.route("GET", "/api/nope", None, api)[0] == 404


def test_memory_queue_backtests(cfg, log, api):
    """TST-UI-06: Decision log, order queue and backtest summaries are exposed read-only [REQ-UI-03, REQ-UI-07]"""
    run_all(new_run(cfg, log), log)
    from berkshire.orders import Queue
    Queue(config.home() / "queue.json").enqueue([{"etoro_symbol": "NVDA", "kind": "open", "rating": "Buy"}], "t", 5)
    (config.home() / "backtest" / "bt1" / "memory").mkdir(parents=True)
    assert server.route("GET", "/api/memory", None, api)[1][0]["rating"] == "Buy"
    assert server.route("GET", "/api/queue", None, api)[1][0]["status"] == "pending"
    assert server.route("GET", "/api/backtests", None, api)[1][0]["run_id"] == "bt1"
    for path in ("/api/queue", "/api/orders", "/api/queue/approve"):   # no write path to orders exists
        assert server.route("POST", path, {}, api)[0] == 404


def test_start_job(api, spawned):
    """TST-UI-07: POST /api/jobs validates input and spawns a headless /berkshire:analyze [REQ-UI-06]"""
    status, job = server.route("POST", "/api/jobs", {"ticker": "nvda", "date": "2026-09-18",
                                                     "analysts": ["news", "market"], "depth": "Medium"}, api)
    assert status == 201 and job["status"] == "running" and job["log_tail"] == "analysis started\n"
    argv = spawned[0]
    assert argv[:2] == ["claude", "-p"] and argv[2].startswith("/berkshire:analyze NVDA 2026-09-18 --analysts market,news --depth medium")
    assert "place-trade" not in " ".join(argv) and "Bash(berkshire *)" in argv[-1]
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk" and "--strict-mcp-config" in argv
    assert {"WebSearch", "WebFetch"} <= set(argv[-1].split()) and "mcp__" not in " ".join(argv)
    assert server.route("GET", f"/api/jobs/{job['id']}", None, api)[1]["ticker"] == "NVDA"
    assert server.route("GET", "/api/jobs", None, api)[1][0]["id"] == job["id"]
    for bad, msg in (({"ticker": "../x"}, "unsafe"), ({"ticker": "NVDA", "date": "2099-01-01"}, "future"),
                     ({"ticker": "NVDA", "analysts": ["astrology"]}, "unknown analyst"),
                     ({"ticker": "NVDA", "depth": "extreme"}, "depth")):
        status, err = server.route("POST", "/api/jobs", bad, api)
        assert status == 400 and msg in err["error"]
    assert len(spawned) == 1
    # No date given: the job uses the engine's clock (the one validation uses), not the system's.
    from conftest import TODAY
    assert server.route("POST", "/api/jobs", {"ticker": "AMD"}, api)[1]["date"] == TODAY
    api._procs[job["id"]] = FakeProc(code=1)
    assert api.job(job["id"])["status"] == "failed (1)"


def test_change_detection(cfg, log, api):
    """TST-UI-08: Snapshots detect new runs, submitted steps, log and queue changes [REQ-UI-04]"""
    import os
    before = api.snapshot()
    state = new_run(cfg, log)
    after = api.snapshot()
    assert server.changed(before, after) == ["run:NVDA/2026-09-18"]
    from berkshire import pipeline
    pipeline.submit(state, "analyst_market", "x")
    sf = Path(state["run_dir"]) / "state.json"
    os.utime(sf, (sf.stat().st_atime, sf.stat().st_mtime + 5))
    assert server.changed(after, api.snapshot()) == ["run:NVDA/2026-09-18"]
    assert server.changed({"queue": 1.0}, {}) == ["queue"]


def test_sse_stream(live, cfg, log):
    """TST-UI-09: /api/events sends hello, then a change event when a run appears [REQ-UI-04]"""
    info, client = live
    events = client.events()
    event, data = next(events)
    assert event == "hello"
    new_run(cfg, log)
    event, data = next(events)
    assert event == "change" and "run:NVDA/2026-09-18" in data["keys"]
    events.close()


def test_static_paths(tmp_path):
    """TST-UI-10: Static files resolve inside dist only; traversal falls back to index.html [REQ-UI-02]"""
    assert server.inside(tmp_path, "a", "b.json") == (tmp_path / "a" / "b.json").resolve()
    for evil in (("..", "x"), ("a/../../x",), ("/etc/passwd",)):
        with pytest.raises(ValueError, match="escapes"):
            server.inside(tmp_path, *evil)
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    assert server.static_path(dist, "/") == (dist / "index.html").resolve()
    assert server.static_path(dist, "/assets/a.js?v=1") == (dist / "assets" / "a.js").resolve()
    for evil in ("/../secret", "/%2e%2e/%2e%2e/etc/passwd", "/assets/../../x"):
        assert server.static_path(dist, evil) == (dist / "index.html").resolve()


def test_unbuilt_page_hint(api, tmp_path):
    """TST-UI-11: Without a built bundle the page explains how to build it or use the TUI [REQ-UI-10]"""
    httpd, info = server.serve(port=0, api=api, dist=tmp_path / "missing", register=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        body = raw(info, "/")[2].decode()
        assert "npm ci && npm run build" in body and "berkshire tui" in body
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_client_and_discovery(live, cfg, log):
    """TST-UI-12: The client finds the server via the registry and reads/writes through the API [REQ-UI-01]"""
    info, client = live
    assert discover()["port"] == info["port"]
    run_all(new_run(cfg, log), log)
    assert client.get("/api/runs")[0]["signal"] == "Buy"
    with pytest.raises(ApiError) as exc:
        client.post("/api/jobs", {"ticker": "../x"})
    assert exc.value.status == 400
    server.registry_path().write_text(json.dumps({**info, "pid": 999999}))
    assert discover() is None


def test_stop_from_api(cfg, log, api, killed):
    """TST-UI-21: POST /api/runs/T/D/stop marks the run stopped and ends only its running job [REQ-UI-13]"""
    state = new_run(cfg, log)
    _, mine = server.route("POST", "/api/jobs", {"ticker": "NVDA", "date": "2026-09-18"}, api)
    _, other = server.route("POST", "/api/jobs", {"ticker": "AMD", "date": "2026-09-18"}, api)
    status, res = server.route("POST", "/api/runs/NVDA/2026-09-18/stop", {"reason": "wrong ticker"}, api)
    assert status == 200 and res["jobs_stopped"] == [mine["id"]] and killed == [mine["id"]]
    assert res["summary"]["status"] == "stopped" and res["stopped"]["reason"] == "wrong ticker"
    assert api.job(mine["id"])["status"] == "stopped" and api.job(other["id"])["status"] == "running"
    assert json.loads(Path(mine["log"]).with_suffix(".json").read_text())["stopped"]
    assert server.route("GET", "/api/runs/NVDA/2026-09-18", None, api)[1]["stopped"]["reason"] == "wrong ticker"
    assert server.route("POST", "/api/runs/NVDA/2026-09-18/stop", {}, api)[0] == 200   # idempotent
    assert killed == [mine["id"]]
    assert server.route("POST", "/api/runs/ZZZ/2026-09-18/stop", {}, api)[0] == 404
    from berkshire import pipeline
    done = run_all(new_run(cfg, log, ticker="AAPL"), log)
    assert server.route("POST", f"/api/runs/AAPL/{done['trade_date']}/stop", {}, api)[0] == 400
    assert not state.get("stopped") and pipeline.load_state(Path(state["run_dir"]))["stopped"]


def test_start_job_resolves_and_refuses_unlisted(api, spawned):
    """TST-UI-22: The start form maps eToro names and refuses unlisted instruments before spawning [REQ-IF-10, REQ-UI-06]"""
    import pandas as pd
    from conftest import FakeTicker
    status, job = server.route("POST", "/api/jobs", {"ticker": "EuroOil", "date": "2026-09-18"}, api)
    assert status == 201 and job["ticker"] == "BZ=F" and "/berkshire:analyze BZ=F 2026-09-18" in spawned[0][2]
    FakeTicker.frames["NOPE"] = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex([]))
    status, err = server.route("POST", "/api/jobs", {"ticker": "NOPE", "date": "2026-09-18"}, api)
    assert status == 400 and "symbol_map" in err["error"] and len(spawned) == 1


def test_duplicate_running_job_refused(api, spawned):
    """TST-UI-25: A second start for a (ticker, date) whose job is still running is refused [REQ-UI-06]"""
    _, first = server.route("POST", "/api/jobs", {"ticker": "BZ=F", "date": "2026-09-18"}, api)
    status, err = server.route("POST", "/api/jobs", {"ticker": "EuroOil", "date": "2026-09-18"}, api)
    assert status == 400 and "already running" in err["error"] and first["id"] in err["error"]
    assert len(spawned) == 1
    assert server.route("POST", "/api/jobs", {"ticker": "BZ=F", "date": "2026-09-17"}, api)[0] == 201
    api._procs[first["id"]] = FakeProc(code=0)
    assert server.route("POST", "/api/jobs", {"ticker": "BZ=F", "date": "2026-09-18"}, api)[0] == 201
    assert len(spawned) == 3


def test_job_timeout(api, spawned, killed, cfg, log):
    """TST-UI-26: A dashboard job past job_timeout_minutes is ended once, its run marked stopped, and a restart is accepted [REQ-UI-14]"""
    new_run(cfg, log)  # NVDA 2026-09-18, unfinished
    old = server.route("POST", "/api/jobs", {"ticker": "NVDA", "date": "2026-09-18"}, api)[1]
    fresh = server.route("POST", "/api/jobs", {"ticker": "NVDA", "date": "2026-09-17"}, api)[1]
    api._jobs[old["id"]]["started"] = (datetime.now() - api.timeout - timedelta(minutes=1)).isoformat(timespec="seconds")
    assert {j["id"]: j["status"] for j in api.jobs()} == {old["id"]: "timed out", fresh["id"]: "running"}
    assert api.job(old["id"])["status"] == "timed out" and killed == [old["id"]]  # killed once
    stopped = server.route("GET", "/api/runs/NVDA/2026-09-18", None, api)[1]["stopped"]
    assert stopped["reason"] == f"timed out after {config.load()['job_timeout_minutes']} min"
    assert server.route("POST", "/api/jobs", {"ticker": "NVDA", "date": "2026-09-18"}, api)[0] == 201
    assert len(spawned) == 3
