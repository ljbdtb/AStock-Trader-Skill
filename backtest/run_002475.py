"""002475 OOS comparison: EMA baseline vs long-term trend filter vs buy-and-hold."""
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
COSTS = {
    "buy_cost_bps": 8.041,
    "sell_cost_bps": 13.041,
}


def load_daily():
    last_error = None
    for attempt in range(5):
        try:
            raw = ak.stock_zh_a_hist(
                symbol=SYMBOL,
                period="daily",
                start_date=START,
                end_date=END,
                adjust=ADJUST,
                timeout=30,
            )
            break
        except Exception as exc:
            last_error = exc
            if attempt == 4:
                raise RuntimeError("Eastmoney data download failed after 5 attempts") from last_error
            time.sleep(2**attempt)
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


def audit(df):
    cols = ["date", "open", "high", "low", "close", "volume"]
    missing = {c: int(df[c].isna().sum()) for c in cols}
    bad_ohlc = int(
        (
            (df.high < df[["open", "close", "low"]].max(axis=1))
            | (df.low > df[["open", "close", "high"]].min(axis=1))
            | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        ).sum()
    )
    return {
        "rows": len(df),
        "first": str(df.date.iloc[0].date()),
        "last": str(df.date.iloc[-1].date()),
        "missing": missing,
        "duplicate_dates": int(df.date.duplicated().sum()),
        "bad_ohlc": bad_ohlc,
        "nonpositive_volume": int((df.volume <= 0).sum()),
        "monotonic_dates": bool(df.date.is_monotonic_increasing),
        "source": "AKShare stock_zh_a_hist / Eastmoney",
        "adjust": ADJUST,
    }


def ema_signal(df, fast=10, slow=20):
    fast_ma = df.close.ewm(span=fast, adjust=False).mean()
    slow_ma = df.close.ewm(span=slow, adjust=False).mean()
    return (fast_ma > slow_ma).astype(float)


def filtered_ema_signal(df, fast=10, slow=20, trend=200):
    base = ema_signal(df, fast=fast, slow=slow)
    long_ma = df.close.rolling(trend, min_periods=trend).mean()
    return (base.eq(1) & df.close.gt(long_ma)).astype(float)


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
    report = audit(df)
    ok = (
        len(df) > TRAIN + EMBARGO + TEST
        and sum(report["missing"].values()) == 0
        and report["duplicate_dates"] == 0
        and report["bad_ohlc"] == 0
        and report["nonpositive_volume"] == 0
        and report["monotonic_dates"]
    )
    print("AUDIT_STATUS", "PASS" if ok else "FAIL")
    print("DATA_AUDIT", report)
    print("COSTS", COSTS)
    if not ok:
        raise SystemExit(2)

    baseline_grid = [
        {"fast": 5, "slow": 20},
        {"fast": 10, "slow": 20},
        {"fast": 10, "slow": 30},
        {"fast": 20, "slow": 60},
    ]
    filtered_grid = [
        {"fast": 5, "slow": 20, "trend": 200},
        {"fast": 10, "slow": 20, "trend": 200},
        {"fast": 10, "slow": 30, "trend": 200},
        {"fast": 20, "slow": 60, "trend": 200},
    ]
    baseline = walk_forward(
        df, ema_signal, baseline_grid, train=TRAIN, test=TEST, embargo=EMBARGO, **COSTS
    )
    filtered = walk_forward(
        df,
        filtered_ema_signal,
        filtered_grid,
        train=TRAIN,
        test=TEST,
        embargo=EMBARGO,
        **COSTS,
    )

    bh_rows = []
    for fold, (_, te) in enumerate(folds(len(df)), 1):
        test_df = df.iloc[te]
        position = pd.Series(1.0, index=test_df.index)
        metric = evaluate(test_df.close, position, **COSTS)
        bh_rows.append(
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
        summarize(filtered.to_dict("records"), "EMA + 200-day trend filter"),
        summarize(bh_rows, "Buy-and-hold"),
    ]
    print("OOS_COMPARISON")
    for summary, frame in results:
        print("SUMMARY", summary)
        print(frame.to_csv(index=False))

    baseline_mean = results[0][0]["mean_oos_sharpe"]
    filtered_mean = results[1][0]["mean_oos_sharpe"]
    filtered_dd = results[1][0]["worst_oos_drawdown"]
    print(
        "CANDIDATE_GATE",
        {
            "sharpe_improved": filtered_mean > baseline_mean,
            "worst_drawdown_below_25pct": filtered_dd >= -0.25,
            "research_candidate": filtered_mean > baseline_mean and filtered_dd >= -0.25,
        },
    )


if __name__ == "__main__":
    main()
