"""Terminal view, driven through Textual's pilot against a real server thread."""

import threading

import pytest

pytest.importorskip("textual")

from conftest import new_run, run_all  # noqa: E402

from berkshire import config, server  # noqa: E402
from berkshire.client import Client  # noqa: E402
from berkshire.tui import BerkshireApp, ConfirmStop, NewAnalysis  # noqa: E402


@pytest.fixture
def served(tmp_path):
    spawned = []

    def spawn(argv, log):
        spawned.append(argv)
        log.write_text("")

        class P:
            pid = 1

            def poll(self):
                return None

        return P()

    api = server.Api(config.home(), spawn=spawn)
    httpd, info = server.serve(port=0, api=api, poll=0.05, dist=tmp_path, register=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield Client(info), spawned
    httpd.shutdown()
    httpd.server_close()


async def test_tui_shows_runs_and_progress(served, cfg, log):
    """TST-UI-13: TUI lists runs and shows team progress, signal and the latest report [REQ-UI-08, REQ-UI-03]"""
    client, _ = served
    run_all(new_run(cfg, log), log)
    app = BerkshireApp(client, url="http://127.0.0.1")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert len(app.runs) == 1 and app.selected == ("NVDA", "2026-09-18")
        progress = app.query_one("#progress")
        assert progress.row_count == 12
        assert "done" in str(progress.get_row_at(0)[2])
        assert "Buy" in str(app.query_one("#summary").render())
        assert app.query_one("#decisions").row_count == 1
        await pilot.press("r")
        await pilot.pause()
        assert app.query_one("#progress").row_count == 12


async def test_tui_live_update(served, cfg, log):
    """TST-UI-14: A run created while the TUI is open appears through the SSE stream [REQ-UI-04, REQ-UI-08]"""
    client, _ = served
    app = BerkshireApp(client)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert app.runs == []
        new_run(cfg, log, ticker="AMD")
        for _ in range(40):
            await pilot.pause(0.05)
            if app.runs:
                break
        assert [r["ticker"] for r in app.runs] == ["AMD"]


async def test_tui_new_analysis(served):
    """TST-UI-15: 'n' opens the form and submitting starts a job through the API [REQ-UI-06, REQ-UI-08]"""
    client, spawned = served
    app = BerkshireApp(client)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, NewAnalysis)
        app.screen.query_one("#ticker").value = "msft"
        await pilot.click("#start")
        await pilot.pause()
        assert spawned and "/berkshire:analyze MSFT" in spawned[0][2]
        assert app.query_one("#jobs").row_count == 1


async def test_tui_stop(served, cfg, log):
    """TST-UI-23: 's' asks first, then stops the selected running analysis; a finished one is refused [REQ-UI-13, REQ-UI-08]"""
    client, _ = served
    new_run(cfg, log, ticker="AMD")
    app = BerkshireApp(client)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmStop)
        await pilot.click("#keep")
        await pilot.pause()
        assert app.detail["summary"]["status"] == "running"
        await pilot.press("s")
        await pilot.pause()
        await pilot.click("#confirm-stop")
        await pilot.pause(0.3)
        assert client.get("/api/runs/AMD/2026-09-18")["summary"]["status"] == "stopped"
        app.load_detail()
        await pilot.press("s")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmStop)
