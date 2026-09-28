from datetime import date, timedelta

import pandas as pd

from astock_trader.position import PositionLedger
from backtest import decision_replay


def _bars(count, minutes):
    times = pd.date_range("2026-09-21 09:30", periods=count,
                          freq=f"{minutes}min")
    close = [10 + i * 0.002 for i in range(count)]
    return pd.DataFrame({
        "time": times,
        "open": close,
        "high": [value + 0.05 for value in close],
        "low": [value - 0.05 for value in close],
        "close": close,
        "volume": [1000 + i for i in range(count)],
    })


def _inputs():
    frames = {"1": _bars(400, 1), "5": _bars(80, 5), "15": _bars(30, 15)}
    dates = pd.date_range("2026-08-17", periods=25, freq="B")
    stock = pd.DataFrame({"date": dates, "close": [100 + i for i in range(25)]})
    index = pd.DataFrame({"date": dates, "close": [100 + i * 0.8 for i in range(25)]})
    return frames, stock, index


def test_replay_trace_is_causal_and_future_mutation_invariant():
    frames, stock, index = _inputs()
    target = frames["5"].time.iloc[-5]
    first = decision_replay.replay_decisions(
        "002475", frames, stock, index, decision_times=[target]
    )[0]
    changed = {key: frame.copy() for key, frame in frames.items()}
    for key, frame in changed.items():
        step = 1 if key == "1" else int(key)
        future = pd.DataFrame({
            "time": [frame.time.iloc[-1] + pd.Timedelta(minutes=step)],
            "open": [500.0], "high": [600.0], "low": [400.0],
            "close": [550.0], "volume": [float(10**9)],
        })
        changed[key] = pd.concat([frame, future], ignore_index=True)
    future_stock = pd.concat([
        stock, pd.DataFrame({"date": [pd.Timestamp(target).normalize()],
                             "close": [99999]})
    ], ignore_index=True)
    second = decision_replay.replay_decisions(
        "002475", changed, future_stock, index, decision_times=[target]
    )[0]
    assert first == second


def test_replay_emits_score_integrity_mtf_asof_and_card_consistency(monkeypatch):
    frames, stock, index = _inputs()
    calls = []
    original = decision_replay.structure_snapshot

    def counted(frame):
        calls.append(len(frame))
        return original(frame)

    monkeypatch.setattr(decision_replay, "structure_snapshot", counted)
    target = frames["5"].time.iloc[-1]
    trace = decision_replay.replay_decisions(
        "002475", frames, stock, index, decision_times=[target],
        position_provider=lambda stamp: PositionLedger(
            stamp.date(), core_shares=1000, t_shares=100
        ),
    )[0]
    assert len(calls) == 1
    assert sum(trace["score_components"].values()) == trace["score_total"]
    assert trace["data_quality"] == "PASS"
    assert trace["mtf"]["status"] == "PASS"
    assert trace["mtf"]["source_timeframes"] == ["1", "15", "5"]
    assert all(pd.Timestamp(value) <= pd.Timestamp(trace["timestamp"])
               for value in trace["mtf"]["source_timestamps"].values())
    assert trace["position_constraints"]["total_shares"] == 1100
    assert f'评分: {trace["score_total"]}/100' in trace["card"]
    assert trace["recommendation"]["action"] in {"HOLD", "WAIT", "REDUCE"}


def test_stale_replay_cannot_create_actionable_recommendation():
    frames, stock, index = _inputs()
    target = frames["5"].time.iloc[-1] + timedelta(minutes=30)
    trace = decision_replay.replay_decisions(
        "002475", frames, stock, index, decision_times=[target],
        position_provider=lambda stamp: PositionLedger(
            stamp.date(), core_shares=1000, t_shares=100
        ),
    )[0]
    assert trace["data_quality"] == "FAIL"
    assert trace["recommendation"]["action"] == "WAIT"
    assert "STALE_OR_MISSING_DATA" in trace["scenario_tags"]


def test_no_bar_at_requested_time_is_explicitly_wait():
    frames, stock, index = _inputs()
    cutoff = frames["5"].time.iloc[0] - pd.Timedelta(minutes=1)
    trace = decision_replay.replay_decisions(
        "002475", frames, stock, index, decision_times=[cutoff]
    )[0]
    assert trace["recommendation"] == {"action": "WAIT", "t_action": "WAIT"}
    assert trace["reason_codes"] == ["NO_BAR_AS_OF_DECISION_TIME"]
