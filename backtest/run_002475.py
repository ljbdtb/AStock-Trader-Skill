"""002475 OOS comparison of EMA position sizing and CSI 300 benchmark."""
import akshare as ak
import pandas as pd
import time

from backtest.walk_forward import evaluate, walk_forward

SYMBOL = "002475"
START = "20150101"
END = "20260922"
ADJUST = "qfq"
TRAIN = 500
TEST = 120
EMBARGO = 5
TARGET_VOL = 0.20
VOL_WINDOW = 20
TREND_WINDOW = 200
COSTS = {"buy_cost_bps": 8.041, "sell_cost_bps": 13.041}


def retry_fetch(fetch, label):
    last_error = None
    for attempt in range(5):
        try:
            return fetch()
        except Exception as exc:
            last_error = exc
            if attempt == 4:
                raise RuntimeError(f"{label} download failed after 5 attempts") from last_error
            time.sleep(2**attempt)


def load_daily():
    raw = retry_fetch(
        lambda: ak.stock_zh_a_hist(
            symbol=SYMBOL,
            period="daily",
            start_date=START,
            end_date=END,
            adjust=ADJUST,
            timeout=30,
        ),
        "002475",
    )
    df = raw.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def load_csi300():
    index = retry_fetch(
        lambda: ak.stock_zh_index_daily(symbol="sh000300"),
        "CSI 300",
    )
    index["date"] = pd.to_datetime(index["date"])
    index["close"] = pd.to_numeric(index["close"], errors="coerce")
    return index.loc[
        index.date.between(pd.Timestamp("2015-01-01"), pd.Timestamp("2026-09-22")),
        ["date", "close"],
    ].dropna().sort_values("date").reset_index(drop=True)


def audit(df, benchmark):
    cols = ["date", "open", "high", "low", "close", "volume"]
    missing = {c: int(df[c].isna().sum()) for c in cols}
    bad_ohlc = int(
        (
            (df.high < df[["open", "close", "low"]].max(axis=1))
            | (df.low > df[["open", "close", "high"]].min(axis=1))
            | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        ).sum()
    )
    overlap = int(df.date.isin(benchmark.date).sum())
    return {
        "rows": len(df),
        "first": str(df.date.iloc[0].date()),
        "last": str(df.date.iloc[-1].date()),
        "missing": missing,
        "duplicate_dates": int(df.date.duplicated().sum()),
        "bad_ohlc": bad_ohlc,
        "nonpositive_volume": int((df.volume <= 0).sum()),
        "monotonic_dates": bool(df.date.is_monotonic_increasing),
        "csi300_rows_in_period": len(benchmark),
        "common_trading_dates": overlap,
        "source": "AKShare stock_zh_a_hist / Eastmoney",
        "adjust": ADJUST,
        "benchmark": "CSI 300 price index (sh000300, no dividends)",
    }


def ema_signal(df, fast=10, slow=20):
    fast_ma = df.close.ewm(span=fast, adjust=False).mean()
    slow_ma = df.close.ewm(span=slow, adjust=False).mean()
    return (fast_ma > slow_ma).astype(float)


def vol_target_ema_signal(df, fast=10, slow=20, use_trend=False):
    base = ema_signal(df, fast=fast, slow=slow)
    returns = df.close.pct_change()
    realized_vol = returns.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std() * (252**0.5)
    # Use only volatility known before today's close/execution.
    exposure = (TARGET_VOL / realized_vol.shift(1)).clip(upper=1.0).fillna(0.0)
    if use_trend:
        long_ma = df.close.rolling(TREND_WINDOW, min_periods=TREND_WINDOW).mean()
        base = base * df.close.gt(long_ma).astype(float)
    return base * exposure


def folds(n):
    start = TRAIN
    while start + EMBARGO + TEST <= n:
        yield slice(0, start), slice(start + EMBARGO, start + EMBARGO + TEST)
        start += TEST


def summarize(rows, label):
    frame = pd.DataFrame(rows)
    summary = {
        "candidate": label,
        "folds": len(frame),
        "mean_oos_return": round(float(frame.oos_return.mean()), 6),
        "median_oos_return": round(float(frame.oos_return.median()), 6),
        "mean_oos_sharpe": round(float(frame.oos_sharpe.mean()), 4),
        "worst_oos_drawdown": round(float(frame.oos_max_drawdown.min()), 6),
        "profitable_folds": int((frame.oos_return > 0).sum()),
        "trades": int(frame.trades.sum()),
    }
    return summary, frame


def main():
    df = load_daily()
    benchmark = load_csi300()
    report = audit(df, benchmark)
    ok = (
        len(df) > TRAIN + EMBARGO + TEST
        and sum(report["missing"].values()) == 0
        and report["duplicate_dates"] == 0
        and report["bad_ohlc"] == 0
        and report["nonpositive_volume"] == 0
        and report["monotonic_dates"]
        and report["common_trading_dates"] == len(df)
    )
    print("AUDIT_STATUS", "PASS" if ok else "FAIL")
    print("DATA_AUDIT", report)
    print("COSTS", COSTS)
    print(
        "RISK_RULE",
        {
            "target_annual_vol": TARGET_VOL,
            "lookback_sessions": VOL_WINDOW,
            "max_gross_exposure": 1.0,
            "volatility_lag_sessions": 1,
            "trend_filter_sessions": TREND_WINDOW,
        },
    )
    if not ok:
        raise SystemExit(2)

    grid = [
        {"fast": 5, "slow": 20},
        {"fast": 10, "slow": 20},
        {"fast": 10, "slow": 30},
        {"fast": 20, "slow": 60},
    ]
    baseline = walk_forward(
        df, ema_signal, grid, train=TRAIN, test=TEST, embargo=EMBARGO, **COSTS
    )
    vol_target = walk_forward(
        df,
        vol_target_ema_signal,
        grid,
        train=TRAIN,
        test=TEST,
        embargo=EMBARGO,
        **COSTS,
    )
    vol_trend = walk_forward(
        df,
        lambda frame, fast, slow: vol_target_ema_signal(
            frame, fast=fast, slow=slow, use_trend=True
        ),
        grid,
        train=TRAIN,
        test=TEST,
        embargo=EMBARGO,
        **COSTS,
    )

    index_rows = []
    for fold, (_, te) in enumerate(folds(len(df)), 1):
        dates = df.iloc[te].date
        test_index = benchmark.loc[benchmark.date.isin(dates)]
        if len(test_index) != len(dates):
            raise RuntimeError(f"CSI 300 date alignment failed in fold {fold}")
        metric = evaluate(
            test_index.close,
            pd.Series(1.0, index=test_index.index),
            **COSTS,
        )
        index_rows.append(
            {
                "fold": fold,
                "oos_return": metric.total_return,
                "oos_sharpe": metric.sharpe,
                "oos_max_drawdown": metric.max_drawdown,
                "trades": metric.trades,
            }
        )

    results = [
        summarize(baseline.to_dict("records"), "EMA walk-forward"),
        summarize(vol_target.to_dict("records"), "EMA + 20% volatility target (max 100%)"),
        summarize(vol_trend.to_dict("records"), "EMA + volatility target + 200-day trend"),
        summarize(index_rows, "CSI 300 buy-and-hold"),
    ]
    print("OOS_COMPARISON")
    for summary, frame in results:
        print("SUMMARY", summary)
        print(frame.to_csv(index=False))

    reference = results[0][0]
    print(
        "RISK_CANDIDATE_GATE",
        {
            "vol_target_sharpe_improved": results[1][0]["mean_oos_sharpe"]
            > reference["mean_oos_sharpe"],
            "vol_target_worst_drawdown_under_25pct": results[1][0][
                "worst_oos_drawdown"
            ]
            >= -0.25,
            "trend_variant_sharpe_improved": results[2][0]["mean_oos_sharpe"]
            > reference["mean_oos_sharpe"],
        },
    )


if __name__ == "__main__":
    main()
