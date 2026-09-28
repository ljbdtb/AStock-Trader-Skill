"""As-of replay of the actual decision engine for acceptance, not P&L optimization."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import hashlib
from pathlib import Path
import time

import numpy as np
import pandas as pd

from astock_trader.card import render_card
from astock_trader.data import fetch_frames
from astock_trader.decision import decide
from astock_trader.indicators import add_indicators
from astock_trader.multitimeframe import alignment, timeframe_snapshot
from astock_trader.position import PositionLedger
from astock_trader.relative_strength import relative_strength
from astock_trader.risk import market_data_quality
from astock_trader.structure import structure_snapshot


SHANGHAI = timezone(timedelta(hours=8))
REAL_DATA_UNIVERSE = {
    "002475": "立讯精密",
    "002594": "比亚迪",
    "300750": "宁德时代",
    "601138": "工业富联",
    "300308": "中际旭创",
    "600519": "贵州茅台",
}
REQUIRED_SCENARIOS = (
    "UPTREND", "DOWNTREND", "RANGE", "BREAKOUT",
    "FALSE_BREAKOUT", "REVERSAL", "GAP_UP", "GAP_DOWN",
    "HIGH_VOLATILITY", "LOW_VOLUME", "STRUCTURAL_INVALIDATION",
    "STALE_OR_MISSING_DATA",
)


def _local_naive(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("Asia/Shanghai").tz_localize(None)
    return stamp


def _aware(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("Asia/Shanghai")
    else:
        stamp = stamp.tz_convert("Asia/Shanghai")
    return stamp.to_pydatetime()


def _as_json(value):
    if isinstance(value, dict):
        return {str(key): _as_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_json(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if value is pd.NA or (isinstance(value, float) and not np.isfinite(value)):
        return None
    return value


def _prefix(frame, cutoff):
    if frame is None or frame.empty or "time" not in frame:
        return pd.DataFrame(columns=getattr(frame, "columns", []))
    times = pd.to_datetime(frame["time"], errors="coerce")
    visible = frame.loc[times <= _local_naive(cutoff)].copy()
    visible["time"] = pd.to_datetime(visible["time"], errors="coerce")
    return visible.reset_index(drop=True)


def _position_trace(position):
    if position is None:
        return {"provided": False}
    return {
        "provided": True,
        "trading_date": position.trading_date.isoformat(),
        "total_shares": position.total_shares,
        "core_shares": position.core_shares,
        "t_shares": position.t_shares,
        "sellable_core": position.sellable_core_shares,
        "sellable_t": position.sellable_t_shares,
        "sellable_total": position.sellable_shares,
        "bought_today": position.bought_today,
        "sold_t_today": position.sold_t_today,
        "bought_back_t_today": position.bought_back_t_today,
        "buyback_remaining": position.buyback_remaining,
    }



def _validate_market_frame(frame, kind):
    """Validate canonical local replay input without sorting or repairing it."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{kind}: file is empty or not a table")
    required = ({"time", "open", "high", "low", "close", "volume"}
                if kind in {"1", "5", "15"} else {"date", "close"})
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{kind}: missing required columns {missing}")
    data = frame.copy()
    time_col = "time" if kind in {"1", "5", "15"} else "date"
    data[time_col] = pd.to_datetime(data[time_col], errors="coerce")
    if data[time_col].isna().any():
        raise ValueError(f"{kind}: invalid {time_col}")
    if data[time_col].duplicated().any():
        raise ValueError(f"{kind}: duplicate {time_col}")
    if not data[time_col].is_monotonic_increasing:
        raise ValueError(f"{kind}: {time_col} must already be sorted")

    numeric = ["close"] if kind.startswith("daily_") else [
        "open", "high", "low", "close", "volume"
    ]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if not np.isfinite(data[numeric].to_numpy(dtype=float)).all():
        raise ValueError(f"{kind}: numeric values must be finite and non-missing")
    if (data.close <= 0).any():
        raise ValueError(f"{kind}: close must be positive")
    if not kind.startswith("daily_"):
        if (data[["open", "high", "low", "close"]] <= 0).any().any():
            raise ValueError(f"{kind}: OHLC values must be positive")
        if (data.volume < 0).any():
            raise ValueError(f"{kind}: volume must be nonnegative")
        if ((data.high < data[["open", "close", "low"]].max(axis=1))
                | (data.low > data[["open", "close", "high"]].min(axis=1))).any():
            raise ValueError(f"{kind}: invalid OHLC relationship")
    return data.reset_index(drop=True)


def _file_for(directory, stem):
    candidates = [directory / f"{stem}{suffix}"
                  for suffix in (".csv", ".parquet")
                  if (directory / f"{stem}{suffix}").is_file()]
    if len(candidates) != 1:
        raise ValueError(f"{stem}: expected exactly one .csv or .parquet file")
    return candidates[0]


def _source_metadata(frame, source_type, source_file, symbol, timeframe,
                     checksum=None, provider=None, data_origin=None):
    column = "time" if timeframe in {"1", "5", "15"} else "date"
    if checksum is None:
        serialized = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
        checksum = hashlib.sha256(serialized).hexdigest()
    metadata = {
        "source_type": source_type, "source_file": source_file,
        "provider": provider, "symbol": str(symbol), "timeframe": timeframe,
        "first_timestamp": pd.Timestamp(frame[column].iloc[0]).isoformat(),
        "last_timestamp": pd.Timestamp(frame[column].iloc[-1]).isoformat(),
        "row_count": int(len(frame)), "checksum": checksum,
    }
    if data_origin:
        metadata["data_origin"] = data_origin
    return metadata


def load_local_symbol(directory, symbol, data_origin="SYNTHETIC_FIXTURE"):
    """Load one canonical bundle. data_origin is a user attestation, not verified."""
    if data_origin not in {"REAL_HISTORICAL", "SYNTHETIC_FIXTURE"}:
        raise ValueError("data_origin must be REAL_HISTORICAL or SYNTHETIC_FIXTURE")
    directory = Path(directory)
    files = {
        "1": _file_for(directory, "1m"), "5": _file_for(directory, "5m"),
        "15": _file_for(directory, "15m"),
        "daily_stock": _file_for(directory, "daily_stock"),
        "daily_csi300": _file_for(directory, "daily_csi300"),
    }
    loaded, metadata = {}, {}
    for timeframe, path in files.items():
        if path.suffix.lower() == ".csv":
            raw = pd.read_csv(path)
        else:
            raw = pd.read_parquet(path)
        frame = _validate_market_frame(raw, timeframe)
        loaded[timeframe] = frame
        metadata[timeframe] = _source_metadata(
            frame, "LOCAL_FIXTURE", f"{symbol}/{path.name}", symbol, timeframe,
            checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            data_origin=data_origin,
        )
    return (
        {period: loaded[period] for period in ("1", "5", "15")},
        loaded["daily_stock"], loaded["daily_csi300"], metadata,
    )


def _sample_times(frame, max_samples):
    if max_samples < 1:
        raise ValueError("max_samples must be at least 1")
    times = pd.to_datetime(frame["time"])
    count = min(max_samples, len(times))
    indices = np.linspace(0, len(times) - 1, count, dtype=int) if count else []
    return times.iloc[indices].tolist()


def _trace_failures(trace):
    failures = []
    components = trace.get("score_components")
    if not isinstance(components, dict) or sum(components.values()) != trace.get("score_total"):
        failures.append("SCORE_COMPONENT_SUM")
    cutoff = pd.Timestamp(trace["timestamp"])
    for period, stamp in trace.get("mtf", {}).get("source_timestamps", {}).items():
        if pd.Timestamp(stamp) > cutoff:
            failures.append(f"MTF_FUTURE_BAR_{period}")
    rs = trace.get("relative_strength", {})
    if rs.get("status") == "PASS" and pd.Timestamp(rs["as_of"]).date() >= cutoff.date():
        failures.append("RS_INCOMPLETE_SESSION")
    position = trace.get("position_constraints", {})
    limits = trace.get("constraints", {})
    if limits.get("max_reducible_qty", 0) > position.get("sellable_core", 0):
        failures.append("REDUCE_T1_LIMIT")
    if limits.get("max_sell_t_qty", 0) > position.get("sellable_t", 0):
        failures.append("SELL_T1_LIMIT")
    if limits.get("max_buyback_t_qty", 0) > position.get("buyback_remaining", 0):
        failures.append("BUYBACK_LEDGER_LIMIT")
    risk = trace.get("risk", {})
    if risk.get("active") and trace.get("data_quality") == "PASS":
        if trace["recommendation"]["t_action"] != "WAIT":
            failures.append("RISK_DID_NOT_CANCEL_T_ACTION")
        if position.get("provided") and position.get("sellable_core", 0) > 0:
            if trace["recommendation"]["action"] != "REDUCE":
                failures.append("RISK_PRIORITY")
    structure = trace.get("structure", {})
    if (structure.get("bias") != trace.get("structure_bias")
            or structure.get("breakout_status") != trace.get("breakout_status")):
        failures.append("STRUCTURE_SNAPSHOT_MISMATCH")
    card = trace.get("card", "")
    if ("决策辅助建议（非委托）" not in card
            or f'评分: {trace.get("score_total")}/100' not in card):
        failures.append("CARD_TRACE_MISMATCH")
    return failures


def _mutate_future(frames, stock_daily, benchmark_daily, decision_time):
    cutoff = _local_naive(decision_time)
    changed = {key: frame.copy() for key, frame in frames.items()}
    for key, frame in changed.items():
        times = pd.to_datetime(frame["time"])
        future = times > cutoff
        if future.any():
            frame.loc[future, ["open", "high", "low", "close"]] = [500, 600, 400, 550]
            frame.loc[future, "volume"] = 1e9
        else:
            next_time = max(times.max(), cutoff) + pd.Timedelta(minutes=int(key))
            extra = pd.DataFrame({
                "time": [next_time], "open": [500.0], "high": [600.0],
                "low": [400.0], "close": [550.0], "volume": [1e9],
            })
            changed[key] = pd.concat([frame, extra], ignore_index=True)
    daily_frames = []
    for frame in (stock_daily, benchmark_daily):
        copy = frame.copy()
        if not {"date", "close"}.issubset(copy.columns) or copy.empty:
            daily_frames.append(copy)
            continue
        dates = pd.to_datetime(copy["date"])
        future = dates.dt.date >= pd.Timestamp(decision_time).date()
        if future.any():
            copy.loc[future, "close"] = 999999.0
        else:
            next_date = max(dates.max().normalize(),
                            pd.Timestamp(decision_time).normalize()) + pd.Timedelta(days=1)
            copy = pd.concat([
                copy, pd.DataFrame({"date": [next_date], "close": [999999.0]})
            ], ignore_index=True)
        daily_frames.append(copy)
    return changed, daily_frames[0], daily_frames[1]


def _causality_failures(symbol, frames, stock_daily, benchmark_daily, decision_times):
    failures = []
    if not decision_times:
        return failures
    indices = sorted(set((0, len(decision_times) // 2, len(decision_times) - 1)))
    for index in indices:
        stamp = decision_times[index]
        baseline = replay_decisions(
            symbol, frames, stock_daily, benchmark_daily, decision_times=[stamp]
        )[0]
        mutated_frames, mutated_stock, mutated_benchmark = _mutate_future(
            frames, stock_daily, benchmark_daily, stamp
        )
        mutated = replay_decisions(
            symbol, mutated_frames, mutated_stock, mutated_benchmark,
            decision_times=[stamp],
        )[0]
        if baseline != mutated:
            failures.append(pd.Timestamp(stamp).isoformat())
    return failures


def _finalize_acceptance(report):
    assets = report["assets"]
    usable = [
        asset for asset in assets
        if asset.get("trace_count", 0) >= 30 and len(asset.get("regimes_seen", [])) > 0
    ]
    schema_failures = sum(len(asset.get("schema_failures", [])) for asset in assets)
    causal_failures = sum(len(asset.get("causality_failures", [])) for asset in assets)
    trace_failures = sum(len(asset.get("decision_trace_failures", [])) for asset in assets)
    genuine_usable = [
        asset for asset in usable
        if asset.get("data_origin") == "REAL_HISTORICAL"
        or asset.get("source_type") == "LIVE_PROVIDER"
    ]
    regimes = sorted({regime for asset in genuine_usable for regime in asset.get("regimes_seen", [])})
    status = (
        "PASS" if len(genuine_usable) >= 3 and len(regimes) > 1
        and schema_failures == 0 and causal_failures == 0 and trace_failures == 0
        else "INCOMPLETE"
    )
    report.update({
        "usable_symbols": len(usable),
        "eligible_real_symbols": len(genuine_usable),
        "total_decisions": sum(asset.get("trace_count", 0) for asset in assets),
        "regimes_seen": regimes,
        "data_sources": [
            {"symbol": asset["symbol"], "source_type": asset.get("source_type"),
             "data_origin": asset.get("data_origin"),
             "timeframes": sorted(asset.get("source_metadata", {}).keys())}
            for asset in assets
        ],
        "provider_failures": sum(
            int(asset.get("provider_failures", 0)) for asset in assets
        ),
        "schema_failures": schema_failures,
        "causality_failures": causal_failures,
        "decision_trace_failures": trace_failures,
        "REAL_DATA_ACCEPTANCE": status,
        "phase1_status": status,
        "scenario_coverage": sorted({
            tag for asset in assets for tag in asset.get("scenario_coverage", [])
        }),
    })
    report["missing_scenarios"] = sorted(
        set(REQUIRED_SCENARIOS) - set(report["scenario_coverage"])
    )
    return report


def run_local_data_acceptance(input_dir, symbols=None, max_samples=120,
                              data_origin="SYNTHETIC_FIXTURE"):
    """Replay local files through the same engine path used for provider data."""
    root = Path(input_dir)
    symbols = symbols or {
        path.name: REAL_DATA_UNIVERSE.get(path.name, path.name)
        for path in sorted(root.iterdir()) if path.is_dir()
    }
    report = {
        "purpose": "software and semantic acceptance only; not OOS performance",
        "input_mode": "LOCAL_FILES",
        "data_origin_attestation": data_origin,
        "data_origin_note": "User-provided label; file contents are not independently authenticated.",
        "timestamp_convention": "input timestamps treated as completed-bar timestamps; verify source semantics",
        "strategy_parameters_changed": "NONE",
        "assets": [],
    }
    for symbol, name in symbols.items():
        asset = {
            "symbol": str(symbol), "name": name, "source_type": "LOCAL_FIXTURE",
            "data_origin": data_origin, "status": "FAIL", "errors": [],
            "schema_failures": [], "causality_failures": [],
            "decision_trace_failures": [], "provider_failures": 0,
        }
        try:
            frames, stock_daily, benchmark_daily, source_metadata = load_local_symbol(
                root / str(symbol), symbol, data_origin=data_origin
            )
            asset["source_metadata"] = source_metadata
            decision_times = _sample_times(frames["5"], max_samples)
            traces = replay_decisions(
                symbol, frames, stock_daily, benchmark_daily,
                decision_times=decision_times,
            )
            asset["traces"] = traces
            asset["trace_count"] = len(traces)
            asset["regimes_seen"] = sorted({
                trace.get("regime") for trace in traces if trace.get("regime")
            })
            asset["scenario_coverage"] = sorted({
                tag for trace in traces for tag in trace.get("scenario_tags", [])
            })
            asset["causality_checks"] = min(3, len(decision_times))
            asset["causality_failures"] = _causality_failures(
                symbol, frames, stock_daily, benchmark_daily, decision_times
            )
            asset["decision_trace_failures"] = [
                {"timestamp": trace.get("timestamp"), "failures": _trace_failures(trace)}
                for trace in traces if _trace_failures(trace)
            ]
            asset["data_date_range"] = [
                pd.Timestamp(frames["5"]["time"].iloc[0]).isoformat(),
                pd.Timestamp(frames["5"]["time"].iloc[-1]).isoformat(),
            ]
            asset["status"] = "PASS" if traces else "FAIL"
        except Exception as exc:
            asset["errors"].append(f"{type(exc).__name__}: {exc}")
            if str(exc).startswith(("1:", "5:", "15:", "1m:", "5m:", "15m:", "daily_stock:", "daily_csi300:")) or "missing required timeframe" in str(exc):
                asset["schema_failures"].append(str(exc))
        report["assets"].append(asset)
    return _finalize_acceptance(report)




def replay_decisions(symbol, frames, stock_daily, benchmark_daily, decision_times=None,
                     position_provider=None, max_age_minutes=15):
    """Replay decisions without exposing bars later than each requested timestamp.

    Intraday timestamps are interpreted as completed-bar timestamps. Callers must
    verify their provider's timestamp convention before using this as market evidence.
    """
    if "5" not in frames:
        raise ValueError("replay requires a 5-minute frame")
    primary = frames["5"]
    if primary.empty or "time" not in primary:
        raise ValueError("replay requires timestamped 5-minute bars")
    if decision_times is None:
        decision_times = pd.to_datetime(primary["time"]).tolist()

    traces = []
    previous_risk = None
    for decision_time in decision_times:
        cutoff = _aware(decision_time)
        visible = {period: _prefix(frame, cutoff) for period, frame in frames.items()}
        bars5 = visible["5"]
        if bars5.empty:
            traces.append({
                "symbol": str(symbol), "timestamp": cutoff.isoformat(),
                "data_quality": "FAIL", "data_as_of": None,
                "reason_codes": ["NO_BAR_AS_OF_DECISION_TIME"],
                "recommendation": {"action": "WAIT", "t_action": "WAIT"},
            })
            continue

        ready = {period: add_indicators(frame) for period, frame in visible.items()
                 if not frame.empty}
        frame5 = ready["5"]
        latest_time = pd.Timestamp(bars5["time"].iloc[-1])
        meta = {"data_time": latest_time.isoformat()}
        data_ok = (
            len(frame5) >= 25
            and market_data_quality(
                frame5, meta, now=cutoff, max_age_minutes=max_age_minutes
            )
        )
        snapshot = structure_snapshot(frame5)
        timeframe_views = {
            period: timeframe_snapshot(frame)
            for period, frame in ready.items()
            if period in {"1", "5", "15"} and len(frame) >= 25
        }
        complete_mtf = set(timeframe_views) == {"1", "5", "15"}
        mtf_alignment = alignment(timeframe_views) if complete_mtf else 0.0
        mtf_timestamps = {
            period: _aware(visible[period]["time"].iloc[-1]).isoformat()
            for period in timeframe_views
        }
        rs = relative_strength(
            stock_daily, benchmark_daily, as_of=cutoff.date()
        ) if stock_daily is not None and benchmark_daily is not None else {
            "status": "MISSING_DATA"
        }
        position = (position_provider(cutoff) if callable(position_provider)
                    else position_provider)
        output = decide(
            frame5, mtf_alignment=mtf_alignment, relative_strength=rs,
            position=position, data_ok=data_ok, previous_risk=previous_risk,
            snapshot=snapshot,
        )
        previous_risk = {
            "active": output["risk_active"],
            "reference_level": output["structural_reference_level"],
            "reference_type": output["structural_reference_type"],
            "invalidation_level": output["structural_invalidation_level"],
        }
        row = frame5.iloc[-1]
        atr_pct = (float(row.atr14 / row.close)
                   if pd.notna(row.get("atr14")) and float(row.close) > 0 else None)
        card_data = {
            **output, "symbol": str(symbol), "data_time": latest_time.isoformat(),
            "provider": "historical replay input",
            "mtf_alignment": mtf_alignment,
            "mtf_status": "PASS" if complete_mtf else "INCOMPLETE",
            "relative_strength": rs,
        }
        high_volume_gap = None
        if len(bars5) >= 2:
            previous_close = float(bars5.close.iloc[-2])
            if previous_close > 0:
                high_volume_gap = float(bars5.open.iloc[-1] / previous_close - 1)
        trace = {
            "symbol": str(symbol),
            "timestamp": cutoff.isoformat(),
            "data_quality": "PASS" if data_ok else "FAIL",
            "data_as_of": latest_time.isoformat(),
            "structure_bias": snapshot.get("bias"),
            "breakout_status": snapshot.get("breakout_status"),
            "structure": {
                key: snapshot.get(key) for key in (
                    "high_state", "low_state", "bias", "support", "support_source",
                    "resistance", "resistance_source", "breakout_status",
                    "breakout_level", "confirmed_swing_high", "confirmed_swing_low",
                    "as_of",
                )
            },
            "regime": output["regime"],
            "mtf": {
                "alignment": mtf_alignment,
                "status": card_data["mtf_status"],
                "source_timeframes": sorted(timeframe_views),
                "source_timestamps": mtf_timestamps,
            },
            "relative_strength": rs,
            "score_components": output["score_components"],
            "score_total": output["score"],
            "risk": {
                "active": output["risk_active"],
                "reference_level": output["structural_reference_level"],
                "invalidation_level": output["structural_invalidation_level"],
                "status": output["risk_status"],
                "reason_codes": output["risk_reason_codes"],
            },
            "position_constraints": _position_trace(position),
            "recommendation": {
                "action": output["action"], "t_action": output["t_action"],
                "decision_status": output["decision_status"],
            },
            "constraints": {
                "max_reducible_qty": output["max_reducible_qty"],
                "max_sell_t_qty": output["max_sell_t_qty"],
                "max_buyback_t_qty": output["max_buyback_t_qty"],
            },
            "scenario_tags": _scenario_tags(
                output, atr_pct, snapshot, high_volume_gap
            ),
            "card": render_card(card_data),
        }
        traces.append(_as_json(trace))
    return traces


def _scenario_tags(output, atr_pct, snapshot, gap):
    tags = []
    regime = str(output["regime"]).upper()
    if regime in {"UPTREND", "STRONG_UPTREND"}:
        tags.append("UPTREND")
    if regime == "DOWNTREND":
        tags.append("DOWNTREND")
    if regime == "RANGE":
        tags.append("RANGE")
    if regime in {"BREAKOUT", "BREAKOUT_ATTEMPT"}:
        tags.append("BREAKOUT")
    if regime == "FALSE_BREAKOUT":
        tags.append("FALSE_BREAKOUT")
    if regime == "REVERSAL":
        tags.append("REVERSAL")
    if gap is not None and gap >= 0.02:
        tags.append("GAP_UP")
    if gap is not None and gap <= -0.02:
        tags.append("GAP_DOWN")
    if atr_pct is not None and atr_pct >= 0.03:
        tags.append("HIGH_VOLATILITY")
    if float(snapshot.get("volume_ratio", 1.0)) < 0.5:
        tags.append("LOW_VOLUME")
    if output["risk_active"]:
        tags.append("STRUCTURAL_INVALIDATION")
    if output["data_quality"] != "PASS":
        tags.append("STALE_OR_MISSING_DATA")
    return tags


def fetch_daily_inputs(symbol, as_of):
    import akshare as ak

    start = (as_of - timedelta(days=120)).strftime("%Y%m%d")
    end = as_of.strftime("%Y%m%d")
    stock = ak.stock_zh_a_hist(
        symbol=str(symbol).zfill(6), period="daily", start_date=start,
        end_date=end, adjust="qfq",
    ).rename(columns={"日期": "date", "收盘": "close"})
    benchmark = ak.stock_zh_index_daily(symbol="sh000300")
    return stock, benchmark



def run_real_data_acceptance(symbols=None, max_samples=120, sample_sleep=0.0):
    """Fetch public historical data and report provider/data/causality failures."""
    symbols = symbols or REAL_DATA_UNIVERSE
    report = {
        "purpose": "software and semantic acceptance only; not OOS performance",
        "input_mode": "LIVE_PROVIDER",
        "timestamp_convention": "provider bar timestamps treated as completed-bar timestamps; verify source semantics",
        "strategy_parameters_changed": "NONE",
        "assets": [],
    }
    for symbol, name in symbols.items():
        asset = {
            "symbol": str(symbol), "name": name, "source_type": "LIVE_PROVIDER",
            "data_origin": "LIVE_PROVIDER", "status": "FAIL", "errors": [],
            "schema_failures": [], "causality_failures": [],
            "decision_trace_failures": [], "provider_failures": 0,
        }
        try:
            frames, provider_meta = fetch_frames(symbol, periods=("1", "5", "15"))
            missing_periods = {"1", "5", "15"} - set(frames)
            if missing_periods:
                asset["provider_failures"] = 1
                raise RuntimeError(
                    f"provider omitted required timeframe data {sorted(missing_periods)}; "
                    f"provider results: {provider_meta}"
                )
            frames = {
                period: _validate_market_frame(frames[period], period)
                for period in ("1", "5", "15")
            }
            if frames["5"].empty:
                raise RuntimeError(f"no usable 5-minute history; provider results: {provider_meta}")
            last_date = pd.Timestamp(frames["5"]["time"].iloc[-1]).date()
            stock_daily, benchmark_daily = fetch_daily_inputs(symbol, last_date)
            source_metadata = {
                period: _source_metadata(
                    frame, "LIVE_PROVIDER", None, symbol, period, provider="AKShare",
                    data_origin="LIVE_PROVIDER",
                )
                for period, frame in frames.items() if period in {"1", "5", "15"}
            }
            stock_clean = _validate_market_frame(
                stock_daily.rename(columns={"日期": "date", "收盘": "close"}),
                "daily_stock",
            )
            benchmark_clean = _validate_market_frame(benchmark_daily, "daily_csi300")
            source_metadata["daily_stock"] = _source_metadata(
                stock_clean, "LIVE_PROVIDER", None, symbol, "daily_stock",
                provider="AKShare", data_origin="LIVE_PROVIDER",
            )
            source_metadata["daily_csi300"] = _source_metadata(
                benchmark_clean, "LIVE_PROVIDER", None, "sh000300", "daily_csi300",
                provider="AKShare", data_origin="LIVE_PROVIDER",
            )
            asset["source_metadata"] = source_metadata
            decision_times = _sample_times(frames["5"], max_samples)
            traces = replay_decisions(
                symbol, frames, stock_clean, benchmark_clean,
                decision_times=decision_times,
            )
            asset["traces"] = traces
            asset["trace_count"] = len(traces)
            asset["regimes_seen"] = sorted({
                trace.get("regime") for trace in traces if trace.get("regime")
            })
            asset["scenario_coverage"] = sorted({
                tag for trace in traces for tag in trace.get("scenario_tags", [])
            })
            asset["causality_checks"] = min(3, len(decision_times))
            asset["causality_failures"] = _causality_failures(
                symbol, frames, stock_clean, benchmark_clean, decision_times
            )
            asset["decision_trace_failures"] = [
                {"timestamp": trace.get("timestamp"), "failures": failures}
                for trace in traces if (failures := _trace_failures(trace))
            ]
            times = pd.to_datetime(frames["5"]["time"])
            asset["data_date_range"] = [times.iloc[0].isoformat(), times.iloc[-1].isoformat()]
            asset["status"] = "PASS" if traces else "FAIL"
            if sample_sleep:
                time.sleep(sample_sleep)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            asset["errors"].append(message)
            if str(exc).startswith(("1:", "5:", "15:", "1m:", "5m:", "15m:", "daily_stock:", "daily_csi300:")):
                asset["schema_failures"].append(message)
            elif not asset.get("source_metadata"):
                asset["provider_failures"] = max(asset.get("provider_failures", 0), 1)
        report["assets"].append(asset)
    report = _finalize_acceptance(report)
    report["loaded_assets"] = sum(asset["status"] == "PASS" for asset in report["assets"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="decision-replay-report.json")
    parser.add_argument("--max-samples", type=int, default=120)
    parser.add_argument("--symbols", nargs="*", default=list(REAL_DATA_UNIVERSE),
                        choices=list(REAL_DATA_UNIVERSE))
    parser.add_argument(
        "--input-dir",
        help="Local bundle root; expects <input-dir>/<symbol>/{1m,5m,15m,daily_stock,daily_csi300}.{csv|parquet}",
    )
    parser.add_argument(
        "--input-origin", choices=("REAL_HISTORICAL", "SYNTHETIC_FIXTURE"),
        default="SYNTHETIC_FIXTURE",
        help="Attested local data origin; default prevents synthetic fixtures passing real-data acceptance",
    )
    args = parser.parse_args()
    symbols = {code: REAL_DATA_UNIVERSE[code] for code in args.symbols}
    if args.input_dir:
        report = run_local_data_acceptance(
            args.input_dir, symbols=symbols, max_samples=args.max_samples,
            data_origin=args.input_origin,
        )
    else:
        report = run_real_data_acceptance(symbols, max_samples=args.max_samples)
    Path(args.output).write_text(
        json.dumps(_as_json(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = {
        "REAL_DATA_ACCEPTANCE": report["REAL_DATA_ACCEPTANCE"],
        "usable_symbols": report["usable_symbols"],
        "eligible_real_symbols": report["eligible_real_symbols"],
        "total_decisions": report["total_decisions"],
        "regimes_seen": report["regimes_seen"],
        "schema_failures": report["schema_failures"],
        "causality_failures": report["causality_failures"],
        "decision_trace_failures": report["decision_trace_failures"],
        "provider_failures": report["provider_failures"],
        "assets": [
            {"symbol": asset["symbol"], "status": asset["status"],
             "decision_count": asset.get("trace_count", 0),
             "regimes_seen": asset.get("regimes_seen", []),
             "errors": asset.get("errors", [])}
            for asset in report["assets"]
        ],
    }
    print(json.dumps(summary, ensure_ascii=False))
    print(f"REPORT_PATH={args.output}")
    if report["REAL_DATA_ACCEPTANCE"] != "PASS":
        raise SystemExit("REAL_DATA_ACCEPTANCE is INCOMPLETE; inspect report and data provenance")


if __name__ == "__main__":
    main()
