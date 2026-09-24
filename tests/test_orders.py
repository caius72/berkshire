"""Risk gate (rating -> order intent) and the approval queue."""

import json
from datetime import datetime, timedelta

import pytest

from berkshire import config, orders
from berkshire.cli import main
from conftest import new_run, run_all

BOOK = {"equity": 100_000.0, "cash": 60_000.0, "currency": "USD", "positions": [
    {"ticker": "NVDA", "etoro_symbol": "NVDA", "quantity": 20, "value": 4_000.0,
     "position_ids": [{"id": 11, "units": 12.0}, {"id": 12, "units": 8.0}]}]}


def gate(rating, book=BOOK, ask=200.0, trader=None, pm=None, atr=5.0, ticker="NVDA", **cfg_over):
    cfg = {**config.DEFAULTS, **cfg_over}
    return orders.gate(ticker=ticker, etoro_symbol=ticker, instrument_id=1137, rating=rating, portfolio=book,
                       ask=ask, trader=trader, pm=pm, atr=atr, cfg=cfg)


def test_rating_map():
    """TST-RISK-01: Buy -> full target, Overweight -> half, Underweight -> close half, Sell -> close all, Hold/REVIEW -> none [REQ-RISK-01]"""
    assert gate("Buy", ticker="AMD")["intent"]["amount"] == 5_000.0
    assert gate("Overweight", ticker="AMD")["intent"]["amount"] == 2_500.0
    uw = gate("Underweight")["intent"]
    assert uw["kind"] == "close" and uw["closes"] == [{"position_id": 11, "units_to_deduct": 6.0},
                                                      {"position_id": 12, "units_to_deduct": 4.0}]
    sell = gate("Sell")["intent"]
    assert [c["units_to_deduct"] for c in sell["closes"]] == [None, None]
    for r in ("Hold", "REVIEW", "Strong Buy"):
        assert gate(r)["intent"] is None
    assert "human review" in gate("REVIEW")["reasons"][0]
    assert gate("Sell", ticker="AMD")["intent"] is None          # nothing held


@pytest.mark.parametrize("over,book,expected,binding", [
    ({}, BOOK, 1_000.0, "distance to target"),                                   # NVDA held at 4k, target 5k
    ({"target_weight": 0.5}, BOOK, 5_000.0, "max_order_pct"),
    ({"target_weight": 0.5, "max_order_pct": 1.0, "max_instrument_pct": 0.08}, BOOK, 4_000.0, "max_instrument_pct"),
    ({"target_weight": 0.5, "max_order_pct": 1.0}, {**BOOK, "cash": 12_000.0}, 2_000.0, "min_cash_pct")])
def test_sizing_caps(over, book, expected, binding):
    """TST-RISK-02: Amount is the smallest of target gap, order cap, instrument cap and cash floor [REQ-RISK-02]"""
    res = gate("Buy", book=book, **over)
    assert res["intent"]["amount"] == expected and binding in res["reasons"][0]


def test_below_minimum_and_missing_inputs():
    """TST-RISK-03: Tiny amounts, unknown equity or no ask produce no order [REQ-RISK-02]"""
    full = {**BOOK, "positions": [{**BOOK["positions"][0], "value": 4_990.0}]}
    assert "below min_order_amount" in gate("Buy", book=full)["reasons"][0]
    assert gate("Buy", book={"positions": []})["intent"] is None
    assert gate("Buy", ask=None)["intent"] is None


def test_stop_loss_rules():
    """TST-RISK-04: Stop = valid Trader stop, else ask - k*ATR, else veto [REQ-RISK-03]"""
    assert gate("Buy", ticker="AMD", trader={"stop_loss": 190.0})["intent"]["stop_loss_rate"] == 190.0
    fallback = gate("Buy", ticker="AMD", trader={"stop_loss": 205.0}, atr=4.0)
    assert fallback["intent"]["stop_loss_rate"] == 192.0 and "ignored" in " ".join(fallback["reasons"])
    assert gate("Buy", ticker="AMD", atr=5.0, atr_stop_multiple=3.0)["intent"]["stop_loss_rate"] == 185.0
    veto = gate("Buy", ticker="AMD", trader=None, atr=None)
    assert veto["intent"] is None and "veto" in veto["reasons"][-1]
    assert gate("Buy", ticker="AMD", ask=5.0, atr=4.0)["intent"] is None     # stop would be <= 0


def test_long_only_unleveraged():
    """TST-RISK-05: Every opening intent is a leverage-1 buy; no rating produces a short [REQ-RISK-04]"""
    for r in ("Buy", "Overweight", "Underweight", "Sell", "Hold"):
        i = gate(r, ticker="AMD")["intent"]
        assert i is None or (i["direction"] == "buy" and i["leverage"] == 1)


def test_take_profit():
    """TST-RISK-06: Take-profit is the PM price target only when above the ask [REQ-RISK-05]"""
    assert gate("Buy", ticker="AMD", pm={"price_target": 250.0})["intent"]["take_profit_rate"] == 250.0
    assert gate("Buy", ticker="AMD", pm={"price_target": 150.0})["intent"]["take_profit_rate"] is None


def test_queue_cap_and_priority(tmp_path):
    """TST-RISK-07: Queue takes at most max_orders, closes first, then strongest opens [REQ-RISK-06]"""
    q = orders.Queue(tmp_path / "q.json")
    mk = lambda sym, kind, rating: {"etoro_symbol": sym, "kind": kind, "rating": rating}
    added = q.enqueue([mk("A", "open", "Overweight"), mk("B", "open", "Buy"), mk("C", "close", "Underweight"),
                       mk("D", "close", "Sell")], "t1", 3)
    assert [i["intent"]["etoro_symbol"] for i in added] == ["D", "C", "B"]


def test_mirror_positions_never_closed():
    """TST-RISK-08: Close intents only target direct positions (mirrors excluded upstream) [REQ-RISK-07]"""
    from berkshire.etoro import from_etoro_summary
    book = from_etoro_summary({"totals": {"totalValue": 1000, "availableCash": 500}, "holdings": [
        {"symbol": "NVDA", "units": 3, "positions": [{"positionId": 1, "units": 1}, {"positionId": 2, "units": 2, "mirrorId": 77}]}]})
    assert [c["position_id"] for c in gate("Sell", book=book)["intent"]["closes"]] == [1]


@pytest.mark.parametrize("key,bad", [("target_weight", 0), ("max_order_pct", 1.5), ("min_cash_pct", 1),
                                     ("max_orders_per_run", 0), ("min_order_amount", -1), ("account", "live")])
def test_limits_validated(monkeypatch, key, bad):
    """TST-RISK-09: Limits are validated; defaults match the agreed conservative set [REQ-RISK-08]"""
    d = config.DEFAULTS
    assert (d["target_weight"], d["max_order_pct"], d["max_instrument_pct"], d["min_cash_pct"], d["max_orders_per_run"],
            d["min_order_amount"], d["atr_stop_multiple"], d["underweight_close_fraction"]) == (0.05, 0.05, 0.15, 0.10, 5, 50.0, 2.0, 0.5)
    with pytest.raises(ValueError, match=key):
        config.load({key: bad})


def test_gate_recorded_in_run(cfg, log, capsys):
    """TST-RISK-10: The gate result (intent or veto + reasons) is written to the run dir [REQ-RISK-09]"""
    state = run_all(new_run(cfg, log), log)
    book = config.home() / "book.json"
    book.write_text(json.dumps({"cash": 50_000, "equity": 100_000, "positions": []}))
    quote = config.home() / "quote.json"
    quote.write_text(json.dumps({"instruments": [{"symbol": "NVDA", "instrumentId": 1137, "quote": {"ask": 300.0, "bid": 299.9}}]}))
    assert main(["gate", state["run_dir"], "--quote-file", str(quote), "--portfolio-file", str(book), "--atr", "3"]) == 0
    saved = json.loads((config.home() / "runs/NVDA/2026-09-18/orders.json").read_text())
    assert saved["intent"]["amount"] == 5_000.0 and saved["intent"]["stop_loss_rate"] == 290.0   # Trader's stop
    assert saved["intent"]["take_profit_rate"] == 340.0 and saved["reasons"]


def test_queue_lifecycle(tmp_path):
    """TST-EXE-04: pending -> approved -> placed; invalid transitions rejected; expiry and supersede [REQ-EXE-04]"""
    q = orders.Queue(tmp_path / "q.json")
    t0 = datetime(2026, 9, 24, 9)
    a = q.enqueue([{"etoro_symbol": "NVDA", "kind": "open", "rating": "Buy"}], "t1", 5, now=t0)[0]
    with pytest.raises(ValueError, match="cannot move"):
        q.mark(a["id"], "placed")
    q.mark(a["id"], "approved")
    assert q.mark(a["id"], "placed", {"outcome": "executed"})["result"] == {"outcome": "executed"}
    b = q.enqueue([{"etoro_symbol": "AMD", "kind": "open", "rating": "Buy"}], "t2", 5, now=t0)[0]
    c = q.enqueue([{"etoro_symbol": "AMD", "kind": "open", "rating": "Overweight"}], "t3", 5, now=t0)[0]
    status = {i["id"]: i["status"] for i in q.load()}
    assert status[b["id"]] == "superseded" and status[c["id"]] == "pending"
    assert q.expire(24, now=t0 + timedelta(hours=25)) == 1
    assert q.pending() == []
    with pytest.raises(ValueError, match="no queue item"):
        q.mark("nope", "approved")


def test_enqueue_idempotent_per_run(cfg, log, capsys):
    """TST-SCHED-03: A run's intent is queued once; a repeated tick does not double-order [REQ-SCHED-03]"""
    state = run_all(new_run(cfg, log), log)
    (config.home() / "runs/NVDA/2026-09-18/orders.json").write_text(json.dumps(
        {"intent": {"etoro_symbol": "NVDA", "kind": "open", "rating": "Buy"}, "reasons": []}))
    main(["enqueue", state["run_dir"], "--tag", "tick-1"])
    first = json.loads(capsys.readouterr().out)
    main(["enqueue", state["run_dir"], "--tag", "tick-2"])
    second = json.loads(capsys.readouterr().out)
    assert len(first["queued"]) == 1 and second["queued"] == [] and "already queued" in second["skipped"][0]
