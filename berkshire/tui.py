"""Terminal view: a Textual client of the Berkshire API (REQ-UI-08).

Mirrors TradingAgents' live CLI panel (team progress, current report, message
timeline) and adds the decision log, order queue and jobs. It is a client
only (REQ-UI-01): everything it shows comes from the HTTP API, and live updates
come from the SSE stream. Needs the optional `tui` extra (textual).
"""

from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from . import data

STATUS_STYLE = {"done": "[green]✔ done[/]", "in progress": "[yellow]◐ in progress[/]", "pending": "[dim]○ pending[/]"}
SIGNAL_STYLE = {"Buy": "bold green", "Overweight": "green", "Hold": "yellow", "Underweight": "red",
                "Sell": "bold red", "REVIEW": "bold magenta"}


def signal_markup(signal: str | None) -> str:
    return f"[{SIGNAL_STYLE.get(signal, 'dim')}]{signal or '…'}[/]"


def run_label(r: dict) -> str:
    return f"{r['ticker']:<9} {r['date']}  {signal_markup(r['signal'])}  {r['done']}/{r['total']}"


class NewAnalysis(ModalScreen):
    """Form for POST /api/jobs (REQ-UI-06)."""

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            yield Label("New analysis", id="form-title")
            yield Input(placeholder="Ticker, e.g. NVDA, RHM.DE, BTC-USD", id="ticker")
            yield Input(value=data.today(), placeholder="YYYY-MM-DD", id="date")
            yield Input(value="market,social,news,fundamentals", id="analysts")
            yield Select([("Shallow (1 round)", "shallow"), ("Medium (3)", "medium"), ("Deep (5)", "deep")],
                         value="shallow", allow_blank=False, id="depth")
            with Horizontal(id="form-buttons"):
                yield Button("Start", variant="primary", id="start")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#start")
    @on(Input.Submitted)
    def start(self):
        self.dismiss({"ticker": self.query_one("#ticker", Input).value.strip(),
                      "date": self.query_one("#date", Input).value.strip(),
                      "analysts": [a.strip() for a in self.query_one("#analysts", Input).value.split(",") if a.strip()],
                      "depth": self.query_one("#depth", Select).value})


class ConfirmStop(ModalScreen):
    """Stopping cannot be undone except by running the analysis again, so it asks first."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, label: str):
        super().__init__()
        self.label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            yield Label(f"Stop the analysis of {self.label}?", id="form-title")
            yield Static("Its background job ends and no further agents run.")
            with Horizontal(id="form-buttons"):
                yield Button("Stop analysis", variant="error", id="confirm-stop")
                yield Button("Keep running", id="keep")

    @on(Button.Pressed, "#confirm-stop")
    def yes(self):
        self.dismiss(True)

    @on(Button.Pressed, "#keep")
    def no(self):
        self.dismiss(False)


class BerkshireApp(App):
    TITLE = "Berkshire"
    CSS = """
    #runs { width: 42; border: round $primary; }
    #main { width: 1fr; border: round $primary; }
    #summary { height: auto; padding: 0 1; }
    #sections { width: 26; }
    #report { width: 1fr; padding: 0 1; }
    #report-md { width: 1fr; }
    #job-log { height: 12; border: round $secondary; }
    #form { width: 64; height: auto; border: thick $primary; background: $surface; padding: 1 2; }
    #form-title { text-style: bold; }
    #form-buttons { height: auto; }
    NewAnalysis, ConfirmStop { align: center middle; }
    """
    BINDINGS = [Binding("n", "new", "New analysis"), Binding("s", "stop", "Stop analysis"),
                Binding("r", "refresh", "Refresh"), Binding("q", "quit", "Quit")]

    def __init__(self, client, url: str = ""):
        super().__init__()
        self.client, self.url = client, url
        self.runs: list[dict] = []
        self.selected: tuple[str, str] | None = None
        self.detail: dict | None = None
        self._stop = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="runs")
            with TabbedContent(id="main", initial="tab-progress"):
                with TabPane("Progress", id="tab-progress"):
                    yield Static(id="summary")
                    yield DataTable(id="progress", cursor_type="none")
                    yield DataTable(id="timeline", cursor_type="none")
                with TabPane("Reports", id="tab-reports"):
                    with Horizontal():
                        yield ListView(id="sections")
                        with VerticalScroll(id="report"):
                            yield Markdown(id="report-md")
                with TabPane("Decisions", id="tab-decisions"):
                    yield DataTable(id="decisions", cursor_type="row")
                with TabPane("Orders", id="tab-orders"):
                    yield Static("Orders are placed only from Claude with /berkshire:approve.", id="orders-note")
                    yield DataTable(id="orders", cursor_type="row")
                with TabPane("Jobs", id="tab-jobs"):
                    yield DataTable(id="jobs", cursor_type="row")
                    yield Static(id="job-log")
        yield Footer()

    def on_mount(self):
        self.sub_title = self.url
        self.query_one("#progress", DataTable).add_columns("Team", "Agent", "Status")
        self.query_one("#timeline", DataTable).add_columns("Time", "Step", "Chars")
        self.query_one("#decisions", DataTable).add_columns("Date", "Ticker", "Rating", "Raw", "Alpha", "Holding", "Status")
        self.query_one("#orders", DataTable).add_columns("Id", "Created", "Ticker", "Kind", "Rating", "Amount",
                                                         "Stop", "Account", "Status")
        self.query_one("#jobs", DataTable).add_columns("Id", "Ticker", "Date", "Status", "Started")
        self.refresh_all()
        self.watch_events()

    # --- data ---------------------------------------------------------------
    def refresh_all(self, keys: list[str] | None = None):
        keys = keys or ["runs", "memory", "queue", "jobs"]
        if any(k.startswith("run") for k in keys) or "runs" in keys:
            self.load_runs()
        if "memory" in keys:
            self.load_decisions()
        if "queue" in keys:
            self.load_orders()
        if "jobs" in keys:
            self.load_jobs()

    def load_runs(self):
        self.runs = self.client.get("/api/runs")
        lv = self.query_one("#runs", ListView)
        index = lv.index
        lv.clear()
        for r in self.runs:
            lv.append(ListItem(Label(run_label(r)), name=f"{r['ticker']}/{r['date']}"))
        if self.runs:
            if self.selected is None:
                self.selected = (self.runs[0]["ticker"], self.runs[0]["date"])
            lv.index = index if index is not None and index < len(self.runs) else 0
        self.load_detail()

    def load_detail(self):
        if not self.selected:
            self.query_one("#summary", Static).update("No runs yet. Press [b]n[/b] to start an analysis.")
            return
        self.detail = d = self.client.get(f"/api/runs/{self.selected[0]}/{self.selected[1]}")
        s = d["summary"]
        orders = d.get("orders") or {}
        intent = orders.get("intent")
        gate = (f"Order proposal: {intent['kind']} {intent.get('amount') or ''} stop {intent.get('stop_loss_rate')}"
                if intent else (f"Gate: {'; '.join(orders.get('reasons', []))}" if orders else "Gate: not run"))
        self.query_one("#summary", Static).update(
            f"[b]{s['ticker']}[/b] · {s['date']} · {s['asset_type']} · "
            f"{'[dim]stopped[/] · ' if s['status'] == 'stopped' else ''}signal {signal_markup(s['signal'])} · "
            f"{s['done']}/{s['total']} agents · {len(d['warnings'])} warnings\n{gate}")
        prog = self.query_one("#progress", DataTable)
        prog.clear()
        team = None
        for r in d["progress"]:  # team named once per group, like TradingAgents' progress panel
            prog.add_row(r["team"] if r["team"] != team else "", r["agent"], STATUS_STYLE.get(r["status"], r["status"]))
            team = r["team"]
        tl = self.query_one("#timeline", DataTable)
        tl.clear()
        for t in reversed(d["timeline"]):
            tl.add_row(t["at"][11:] or "--:--", t["step"], str(t.get("chars", "")))
        sec = self.query_one("#sections", ListView)
        sec.clear()
        for i, section in enumerate(d["sections"]):
            sec.append(ListItem(Label(section["agent"]), name=str(i)))
        if d["sections"]:
            self.show_section(len(d["sections"]) - 1)  # latest report, like TradingAgents' "current report"

    def show_section(self, i: int):
        section = self.detail["sections"][i]
        self.query_one("#report-md", Markdown).update(f"## {section['agent']}\n\n{section['text']}")

    def load_decisions(self):
        t = self.query_one("#decisions", DataTable)
        t.clear()
        for e in self.client.get("/api/memory"):
            t.add_row(e["date"], e["ticker"], signal_markup(e["rating"]), e["raw"] or "", e["alpha"] or "",
                      e["holding"] or "", "pending" if e["pending"] else f"resolved {e['resolved'] or ''}")

    def load_orders(self):
        t = self.query_one("#orders", DataTable)
        t.clear()
        for q in self.client.get("/api/queue"):
            i = q["intent"]
            t.add_row(q["id"], q["created"][:16], i.get("etoro_symbol", ""), i.get("kind", ""), i.get("rating", ""),
                      str(i.get("amount", "")), str(i.get("stop_loss_rate", "")), i.get("account", ""), q["status"])

    def load_jobs(self):
        t = self.query_one("#jobs", DataTable)
        t.clear()
        jobs = self.client.get("/api/jobs")
        for j in jobs:
            t.add_row(j["id"], j["ticker"], j["date"], j["status"], j["started"][11:])
        self.query_one("#job-log", Static).update(jobs[0]["log_tail"][-1500:] if jobs else "")

    # --- events -------------------------------------------------------------
    @on(ListView.Selected, "#runs")
    def pick_run(self, event: ListView.Selected):
        ticker, date = event.item.name.split("/")
        self.selected = (ticker, date)
        self.load_detail()

    @on(ListView.Selected, "#sections")
    def pick_section(self, event: ListView.Selected):
        self.show_section(int(event.item.name))

    def action_refresh(self):
        self.refresh_all()

    def action_new(self):
        def started(form):
            if not form:
                return
            try:
                job = self.client.post("/api/jobs", form)
                self.notify(f"Started {job['ticker']} {job['date']} (job {job['id']})")
                self.load_jobs()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self.notify(str(exc), severity="error")
        self.push_screen(NewAnalysis(), started)

    def action_stop(self):
        run = self.detail and self.detail["summary"]
        if not run or run["status"] != "running":
            self.notify("The selected analysis is not running.", severity="warning")
            return

        def confirmed(yes):
            if not yes:
                return
            try:
                res = self.client.post(f"/api/runs/{run['ticker']}/{run['date']}/stop", {"reason": "stopped from the terminal view"})
                jobs = f", job {', '.join(res['jobs_stopped'])} ended" if res["jobs_stopped"] else ""
                self.notify(f"Stopped {run['ticker']} {run['date']}{jobs}")
                self.refresh_all()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self.notify(str(exc), severity="error")
        self.push_screen(ConfirmStop(f"{run['ticker']} {run['date']}"), confirmed)

    @work(thread=True, exclusive=True)
    def watch_events(self):
        try:
            for event, data in self.client.events(stop=lambda: self._stop):
                if event == "change":
                    self.call_from_thread(self.refresh_all, data["keys"])
        except Exception:  # noqa: BLE001 - server gone; the view stays usable with r
            return

    def on_unmount(self):
        self._stop = True
        if hasattr(self.client, "close"):
            self.client.close()


def main() -> int:
    from .client import Client, ensure_server
    info = ensure_server()
    BerkshireApp(Client(info), url=info["url"].split("?")[0]).run()
    return 0
