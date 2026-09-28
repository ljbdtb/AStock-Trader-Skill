from datetime import date

import pandas as pd

from astock_trader.position import PositionLedger
from astock_trader import risk as risk_module
from astock_trader.risk import gate_decision


def snapshot():
    return {"as_of": 7, "bias": "BULLISH", "high_state": "HH",
            "low_state": "HL", "confirmed_swing_low": 10.0,
            "support": 10.0, "support_source": "CONFIRMED_SWING"}


def test_close_below_buffered_confirmed_hl_overrides_hold():
    risk = risk_module.structural_invalidation(snapshot(), close=9.7, low=9.2, atr=1.0)
    assert risk.reference_level == 10.0
    assert risk.reference_type == "CONFIRMED_HIGHER_LOW"
    assert risk.invalidation_level == 9.75
    assert risk.breached and risk.confirmed
    ledger = PositionLedger(date(2026, 9, 24), core_shares=100)
    assert gate_decision("HOLD", "BUYBACK_T", ledger, True, invalidation=risk) == ("REDUCE", "WAIT")


def test_wick_alone_does_not_confirm_and_unknown_reference_fails_closed():
    risk = risk_module.structural_invalidation(snapshot(), close=9.8, low=9.2, atr=1.0)
    assert risk.breached and not risk.confirmed
    assert risk.reason_codes == ("INTRABAR_BREACH_UNCONFIRMED",)
    fallback = risk_module.structural_invalidation({**snapshot(), "low_state": "NA"}, close=8, low=8, atr=1)
    assert fallback.reference_type == "UNKNOWN"
    assert fallback.reference_level is None
    assert not fallback.confirmed
    unknown = risk_module.structural_invalidation(
        {**snapshot(), "low_state": "NA", "confirmed_swing_low": None,
         "support_source": "UNKNOWN"}, close=8, low=8, atr=1)
    assert unknown.reference_level is None
    assert not unknown.confirmed


def test_bad_data_or_unsellable_position_never_issues_reduce():
    risk = risk_module.structural_invalidation(snapshot(), close=9, low=8.9, atr=1)
    ledger = PositionLedger(date(2026, 9, 24), core_shares=100)
    assert gate_decision("HOLD", "WAIT", ledger, False, invalidation=risk) == ("WAIT", "WAIT")
    unsellable = PositionLedger(date(2026, 9, 24), core_shares=100, bought_core_today=100)
    assert gate_decision("HOLD", "WAIT", unsellable, True, invalidation=risk) == ("WAIT", "WAIT")


def test_invalid_atr_cannot_create_confirmed_structural_invalidation():
    risk = risk_module.structural_invalidation(snapshot(), close=9, low=8.9, atr=float("nan"))
    assert risk.invalidation_level is None
    assert not risk.confirmed


def test_confirmed_risk_persists_until_new_confirmed_higher_low():
    first = risk_module.structural_invalidation(snapshot(), close=9.7, low=9.2, atr=1)
    previous = {"active": first.active, "reference_level": first.reference_level,
                "invalidation_level": first.invalidation_level}
    rebound = risk_module.structural_invalidation(
        snapshot(), close=10.2, low=10.1, atr=1, previous=previous)
    assert rebound.active
    assert rebound.status == "RECOVERY"
    stale = risk_module.structural_invalidation(
        snapshot(), close=12, low=12, atr=1, data_ok=False, previous=previous)
    assert stale.active and not stale.confirmed
    assert stale.status == "WAIT_DATA"
    assert stale.invalidation_level == 9.75
    assert "DATA_STALE_NO_NEW_INVALIDATION" in stale.reason_codes
    new_structure = {**snapshot(), "confirmed_swing_low": 10.5, "support": 10.5}
    cleared = risk_module.structural_invalidation(
        new_structure, close=10.8, low=10.7, atr=1, previous=previous)
    assert not cleared.active


def test_stale_data_cannot_create_new_risk():
    stale = risk_module.structural_invalidation(
        snapshot(), close=9, low=8.8, atr=1, data_ok=False)
    assert not stale.active
    assert not stale.confirmed
    assert stale.status == "WAIT_DATA"


def test_missing_required_five_minute_timeframe_blocks_risk_confirmation():
    from main import decision_data_ok

    longer_frame = pd.DataFrame([{"close": 9, "low": 8.8, "high": 10}])
    assert not decision_data_ok({"15": longer_frame},
                                {"15": longer_frame}, {"15": {}})


def test_reduce_uses_sellable_core_not_t_and_reports_t1_block():
    risk = risk_module.structural_invalidation(snapshot(), close=9, low=8.8, atr=1)
    limited = PositionLedger(date(2026, 9, 24), core_shares=1800,
                             bought_core_today=200, t_shares=400)
    assert gate_decision("HOLD", "SELL_T", limited, True, invalidation=risk) == ("REDUCE", "WAIT")
    blocked = PositionLedger(date(2026, 9, 24), core_shares=200,
                             bought_core_today=200, t_shares=400)
    assert gate_decision("HOLD", "SELL_T", blocked, True, invalidation=risk) == ("WAIT", "WAIT")


def test_decision_uses_same_snapshot_for_display_and_risk(monkeypatch):
    from astock_trader import decision

    facts = {**snapshot(), "support": 10.0, "resistance": 11.0,
             "resistance_source": "CONFIRMED_SWING",
             "breakout_status": "KNOWN_LEVEL", "breakout_level": 11.0,
             "volume_ratio": 1.0}
    calls = []

    def once(frame):
        calls.append(1)
        return facts

    monkeypatch.setattr(decision, "structure_snapshot", once)
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "STRONG_UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 85)
    row = pd.DataFrame([{"close": 9.7, "low": 9.2, "high": 10.0,
                         "atr14": 1.0, "vwap": 9.7, "rsi12": 70,
                         "macd_hist": 0, "volume": 1000}])
    ledger = PositionLedger(date(2026, 9, 24), core_shares=100)
    out = decision.decide(row, position=ledger, data_ok=True)
    assert calls == [1]
    assert out["score"] >= 85
    assert out["action"] == "REDUCE"
    assert out["t_action"] == "WAIT"
    assert out["support"] == 10.0
    assert out["structural_reference_level"] == 10.0
    assert out["structural_invalidation_level"] == 9.75
    assert out["structural_invalidation_confirmed"]
    assert out["risk_active"]
    assert out["risk_status"] == "CONFIRMED_INVALIDATION"
    assert out["max_reducible_qty"] == 100
    assert "reduce_quantity" not in out
    assert "STRUCTURE_INVALIDATED" in out["risk_reason_codes"]
    from astock_trader.card import render_card
    card = render_card({**out, "symbol": "002475"})
    assert "失效参考: 9.75" in card
    assert decision.decide(row, position=ledger, data_ok=False)["action"] == "WAIT"


def test_decision_preserves_risk_through_rebound_and_bad_data(monkeypatch):
    from astock_trader import decision

    facts = {**snapshot(), "resistance": 11.0,
             "resistance_source": "CONFIRMED_SWING",
             "breakout_status": "KNOWN_LEVEL", "breakout_level": 11.0,
             "volume_ratio": 1.0}
    monkeypatch.setattr(decision, "structure_snapshot", lambda df: facts)
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "STRONG_UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 90)
    ledger = PositionLedger(date(2026, 9, 24), core_shares=200,
                            bought_core_today=200, t_shares=400)
    row = pd.DataFrame([{"close": 9.7, "low": 9.2, "high": 10.0,
                         "atr14": 1.0, "vwap": 9.7, "rsi12": 70,
                         "macd_hist": 0, "volume": 1000}])
    first = decision.decide(row, position=ledger, data_ok=True)
    assert first["risk_active"]
    assert first["decision_status"] == "REDUCE_BLOCKED_T1"
    assert first["max_reducible_qty"] == 0
    from astock_trader.card import render_card
    assert "REDUCE_BLOCKED_T1" in render_card({**first, "symbol": "002475"})
    previous = {"active": first["risk_active"],
                "reference_level": first["structural_reference_level"]}
    row.loc[0, ["close", "low"]] = [10.3, 10.1]
    rebound = decision.decide(row, position=ledger, data_ok=True, previous_risk=previous)
    assert rebound["risk_active"]
    assert rebound["risk_status"] == "RECOVERY"
    assert rebound["action"] == "WAIT"
    stale = decision.decide(row, position=ledger, data_ok=False, previous_risk=previous)
    assert stale["risk_active"]
    assert stale["decision_status"] == "WAIT_DATA"


def test_analysis_state_persists_structural_risk(tmp_path):
    from astock_trader.state import AnalysisState, StateStore

    store = StateStore(tmp_path / "state.json")
    store.put(AnalysisState("002475", risk_active=True, risk_reference_level=10.0,
                            risk_invalidation_level=9.75))
    previous = store.get("002475")
    assert previous.risk_active
    assert previous.risk_reference_level == 10.0
    assert previous.risk_invalidation_level == 9.75


def test_changed_structural_level_triggers_updated_decision_card():
    from astock_trader.state import AnalysisState, materially_changed

    previous = AnalysisState("002475", regime="UPTREND", action="HOLD",
                             t_action="WAIT", score=70,
                             risk_reference_level=10.0,
                             risk_invalidation_level=9.75,
                             risk_status="INTACT")
    current = {"regime": "UPTREND", "action": "HOLD", "t_action": "WAIT",
               "score": 70, "risk_active": False, "risk_status": "INTACT",
               "structural_reference_level": 10.5,
               "structural_invalidation_level": 10.25}
    assert materially_changed(previous, current)


def test_structural_risk_is_prefix_invariant_to_future_prices():
    from astock_trader.structure import structure_snapshot

    highs = [11, 12, 16, 12, 11, 12, 13, 17, 13, 12, 13, 13, 14]
    lows = [8, 7, 6, 7, 5, 6, 7, 8, 7, 6, 7, 8, 4]
    data = pd.DataFrame({"high": highs, "low": lows,
                         "close": [(h + l) / 2 for h, l in zip(highs, lows)],
                         "volume": [1000] * len(highs)})
    data.loc[12, "close"] = 5
    future = pd.concat([data, pd.DataFrame([{
        "high": 1000, "low": 0.1, "close": 500, "volume": 1000000
    }])], ignore_index=True)
    at_t = structure_snapshot(data)
    assert at_t == structure_snapshot(future, as_of=12)
    first = risk_module.structural_invalidation(
        at_t, close=5, low=4, atr=1)
    after_future_change = risk_module.structural_invalidation(
        structure_snapshot(future, as_of=12), close=5, low=4, atr=1)
    assert first == after_future_change


def test_decision_caps_reduce_quantity_at_sellable_core(monkeypatch):
    from astock_trader import decision

    facts = {**snapshot(), "resistance": 11.0,
             "resistance_source": "CONFIRMED_SWING",
             "breakout_status": "KNOWN_LEVEL", "breakout_level": 11.0,
             "volume_ratio": 1.0}
    monkeypatch.setattr(decision, "structure_snapshot", lambda df: facts)
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "STRONG_UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 90)
    row = pd.DataFrame([{"close": 9.7, "low": 9.2, "high": 10.0,
                         "atr14": 1.0, "vwap": 9.7, "rsi12": 70,
                         "macd_hist": 0, "volume": 1000}])
    ledger = PositionLedger(date(2026, 9, 24), core_shares=1800,
                            bought_core_today=200, t_shares=400)
    out = decision.decide(row, position=ledger, data_ok=True)
    assert out["action"] == "REDUCE"
    assert out["max_reducible_qty"] == 1600
    assert "REDUCE_LIMITED_BY_T1" in out["risk_reason_codes"]
    from astock_trader.card import render_card
    card = render_card({**out, "symbol": "002475"})
    assert "核心动作: REDUCE" in card
    assert "可减核心仓上限: ≤1600股" in card
    assert "REDUCE 1600股" not in card


def test_card_marks_missing_structural_level_as_unavailable():
    from astock_trader.card import render_card

    card = render_card({"symbol": "002475", "price": 10, "regime": "UNKNOWN",
                        "score": 50, "action": "WAIT", "support": 9,
                        "resistance": 11, "structural_invalidation_level": None})
    assert "失效参考: 不可判定" in card
