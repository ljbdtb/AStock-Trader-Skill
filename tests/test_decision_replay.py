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
        assert record["source_file"] == f"002475/{expected_file}"
        assert str(tmp_path) not in record["source_file"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
         "duplicate time"),
        (lambda frame: frame.iloc[::-1].reset_index(drop=True),
         "already be sorted"),
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


def test_local_acceptance_runs_replay_and_keeps_fixture_incomplete(tmp_path):
    _write_bundle(tmp_path / "002475")

    report = decision_replay.run_local_data_acceptance(
        tmp_path, symbols={"002475": "立讯精密"}, max_samples=4
    )

    asset = report["assets"][0]
    assert asset["trace_count"] == 4
    assert asset["causality_checks"] == 3
    assert set(asset["source_metadata"]) == {
        "1", "5", "15", "daily_stock", "daily_csi300"
    }
    assert report["usable_symbols"] == 0
    assert report["eligible_real_symbols"] == 0
    assert report["REAL_DATA_ACCEPTANCE"] == "INCOMPLETE"


def test_sample_times_only_uses_complete_mtf_overlap():
    frames, _, _ = _inputs()

    samples = decision_replay._sample_times(
        frames["5"], max_samples=5, frames=frames
    )

    assert len(samples) == 5
    latest_overlap = min(pd.to_datetime(frame.time).iloc[-1] for frame in frames.values())
    first_ready = max(pd.to_datetime(frame.time).iloc[24] for frame in frames.values())
    assert all(first_ready <= pd.Timestamp(stamp) <= latest_overlap for stamp in samples)
    for stamp in samples:
        assert all((pd.to_datetime(frame.time) <= stamp).sum() >= 25
                   for frame in frames.values())


def test_collector_persists_only_validated_provider_bundles_and_provenance(tmp_path):
    frames, stock, benchmark = _inputs()

    def fetch_frames(symbol, periods):
        assert periods == ("1", "5", "15")
        return frames, {period: {"provider": "fixture-mock"} for period in periods}

    def fetch_daily(symbol, as_of):
        return stock, benchmark

    result = decision_replay.collect_acceptance_data(
        tmp_path, {"002475": "立讯精密"},
        fetch_frames_fn=fetch_frames, fetch_daily_fn=fetch_daily,
    )

    asset = result["assets"][0]
    assert asset["status"] == "PASS"
    assert set(asset["source_metadata"]) == {
        "1m", "5m", "15m", "daily_stock", "daily_csi300"
    }
    assert asset["source_metadata"]["1m"]["source_type"] == "LIVE_PROVIDER"
    assert asset["source_metadata"]["1m"]["source_file"] == "002475/1m.csv"
    assert (tmp_path / "collection-manifest.json").exists()
    for filename in ("1m.csv", "5m.csv", "15m.csv",
                     "daily_stock.csv", "daily_csi300.csv"):
        assert (tmp_path / "002475" / filename).is_file()


def test_collector_keeps_complete_latest_day_1m_without_filling_old_opens(tmp_path):
    frames, stock, benchmark = _inputs()
    old = _bars(2, 1)
    old["time"] = pd.to_datetime(["2026-09-28 14:59", "2026-09-28 15:00"])
    old["open"] = 0.0  # Eastmoney reports unavailable prior-session 1m opens as zero.
    current = _bars(3, 1)
    current["time"] = pd.to_datetime([
        "2026-09-29 10:01", "2026-09-29 10:02", "2026-09-29 10:03"
    ])
    frames["1"] = pd.concat([old, current], ignore_index=True)

    result = decision_replay.collect_acceptance_data(
        tmp_path, {"002475": "立讯精密"},
        fetch_frames_fn=lambda symbol, periods: (
            frames,
            {period: {"provider": "AKShare/Eastmoney",
                      "fetched_at": "2026-09-29T10:03:30+08:00"}
             for period in periods},
        ),
        fetch_daily_fn=lambda symbol, as_of: (stock, benchmark),
    )

    asset = result["assets"][0]
    assert asset["status"] == "PASS"
    saved = pd.read_csv(tmp_path / "002475" / "1m.csv")
    assert saved["time"].tolist() == [
        "2026-09-29 10:01:00", "2026-09-29 10:02:00"
    ]
    assert saved["open"].tolist() == current["open"].iloc[:2].tolist()
    source = asset["source_metadata"]["1m"]
    assert source["raw_row_count"] == 5
    assert source["raw_first_timestamp"] == "2026-09-28T14:59:00"
    assert source["raw_last_timestamp"] == "2026-09-29T10:03:00"
    assert source["excluded_prior_session_rows"] == 2
    assert source["excluded_incomplete_rows"] == 1
    assert source["row_count"] == 2
    assert source["first_timestamp"] == "2026-09-29T10:01:00"
    assert source["last_timestamp"] == "2026-09-29T10:02:00"
    assert asset["source_metadata"]["5m"]["row_count"] == len(frames["5"])
    assert asset["source_metadata"]["15m"]["row_count"] == len(frames["15"])


def test_collector_rejects_missing_latest_1m_open_from_raw_provider(
        tmp_path, monkeypatch):
    import akshare as ak

    frames, stock, benchmark = _inputs()
    frames["1"].loc[10, "open"] = None
    names = {"time": "时间", "open": "开盘", "high": "最高",
             "low": "最低", "close": "收盘", "volume": "成交量"}

    def provider(symbol, period, adjust):
        assert symbol == "002475"
        assert adjust == ""
        return frames[period].rename(columns=names)

    monkeypatch.setattr(ak, "stock_zh_a_hist_min_em", provider)
    result = decision_replay.collect_acceptance_data(
        tmp_path, {"002475": "立讯精密"},
        fetch_daily_fn=lambda symbol, as_of: (stock, benchmark),
    )

    assert result["assets"][0]["status"] == "FAIL"
    assert "numeric values must be finite" in result["assets"][0]["errors"][0]
    assert not (tmp_path / "002475").exists()


def test_collector_excludes_recent_start_labeled_5m_and_15m_bars(tmp_path):
    frames, stock, benchmark = _inputs()
    frames["1"] = _bars(3, 1)
    frames["1"]["time"] = pd.to_datetime([
        "2026-09-29 09:59", "2026-09-29 10:00", "2026-09-29 10:01"
    ])
    for period in ("5", "15"):
        frames[period].loc[frames[period].index[-1], "time"] = pd.Timestamp(
            "2026-09-29 10:00"
        )
    result = decision_replay.collect_acceptance_data(
        tmp_path, {"002475": "立讯精密"},
        fetch_frames_fn=lambda symbol, periods: (
            frames,
            {period: {"provider": "AKShare/Eastmoney",
                      "fetched_at": "2026-09-29T10:03:30+08:00"}
             for period in periods},
        ),
        fetch_daily_fn=lambda symbol, as_of: (stock, benchmark),
    )

    asset = result["assets"][0]
    assert asset["status"] == "PASS"
    for period in ("5", "15"):
        source = asset["source_metadata"][f"{period}m"]
        assert source["excluded_incomplete_rows"] == 1
        assert source["row_count"] == len(frames[period]) - 1
        saved = pd.read_csv(tmp_path / "002475" / f"{period}m.csv")
        assert saved["time"].iloc[-1] != "2026-09-29 10:00:00"


def test_collector_does_not_write_a_partial_symbol_bundle(tmp_path):
    frames, _, _ = _inputs()

    result = decision_replay.collect_acceptance_data(
        tmp_path, {"002475": "立讯精密"},
        fetch_frames_fn=lambda symbol, periods: (
            {"5": frames["5"]}, {"1": {"error": "source unavailable"}}
        ),
        fetch_daily_fn=lambda symbol, as_of: (None, None),
    )

    assert result["assets"][0]["status"] == "FAIL"
    assert not (tmp_path / "002475").exists()
