"""eToro adapters: portfolio snapshot, symbol mapping, universe."""

import json

import pytest

from berkshire import config, etoro
from berkshire.cli import main

SUMMARY = {"account": "demo", "accountCurrency": "USD",
           "totals": {"totalValue": 100000.0, "availableCash": 90000.0},
           "holdings": [{"symbol": "NVDA", "instrumentId": 1137, "units": 20, "currentValue": 4500.0,
                         "averageOpenRate": 180.0, "positions": [{"positionId": 5, "units": 20}]},
                        {"symbol": "BTC", "instrumentId": 100000, "assetTypeId": 10, "units": 0.1, "currentValue": 6000.0}],
           "copiedTraders": [{"username": "someone"}]}

WATCHLISTS = {"watchlists": {"watchlists": [
    {"name": "Recently Invested", "items": [{"itemId": 3000, "itemType": "Instrument", "market": {"symbolName": "SPY", "assetTypeId": 6}}]},
    {"name": "My Watchlist", "items": [
        {"itemId": 1137, "itemType": "Instrument", "market": {"symbolName": "NVDA", "assetTypeId": 5}},
        {"itemId": 18, "itemType": "Instrument", "market": {"symbolName": "GOLD", "assetTypeId": 2}},
        {"itemId": 22, "itemType": "Instrument", "market": {"symbolName": "NATGAS2", "assetTypeId": 2}},
        {"itemId": 1, "itemType": "Instrument", "market": {"symbolName": "EURUSD", "assetTypeId": 1}},
        {"itemId": 2587, "itemType": "Instrument", "market": {"symbolName": "RHM.DE", "assetTypeId": 5}},
        {"itemId": 100063, "itemType": "Instrument", "market": {"symbolName": "SOL", "assetTypeId": 10}},
        {"itemId": 918269, "itemType": "User"}]}]}}


def test_portfolio_from_summary(tmp_path, capsys):
    """TST-EXE-06: The eToro portfolio summary maps to equity, cash and direct positions [REQ-EXE-06]"""
    p = etoro.from_etoro_summary(SUMMARY)
    assert (p["equity"], p["cash"], p["currency"]) == (100000.0, 90000.0, "USD")
    nvda = etoro.position_in(p, "NVDA")
    assert nvda["quantity"] == 20 and nvda["value"] == 4500.0 and nvda["position_ids"] == [{"id": 5, "units": 20.0}]
    assert "Current position in NVDA: 20 units, average price 180.00, value 4,500.00" in etoro.render_portfolio(p, "NVDA")
    f = tmp_path / "s.json"
    f.write_text(json.dumps(SUMMARY))
    assert main(["etoro-portfolio", str(f), "--out", str(tmp_path / "p.json")]) == 0
    assert etoro.load_portfolio_file(tmp_path / "p.json")["equity"] == 100000.0
    assert etoro.load_portfolio_file(f)["cash"] == 90000.0      # raw summary also accepted


@pytest.mark.parametrize("sym,atype,expected", [
    ("NVDA", 5, "NVDA"), ("RHM.DE", 5, "RHM.DE"), ("EIMI.L", 6, "EIMI.L"), ("BRK.B", 5, "BRK-B"),
    ("BTC", 10, "BTC-USD"), ("EURUSD", 1, "EURUSD=X"), ("GOLD", 2, "GC=F"), ("SPX500", 4, "^GSPC"),
    ("NATGAS2", 2, None), ("MYSTERY", 4, None)])
def test_symbol_mapping(sym, atype, expected):
    """TST-EXE-07: eToro symbols map to Yahoo symbols; unmappable ones return None [REQ-EXE-07]"""
    assert etoro.yf_symbol(sym, atype, config.DEFAULTS["symbol_map"]) == expected


def test_universe(tmp_path):
    """TST-SCHED-01: Universe = holdings then named watchlist, de-duplicated, users/unmappable skipped [REQ-SCHED-01, REQ-IF-04]"""
    p = etoro.from_etoro_summary(SUMMARY)
    items, skipped = etoro.universe(p, WATCHLISTS, "My Watchlist", config.DEFAULTS["symbol_map"], 10)
    assert [i["ticker"] for i in items] == ["NVDA", "BTC-USD", "GC=F", "EURUSD=X", "RHM.DE", "SOL-USD"]
    assert [i["source"] for i in items[:2]] == ["holding", "holding"]
    assert {i["ticker"]: i["asset_type"] for i in items}["SOL-USD"] == "crypto"
    assert items[1]["etoro_symbol"] == "BTC" and items[1]["instrument_id"] == 100000
    assert any("NATGAS2" in s for s in skipped)
    _, missing = etoro.universe(p, WATCHLISTS, "Nope", {}, 10)
    assert "watchlist 'Nope' not found" in missing


def test_universe_cap():
    """TST-SCHED-04: max_tickers_per_tick caps the universe, holdings first [REQ-SCHED-04]"""
    p = etoro.from_etoro_summary(SUMMARY)
    items, skipped = etoro.universe(p, WATCHLISTS, "My Watchlist", config.DEFAULTS["symbol_map"], 2)
    assert [i["source"] for i in items] == ["holding", "holding"]
    assert sum("over max_tickers_per_tick" in s for s in skipped) == 4


def test_weekend_is_settle_only(tmp_path, capsys):
    """TST-SCHED-02: universe reports trading_day=false on weekends so the tick only settles [REQ-SCHED-02]"""
    from berkshire.cli import is_trading_day
    assert is_trading_day("2026-09-25") and not is_trading_day("2026-09-26") and not is_trading_day("2026-09-27")
    main(["universe", "--date", "2026-09-26"])
    assert json.loads(capsys.readouterr().out)["trading_day"] is False


def test_account_default_demo():
    """TST-EXE-03: Account defaults to demo; only demo/real accepted; the gate stamps it on intents [REQ-EXE-03]"""
    assert config.load()["account"] == "demo"
    from berkshire import orders
    intent = orders.gate(ticker="AMD", etoro_symbol="AMD", instrument_id=None, rating="Buy",
                         portfolio={"equity": 1e5, "cash": 5e4, "positions": []}, ask=100.0, trader=None, pm=None,
                         atr=2.0, cfg={**config.DEFAULTS, "account": "real"})["intent"]
    assert intent["account"] == "real"
