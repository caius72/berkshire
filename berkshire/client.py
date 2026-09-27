"""Client of the Berkshire API: discovery through ~/.berkshire/server.json, auto-start, JSON + SSE.

The terminal UI and `berkshire web` use it; it holds no trading logic (REQ-UI-01).
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time

from . import config
from .server import GUARD_HEADER, TOKEN_HEADER, registry_path


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def discover() -> dict | None:
    """The registered server if its process is alive and it answers /api/health."""
    try:
        info = json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not _alive(info.get("pid")):
        return None
    try:
        Client(info).get("/api/health", timeout=2)
    except (OSError, ApiError):
        return None
    return info


def ensure_server(wait: float = 10.0) -> dict:
    """A live server's registry entry, starting `berkshire serve` in the background if needed."""
    info = discover()
    if info:
        return info
    log = config.home() / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        subprocess.Popen(
            [sys.executable, "-m", "berkshire", "serve"],
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.2)
        if info := discover():
            return info
    raise RuntimeError(f"the Berkshire server did not start; see {log}")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class Client:
    def __init__(self, info: dict):
        self.port = int(info["port"])
        self.headers = {GUARD_HEADER: "1", TOKEN_HEADER: info.get("token", ""), "Host": f"127.0.0.1:{self.port}"}
        self._stream_sock = None

    def _request(self, method, path, body=None, timeout=10):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers, data = dict(self.headers), None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        if path == "/api/events":
            # Capture the socket BEFORE getresponse(): a streaming response hands it to the
            # response object and sets conn.sock = None, and close() must be able to shut it
            # from another thread, or quitting waits for the next keep-alive (mtui's lesson).
            self._stream_sock = conn.sock
        return conn, conn.getresponse()

    def get(self, path, timeout=10):
        return self._call("GET", path, None, timeout)

    def post(self, path, body, timeout=10):
        return self._call("POST", path, body, timeout)

    def _call(self, method, path, body, timeout):
        conn, resp = self._request(method, path, body, timeout)
        try:
            payload = json.loads(resp.read() or b"null")
        finally:
            conn.close()
        if resp.status >= 400:
            raise ApiError(resp.status, (payload or {}).get("error", "") if isinstance(payload, dict) else "")
        return payload

    def close(self):
        """Interrupt a blocking events() read in another thread."""
        import socket

        sock, self._stream_sock = self._stream_sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def events(self, stop=lambda: False):
        """Yield (event, data) from /api/events until `stop()` is true or the stream ends."""
        conn, resp = self._request("GET", "/api/events", timeout=None)
        try:
            event, data = "message", []
            while not stop():
                line = resp.readline()
                if not line:
                    return
                line = line.decode().rstrip("\r\n")
                if line.startswith(":"):
                    continue
                if not line:
                    if data:
                        yield event, json.loads("\n".join(data))
                    event, data = "message", []
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())
        finally:
            conn.close()
