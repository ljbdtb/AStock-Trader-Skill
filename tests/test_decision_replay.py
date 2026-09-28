from datetime import timedelta
import pytest

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


def _write_bundle(directory):
    directory.mkdir(parents=True)
    frames, stock, benchmark = _inputs()
    for period, frame in frames.items():
        frame.to_csv(directory / f"{period}m.csv", index=False)
    stock.to_csv(directory / "daily_stock.csv", index=False)
    benchmark.to_csv(directory / "daily_csi300.csv", index=False)


def test_local_bundle_loads_canonical_files_and_records_provenance(tmp_path):
    bundle = tmp_path / "002475"
    _write_bundle(bundle)

    frames, stock, benchmark, metadata = decision_replay.load_local_symbol(
        bundle, "002475", data_origin="REAL_HISTORICAL"
    )

    assert set(frames) == {"1", "5", "15"}
    assert len(stock) == len(benchmark) == 25
    assert set(metadata) == {"1", "5", "15", "daily_stock", "daily_csi300"}
    for timeframe, record in metadata.items():
        assert record["source_type"] == "LOCAL_FIXTURE"
        assert record["data_origin"] == "REAL_HISTORICAL"
        assert record["row_count"] > 0
        assert len(record["checksum"]) == 64
        assert record["first_timestamp"] <= record["last_timestamp"]
        expected_file = {
            "1": "1m.csv", "5": "5m.csv", "15": "15m.csv",
            "daily_stock": "daily_stock.csv", "daily_csi300": "daily_csi300.csv",
        }[timeframe]
        assert record["source_file"].endswith(expected_file)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
         "duplicate time"),
        (lambda frame: frame.iloc[::-1].reset_index(drop=True),
         "already sorted"),
        (lambda frame: frame.assign(high=frame["low"] - 1),
         "OHLC relationship"),
        (lambda frame: frame.drop(columns=["volume"]),
         "missing required columns"),
    ],
)
def test_local_bundle_rejects_invalid_intraday_data(tmp_path, mutate, message):
    bundle = tmp_path / "002475"
    _write_bundle(bundle)
    bars_path = bundle / "5m.csv"
    bars = pd.read_csv(bars_path)
    mutate(bars).to_csv(bars_path, index=False)

    with pytest.raises(ValueError, match=message):
        decision_replay.load_local_symbol(bundle, "002475")


def test_synthetic_input_cannot_pass_real_data_acceptance():
    report = decision_replay._finalize_acceptance({
        "assets": [
            {
                "symbol": str(index), "source_type": "LOCAL_FIXTURE",
                "data_origin": "SYNTHETIC_FIXTURE", "trace_count": 30,
                "regimes_seen": ["RANGE", "UPTREND"], "schema_failures": [],
                "causality_failures": [], "decision_trace_failures": [],
                "errors": [], "source_metadata": {},
            }
            for index in range(3)
        ]
    })

    assert report["usable_symbols"] == 3
    assert report["eligible_real_symbols"] == 0
    assert report["REAL_DATA_ACCEPTANCE"] == "INCOMPLETE"


def test_replay_trace_integrity_audit_passes_current_snapshot():
    frames, stock, benchmark = _inputs()
    trace = decision_replay.replay_decisions(
        "002475", frames, stock, benchmark,
        decision_times=[frames["5"].time.iloc[-1]],
    )[0]

    assert decision_replay._trace_failures(trace) == []
