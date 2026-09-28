"""Completed-session relative strength against the CSI 300 price index.

These values are evidence for a human decision recommendation, never orders.
The stock series is qfq-adjusted while the benchmark is a price index; this
comparison excludes benchmark dividends and should not be treated as alpha.
"""
from datetime import timedelta

import pandas as pd


HORIZONS = (1, 5, 20)


def _sessions(frame, as_of):
    if not {"date", "close"}.issubset(frame.columns):
        raise ValueError("daily series requires date and close")
    series = frame.loc[:, ["date", "close"]].copy()
    series["date"] = pd.to_datetime(series["date"], errors="coerce").dt.normalize()
    series["close"] = pd.to_numeric(series["close"], errors="coerce")
    if series.isna().any().any() or (series["close"] <= 0).any():
        raise ValueError("invalid date or close")
    series = series[series["date"] < pd.Timestamp(as_of).normalize()]
    if series["date"].duplicated().any():
        raise ValueError("duplicate session")
    return series.sort_values("date").reset_index(drop=True)


def relative_strength(stock_daily, benchmark_daily, as_of):
    """Return 1/5/20 *session* excess returns using only completed common bars.

    as_of is the intraday decision date. An incomplete same-day daily bar is
    excluded, and the newest completed dates must agree across both sources.
    """
    try:
        stock = _sessions(stock_daily, as_of)
        benchmark = _sessions(benchmark_daily, as_of)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {"status": "INVALID_DATA", "reason": str(exc)}
    if stock.empty or benchmark.empty:
        return {"status": "INSUFFICIENT_HISTORY"}
    if stock["date"].iloc[-1] != benchmark["date"].iloc[-1]:
        return {"status": "UNALIGNED", "reason": "latest completed sessions differ"}
    common = stock.merge(benchmark, on="date", how="inner",
                         suffixes=("_stock", "_benchmark"), validate="one_to_one")
    if len(common) <= max(HORIZONS):
        return {"status": "INSUFFICIENT_HISTORY", "common_sessions": len(common)}
    result = {"status": "PASS", "as_of": common["date"].iloc[-1].date().isoformat(),
              "benchmark": "CSI300_PRICE_INDEX", "common_sessions": len(common)}
    for horizon in HORIZONS:
        stock_return = common["close_stock"].iloc[-1] / common["close_stock"].iloc[-1-horizon] - 1
        benchmark_return = common["close_benchmark"].iloc[-1] / common["close_benchmark"].iloc[-1-horizon] - 1
        result[f"{horizon}d"] = float(stock_return - benchmark_return)
    return result


def fetch_relative_strength(symbol, as_of):
    """Fetch daily A-share and CSI 300 history, then apply completed-bar rules."""
    import akshare as ak

    start = (as_of - timedelta(days=120)).strftime("%Y%m%d")
    end = as_of.strftime("%Y%m%d")
    stock = ak.stock_zh_a_hist(symbol=str(symbol).zfill(6), period="daily",
                               start_date=start, end_date=end, adjust="qfq")
    benchmark = ak.stock_zh_index_daily(symbol="sh000300")
    stock = stock.rename(columns={"日期": "date", "收盘": "close"})
    benchmark = benchmark.rename(columns={"日期": "date", "收盘": "close"})
    return relative_strength(stock, benchmark, as_of)
