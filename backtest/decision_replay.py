"""As-of replay of the actual decision engine for acceptance, not P&L optimization."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
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
    """Fetch public real market data; retain failures and scenario coverage honestly."""
    symbols = symbols or REAL_DATA_UNIVERSE
    report = {
        "purpose": "software and semantic acceptance only; not OOS performance",
        "universe": symbols,
        "timestamp_convention": "input provider bar timestamps treated as completed-bar timestamps; verify provider semantics",
        "strategy_parameters_changed": "NONE",
        "assets": [],
    }
    for symbol, name in symbols.items():
        asset = {"symbol": symbol, "name": name, "status": "FAIL", "errors": []}
        try:
            frames, metas = fetch_frames(symbol, periods=("1", "5", "15"))
            if "5" not in frames or frames["5"].empty:
                raise RuntimeError("no usable 5-minute history")
            last_date = pd.Timestamp(frames["5"]["time"].iloc[-1]).date()
            daily_stock, daily_benchmark = fetch_daily_inputs(symbol, last_date)
            times = pd.to_datetime(frames["5"]["time"])
            count = min(max_samples, len(times))
            indices = np.linspace(0, len(times)-1, count, dtype=int) if count else []
            selected_times = times.iloc[indices].tolist()
            traces = replay_decisions(
                symbol, frames, daily_stock, daily_benchmark,
                decision_times=selected_times,
            )
            asset["source_metadata"] = metas
            asset["sample_count"] = len(traces)
            asset["data_date_range"] = [
                times.iloc[0].isoformat(), times.iloc[-1].isoformat()
            ]
            asset["scenario_coverage"] = sorted({
                tag for trace in traces for tag in trace.get("scenario_tags", [])
            })
            asset["traces"] = traces
            asset["status"] = "PASS" if traces else "FAIL"
            if sample_sleep:
                time.sleep(sample_sleep)
        except Exception as exc:
            asset["errors"].append(f"{type(exc).__name__}: {exc}")
        report["assets"].append(asset)

    report["loaded_assets"] = sum(asset["status"] == "PASS" for asset in report["assets"])
    report["scenario_coverage"] = sorted({
        tag for asset in report["assets"] for tag in asset.get("scenario_coverage", [])
    })
    report["missing_scenarios"] = sorted(
        set(REQUIRED_SCENARIOS) - set(report["scenario_coverage"])
    )
    report["phase1_status"] = (
        "PASS" if report["loaded_assets"] >= 3 and not report["missing_scenarios"]
        else "INCOMPLETE"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="decision-replay-report.json")
    parser.add_argument("--max-samples", type=int, default=120)
    parser.add_argument("--symbols", nargs="*", default=list(REAL_DATA_UNIVERSE))
    args = parser.parse_args()
    symbols = {code: REAL_DATA_UNIVERSE[code] for code in args.symbols}
    report = run_real_data_acceptance(symbols, max_samples=args.max_samples)
    Path(args.output).write_text(
        json.dumps(_as_json(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "loaded_assets": report["loaded_assets"],
        "assets": [
            {"symbol": item["symbol"], "status": item["status"],
             "sample_count": item.get("sample_count", 0),
             "errors": item["errors"]}
            for item in report["assets"]
        ],
        "scenario_coverage": report["scenario_coverage"],
        "missing_scenarios": report["missing_scenarios"],
        "phase1_status": report["phase1_status"],
    }, ensure_ascii=False))
    print(f"REPORT_PATH={args.output}")
    if report["loaded_assets"] < 3:
        raise SystemExit("fewer than three assets returned usable data")


if __name__ == "__main__":
    main()
