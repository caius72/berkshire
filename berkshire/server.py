"""Local HTTP + SSE API over ~/.berkshire, shared by the web page and the terminal UI (REQ-UI).

Same shape as matlab-engine-mcp's webui_server.py: one process owns the state,
and every view is a client of this API (R-0 there, REQ-UI-01 here).

Locked down because it can start analyses (which spawn Claude):
  * Bound to 127.0.0.1 only; the Host header must be loopback (DNS rebinding).
  * No CORS. The page is served same-origin from webui/dist (or the Vite proxy).
  * Every /api request needs `X-WebUI: 1` (forces a preflight, which is refused)
    and the per-process token in `X-WebUI-Token`. The token is the only check that
    authenticates a non-browser caller; it reaches the page once as `?t=` and the
    TUI through the 0600 registry file ~/.berkshire/server.json.
  * It never places orders: eToro's per-order approval lives in a Claude session
    (/berkshire:approve), so the API only reads the queue (REQ-UI-07).

Routing, the guard, static-path mapping and change detection are pure functions
so they unit-test without a socket.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import backtest, config, pipeline
from .memory import DecisionLog
from .orders import Queue

GUARD_HEADER, TOKEN_HEADER = "X-WebUI", "X-WebUI-Token"
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
DIST = Path(__file__).resolve().parents[1] / "webui" / "dist"
MAX_BODY = 64 * 1024
_CTYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
           ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json", ".map": "application/json"}
DEFAULT_PORT = 8787


# --- guard (REQ-UI-02) ------------------------------------------------------

def host_ok(host: str | None) -> bool:
    if not host:
        return False
    name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
    return name in _LOOPBACK


def authorized(headers, token: str) -> bool:
    return (headers.get(GUARD_HEADER) == "1" and bool(token)
            and hmac.compare_digest(headers.get(TOKEN_HEADER, ""), token))


def static_path(dist: Path, urlpath: str) -> Path:
    """Map a URL to a file under dist; anything escaping dist falls back to index.html."""
    rel = unquote(urlparse(urlpath).path).lstrip("/") or "index.html"
    full = (dist / rel).resolve()
    root = dist.resolve()
    return full if full == root or root in full.parents else root / "index.html"


# --- state access -------------------------------------------------------------

def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Api:
    """Read model over BERKSHIRE_HOME plus the job runner. `spawn(argv, log_path)`
    is injectable so tests never start Claude."""

    def __init__(self, home: Path | None = None, spawn=None):
        self.home = Path(home or config.home())
        self.spawn = spawn or _spawn_detached
        self._jobs: dict[str, dict] = {}
        self._procs: dict[str, object] = {}

    # paths
    @property
    def runs_dir(self):
        return self.home / "runs"

    def _state_files(self):
        return sorted(self.runs_dir.glob("*/*/state.json")) if self.runs_dir.exists() else []

    # reads
    def runs(self) -> list[dict]:
        out = []
        for f in self._state_files():
            state = _read_json(f)
            if state:
                out.append({**pipeline.summary(state), "updated": datetime.fromtimestamp(f.stat().st_mtime)
                            .isoformat(timespec="seconds")})
        return sorted(out, key=lambda r: (r["date"], r["updated"]), reverse=True)

    def run(self, ticker: str, date: str) -> dict | None:
        rdir = self.runs_dir / config.safe_component(ticker) / config.safe_component(date)
        state = _read_json(rdir / "state.json")
        if not state:
            return None
        return {"summary": pipeline.summary(state), "progress": pipeline.progress_rows(state),
                "sections": pipeline.report_sections(state), "timeline": state.get("timeline") or [{"step": c, "at": ""} for c in state["completed"]],
                "warnings": state.get("warnings", []), "structured": state.get("structured", {}),
                "instrument_context": state.get("instrument_context", ""), "config": state.get("config", {}),
                "analysts": state.get("analysts", []), "orders": _read_json(rdir / "orders.json"),
                "report": state.get("report")}

    def memory(self) -> list[dict]:
        return list(reversed(DecisionLog(self.home / "memory" / "trading_memory.md").entries()))

    def queue(self) -> list[dict]:
        return list(reversed(Queue(self.home / "queue.json").load()))

    def backtests(self) -> list[dict]:
        base = self.home / "backtest"
        out = []
        for d in sorted(base.iterdir()) if base.exists() else []:
            log = DecisionLog(d / "memory" / "trading_memory.md")
            out.append({"run_id": d.name, **backtest.summarize(log)})
        return out

    # jobs (REQ-UI-06)
    def start_job(self, body: dict) -> dict:
        ticker = config.safe_component(str(body.get("ticker", "")).strip().upper())
        date = pipeline.validate_date(str(body.get("date") or datetime.now().strftime("%Y-%m-%d")))
        args = [ticker, date]
        if body.get("analysts"):
            chosen = pipeline.select_analysts(list(body["analysts"]), pipeline.detect_asset_type(ticker))
            args += ["--analysts", ",".join(chosen)]
        if body.get("depth"):
            if str(body["depth"]).lower() not in pipeline.DEPTH:
                raise ValueError(f"depth must be one of {', '.join(pipeline.DEPTH)}")
            args += ["--depth", str(body["depth"]).lower()]
        job_id = uuid.uuid4().hex[:8]
        log = self.home / "jobs" / f"{job_id}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        prompt = "/berkshire:analyze " + " ".join(args) + " (headless: do not ask questions; skip step 5)"
        argv = ["claude", "-p", prompt, "--allowedTools",
                "Bash(berkshire *) Bash(date *) Read Write Agent"]
        proc = self.spawn(argv, log)
        job = {"id": job_id, "ticker": ticker, "date": date, "args": args, "log": str(log),
               "started": datetime.now().isoformat(timespec="seconds"), "pid": getattr(proc, "pid", None)}
        self._jobs[job_id], self._procs[job_id] = job, proc
        config.atomic_write(log.with_suffix(".json"), json.dumps(job, indent=2))
        return self.job(job_id)

    def job(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id) or _read_json(self.home / "jobs" / f"{config.safe_component(job_id)}.json")
        if not job:
            return None
        proc = self._procs.get(job_id)
        code = proc.poll() if proc is not None and hasattr(proc, "poll") else None
        status = "running" if proc is not None and code is None else ("exited" if proc is None else
                                                                          ("done" if code == 0 else f"failed ({code})"))
        try:
            tail = Path(job["log"]).read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError:
            tail = ""
        return {**job, "status": status, "log_tail": tail}

    def jobs(self) -> list[dict]:
        ids = set(self._jobs)
        jdir = self.home / "jobs"
        ids |= {p.stem for p in jdir.glob("*.json")} if jdir.exists() else set()
        return sorted((self.job(i) for i in ids), key=lambda j: j["started"], reverse=True)

    # change detection for SSE (REQ-UI-04)
    def snapshot(self) -> dict[str, float]:
        snap = {f"run:{f.parent.parent.name}/{f.parent.name}": f.stat().st_mtime for f in self._state_files()}
        for key, rel in (("memory", "memory/trading_memory.md"), ("queue", "queue.json")):
            p = self.home / rel
            if p.exists():
                snap[key] = p.stat().st_mtime
        jdir = self.home / "jobs"
        if jdir.exists():
            snap["jobs"] = max((p.stat().st_mtime for p in jdir.iterdir()), default=0.0)
        return snap


def changed(prev: dict, cur: dict) -> list[str]:
    """Keys added, removed or modified between two snapshots."""
    return sorted(k for k in prev.keys() | cur.keys() if prev.get(k) != cur.get(k))


def _spawn_detached(argv, log_path: Path):
    log = open(log_path, "ab")  # noqa: SIM115 - the child owns it
    return subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True, cwd=str(Path.home()))


# --- routing (pure) -----------------------------------------------------------

def route(method: str, path: str, body: dict | None, api: Api) -> tuple[int, object]:
    parts = [unquote(p) for p in urlparse(path).path.strip("/").split("/")][1:]  # drop "api"
    try:
        if method == "GET":
            if parts == ["health"]:
                return 200, {"ok": True, "home": str(api.home)}
            if parts == ["runs"]:
                return 200, api.runs()
            if len(parts) == 3 and parts[0] == "runs":
                run = api.run(parts[1], parts[2])
                return (200, run) if run else (404, {"error": "no such run"})
            if parts == ["memory"]:
                return 200, api.memory()
            if parts == ["queue"]:
                return 200, api.queue()
            if parts == ["backtests"]:
                return 200, api.backtests()
            if parts == ["config"]:
                return 200, config.load()
            if parts == ["jobs"]:
                return 200, api.jobs()
            if len(parts) == 2 and parts[0] == "jobs":
                job = api.job(parts[1])
                return (200, job) if job else (404, {"error": "no such job"})
        if method == "POST" and parts == ["jobs"]:
            return 201, api.start_job(body or {})
    except ValueError as exc:
        return 400, {"error": str(exc)}
    return 404, {"error": f"no route for {method} {path}"}


# --- HTTP -------------------------------------------------------------------

def _make_handler(api: Api, token: str, dist: Path, poll: float):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _write(self, status, ctype, payload: bytes):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status, obj):
            self._write(status, "application/json", json.dumps(obj, default=str, ensure_ascii=False).encode())

        def _guarded(self) -> bool:
            if not host_ok(self.headers.get("Host")) or not authorized(self.headers, token):
                self._json(403, {"error": "forbidden: missing guard header or stale token"})
                return False
            return True

        def do_OPTIONS(self):  # no CORS, ever
            self._json(403, {"error": "cross-origin requests are not allowed"})

        def do_GET(self):
            if not self.path.startswith("/api/"):
                return self._static()
            if not self._guarded():
                return
            if urlparse(self.path).path == "/api/events":
                return self._events()
            self._json(*route("GET", self.path, None, api))

        def do_POST(self):
            if not self.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if not self._guarded():
                return
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"error": "body too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"error": "invalid JSON"})
            self._json(*route("POST", self.path, body, api))

        def _events(self):
            """SSE: a `hello`, then a `change` event listing changed keys (REQ-UI-04)."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            prev, beat = api.snapshot(), time.monotonic()
            try:
                self.wfile.write(f"event: hello\ndata: {json.dumps({'keys': sorted(prev)})}\n\n".encode())
                self.wfile.flush()
                while True:
                    time.sleep(poll)
                    cur = api.snapshot()
                    keys = changed(prev, cur)
                    if keys:
                        self.wfile.write(f"event: change\ndata: {json.dumps({'keys': keys})}\n\n".encode())
                        prev, beat = cur, time.monotonic()
                    elif time.monotonic() - beat > 15:
                        self.wfile.write(b": keep-alive\n\n")
                        beat = time.monotonic()
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def _static(self):
            target = static_path(dist, self.path)
            if not target.is_file():
                if not (dist / "index.html").is_file():
                    return self._write(200, "text/html", (
                        b"<h1>Berkshire</h1><p>The web UI is not built. Run <code>npm ci && npm run build</code> "
                        b"in <code>webui/</code>, or use <code>berkshire tui</code>.</p>"))
                target = dist / "index.html"
            self._write(200, _CTYPES.get(target.suffix, "application/octet-stream"), target.read_bytes())

        def log_message(self, *args):  # quiet
            pass

    return Handler


def registry_path() -> Path:
    return config.home() / "server.json"


def serve(port: int = DEFAULT_PORT, api: Api | None = None, tries: int = 20, poll: float = 1.0,
          dist: Path = DIST, register: bool = True):
    """Bind the first free port from `port`, write the registry, return (httpd, info)."""
    api = api or Api()
    token = secrets.token_urlsafe(24)
    last = None
    for p in range(port, port + tries) if port else [0]:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), _make_handler(api, token, dist, poll))
            break
        except OSError as exc:
            last = exc
    else:
        raise OSError(f"no free port in {port}..{port + tries - 1}: {last}")
    httpd.daemon_threads = True
    bound = httpd.server_address[1]
    info = {"pid": os.getpid(), "port": bound, "token": token, "url": f"http://127.0.0.1:{bound}/?t={token}",
            "started": datetime.now().isoformat(timespec="seconds"), "home": str(api.home)}
    if register:
        reg = registry_path()
        config.atomic_write(reg, json.dumps(info, indent=2))
        os.chmod(reg, 0o600)
    return httpd, info


def run_forever(port: int = DEFAULT_PORT) -> None:
    httpd, info = serve(port)
    print(json.dumps({k: info[k] for k in ("url", "port", "pid")}), flush=True)

    def stop(*_):
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        reg = registry_path()
        if (_read_json(reg) or {}).get("pid") == os.getpid():
            reg.unlink(missing_ok=True)
