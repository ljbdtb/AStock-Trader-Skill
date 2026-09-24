from datetime import date

import pytest

from astock_trader.position import PositionLedger
from astock_trader.trading_rules import t_signal
from types import SimpleNamespace


def test_sell_then_buyback_respects_t_inventory_and_t_plus_one():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=400)
    assert ledger.sellable_core_shares == 600
    assert ledger.sellable_t_shares == 400
    ledger.sell_t(200)
    assert ledger.sold_t_today == 200
    assert ledger.buyback_remaining == 200
    ledger.buyback_t(100)
    assert ledger.total_shares == 900
    assert ledger.sellable_t_shares == 200
    assert ledger.buyback_remaining == 100
    with pytest.raises(ValueError):
        ledger.sell_t(201)
    with pytest.raises(ValueError):
        ledger.buyback_t(101)


def test_new_t_purchase_cannot_be_sold_even_with_sellable_core():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200,
                            bought_t_today=200)
    assert ledger.sellable_shares == 600
    assert ledger.sellable_t_shares == 0
    with pytest.raises(ValueError):
        ledger.sell_t(100)


def test_rollover_makes_bought_shares_sellable_and_clears_intraday_counters():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200)
    ledger.sell_t(100)
    ledger.buyback_t(100)
    ledger.rollover(date(2026, 9, 25))
    assert ledger.sellable_t_shares == 200
    assert ledger.buyback_remaining == 0
    assert ledger.sold_t_today == 0
    assert ledger.bought_back_t_today == 0


def test_multiple_core_and_t_sales_preserve_lot_boundaries():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=300,
                            bought_core_today=100)
    ledger.sell_core(200)
    ledger.sell_core(100)
    ledger.sell_t(100)
    ledger.sell_t(50)
    assert ledger.core_shares == 300
    assert ledger.t_shares == 150
    assert ledger.sellable_core_shares == 200
    assert ledger.sellable_t_shares == 150
    assert ledger.sold_today == 450
    assert ledger.buyback_remaining == 150
    with pytest.raises(ValueError):
        ledger.sell_core(201)


@pytest.mark.parametrize("kwargs", [
    {"core_shares": -1},
    {"t_shares": 10, "bought_t_today": 11},
    {"sold_t_today": 5, "bought_back_t_today": 6},
    {"portfolio_weight": -0.1},
    {"portfolio_weight": 1.1},
])
def test_invalid_state_is_rejected(kwargs):
    with pytest.raises(ValueError):
        PositionLedger(date(2026, 9, 24), **kwargs)


def test_buyback_signal_requires_a_prior_t_sale():
    row = SimpleNamespace(close=10.0, vwap=10.0, rsi12=50, macd_hist=0.1)
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200)
    assert t_signal("UPTREND", row, ledger) == "WAIT"
    ledger.sell_t(100)
    assert t_signal("UPTREND", row, ledger) == "BUYBACK_T"
    ledger.buyback_t(100)
    assert t_signal("UPTREND", row, ledger) == "WAIT"


def test_sell_signal_uses_sellable_t_not_sellable_core():
    row = SimpleNamespace(close=10.0, vwap=10.0, rsi12=50, macd_hist=0.1)
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200,
                            bought_t_today=200)
    assert t_signal("FALSE_BREAKOUT", row, ledger) == "WAIT"


def test_decision_uses_ledger_sellable_count(monkeypatch):
    import pandas as pd
    from astock_trader import decision

    monkeypatch.setattr(decision, "classify", lambda df: "RANGE")
    monkeypatch.setattr(decision, "score", lambda *args: 50)
    monkeypatch.setattr(decision, "structure_features", lambda df: {
        "bias": "NEUTRAL", "high_state": "NA", "low_state": "NA",
        "swing_low": None, "swing_high": None, "volume_ratio": 1.0})
    frame = pd.DataFrame([{"close": 10., "low": 9., "high": 11.,
                           "atr14": 1., "vwap": 10., "rsi12": 50.,
                           "macd_hist": 0.1}])
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200,
                            bought_t_today=200)
    assert decision.decide(frame, position=ledger)["sellable_shares"] == 600


def test_cli_position_snapshot_requires_complete_same_day_state():
    from argparse import Namespace
    from main import position_from_args

    values = dict(trading_date="2026-09-24", core_shares=600, t_shares=200,
                  bought_core_today=0, bought_t_today=200, sold_t_today=0,
                  bought_back_t_today=0, shares=800, cost=None,
                  portfolio_weight=0.4)
    position = position_from_args(Namespace(**values))
    assert position.sellable_shares == 600
    values["bought_t_today"] = None
    with pytest.raises(ValueError):
        position_from_args(Namespace(**values))


def test_cli_legacy_share_count_is_not_assumed_to_be_sellable():
    from argparse import Namespace
    from main import position_from_args

    values = dict(trading_date=None, core_shares=None, t_shares=None,
                  bought_core_today=None, bought_t_today=None,
                  sold_t_today=None, bought_back_t_today=None,
                  shares=800, cost=None, portfolio_weight=None)
    assert position_from_args(Namespace(**values)) is None
