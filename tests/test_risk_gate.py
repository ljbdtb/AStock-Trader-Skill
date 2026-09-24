from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from astock_trader.position import PositionLedger
from astock_trader.risk import gate_decision, market_data_quality


def test_high_concentration_blocks_buyback_but_not_t_sale():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200,
                            sold_t_today=100, portfolio_weight=0.95)
    assert gate_decision("HOLD", "BUYBACK_T", ledger, True)[1] == "WAIT"
    assert gate_decision("WAIT", "SELL_T", ledger, True) == ("WAIT", "SELL_T")


def test_missing_position_or_bad_data_blocks_actionable_signals():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200)
    assert gate_decision("REDUCE", "SELL_T", None, True) == ("WAIT", "WAIT")
    assert gate_decision("REDUCE", "SELL_T", ledger, False) == ("WAIT", "WAIT")


def test_reduce_takes_precedence_over_t_sale_and_empty_holding_cannot_hold():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200)
    assert gate_decision("REDUCE", "SELL_T", ledger, True) == ("REDUCE", "WAIT")
    empty = PositionLedger(date(2026, 9, 24))
    assert gate_decision("HOLD", "WAIT", empty, True) == ("WAIT", "WAIT")


def test_unrecognized_or_net_new_buy_intents_fail_closed():
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200,
                            portfolio_weight=0.40)
    assert gate_decision("BUY", "BUY_T", ledger, True) == ("WAIT", "WAIT")


def test_data_quality_rejects_stale_and_invalid_bars():
    now = datetime(2026, 9, 24, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    frame = pd.DataFrame([{"time": "2026-09-24 10:25:00", "open": 10.,
                           "high": 11., "low": 9., "close": 10.,
                           "volume": 1000.}])
    assert market_data_quality(frame, {"data_time": "2026-09-24T10:25:00"}, now)
    assert not market_data_quality(frame, {"data_time": "2026-09-24T09:30:00"}, now)
    bad = frame.copy()
    bad.loc[0, "high"] = 8.
    assert not market_data_quality(bad, {"data_time": "2026-09-24T10:25:00"}, now)
    bad.loc[0, "high"] = float("inf")
    assert not market_data_quality(bad, {"data_time": "2026-09-24T10:25:00"}, now)
    assert not market_data_quality(frame, {"error": "provider failed"}, now)


def test_decision_applies_gate_to_t_action(monkeypatch):
    from astock_trader import decision

    monkeypatch.setattr(decision, "classify", lambda df: "UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args: 50)
    monkeypatch.setattr(decision, "structure_features", lambda df: {
        "bias": "NEUTRAL", "high_state": "NA", "low_state": "NA",
        "swing_low": None, "swing_high": None, "volume_ratio": 1.0})
    frame = pd.DataFrame([{"close": 10., "low": 9., "high": 11.,
                           "atr14": 1., "vwap": 10., "rsi12": 50.,
                           "macd_hist": 0.1}])
    ledger = PositionLedger(date(2026, 9, 24), core_shares=600, t_shares=200,
                            sold_t_today=100, portfolio_weight=0.95)
    assert decision.decide(frame, position=ledger, data_ok=True)["t_action"] == "WAIT"
    ledger.portfolio_weight = 0.40
    assert decision.decide(frame, position=ledger, data_ok=True)["t_action"] == "BUYBACK_T"
    assert decision.decide(frame, position=ledger, data_ok=False)["t_action"] == "WAIT"
