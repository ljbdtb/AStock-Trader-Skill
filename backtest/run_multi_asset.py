"""Fixed-rule multi-stock OOS generalization check; no per-symbol risk tuning."""
import time

import akshare as ak
import pandas as pd

from backtest.risk_sizing import volatility_target_exposure
from backtest.walk_forward import walk_forward

START = "20150101"
END = "20260922"
TRAIN = 500
TEST = 120
EMBARGO = 5
TARGET_VOL = 0.20
VOL_WINDOW = 20
BUY_COST_BPS = 8.041
SELL_COST_BPS = 13.041
SYMBOLS = {
    "002475": "立讯精密",
    "002594": "比亚迪",
    "300750": "宁德时代",
    "601138": "工业富联",
    "300308": "中际旭创",
    "600519": "贵州茅台",
}
PARAM_GRID = [
    {"fast": 5, "slow": 20},
    {"fast": 10, "slow": 20},
    {"fast": 10, "slow": 30},
    {"fast": 20, "slow": 60},
]


def retry_fetch(fetch, label):
    last_error = None
    for attempt in range(5):
        try:
            return fetch()
        except Exception as exc:
            last_error = exc
            if attempt == 4:
                raise RuntimeError(f"{label} failed after 5 attempts") from last_error
            time.sleep(2**attempt)


def symbol_with_market(code):
    return ("sh" if code.startswith("6") else "sz") + code


def load_daily(code):
    market_symbol = symbol_with_market(code)
    raw = retry_fetch(
        lambda: ak.stock_zh_a_hist_tx(
            symbol=market_symbol,
            start_date=START,
            end_date=END,
            adjust="qfq",
            timeout=30,
        ),
        f"Tencent {market_symbol}",
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
    ).copy()
    required = ["date", "open", "high", "low", "close", "volume"]
    missing_columns = [col for col in required if col not in df.columns]
    if missing_columns:
        raise ValueError(f"{code} provider response missing columns: {missing_columns}")
    df["date"] = pd.to_datetime(df["date"])
    for col in required[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def audit(df, code):
    columns = ["date", "open", "high", "low", "close", "volume"]
    missing = {col: int(df[col].isna().sum()) for col in columns}
    bad_ohlc_mask = (
        (df.high < df[["open", "close", "low"]].max(axis=1))
        | (df.low > df[["open", "close", "high"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    bad_ohlc = int(bad_ohlc_mask.sum())
    bad_rows = df.loc[bad_ohlc_mask, ["date", "open", "high", "low", "close"]]
    report = {
        "symbol": code,
        "source": "AKShare stock_zh_a_hist_tx (Tencent)",
        "adjust": "qfq",
        "rows": len(df),
        "first": str(df.date.iloc[0].date()) if len(df) else None,
        "last": str(df.date.iloc[-1].date()) if len(df) else None,
        "missing": missing,
        "duplicate_dates": int(df.date.duplicated().sum()),
        "bad_ohlc": bad_ohlc,
        "bad_ohlc_rows": bad_rows.to_dict("records"),
        "nonpositive_volume": int((df.volume <= 0).sum()),
        "monotonic_dates": bool(df.date.is_monotonic_increasing),
    }
    report["pass"] = (
        len(df) > TRAIN + EMBARGO + TEST
        and sum(missing.values()) == 0
        and report["duplicate_dates"] == 0
        and bad_ohlc == 0
        and report["nonpositive_volume"] == 0
        and report["monotonic_dates"]
    )
    return report


def signal(df, fast=10, slow=20):
    ema_fast = df.close.ewm(span=fast, adjust=False).mean()
    ema_slow = df.close.ewm(span=slow, adjust=False).mean()
    base = (ema_fast > ema_slow).astype(float)
    # Close-time sizing; shared evaluator shifts once for next-bar execution.
    return base * volatility_target_exposure(
        df.close, target_vol=TARGET_VOL, lookback=VOL_WINDOW, max_position=1.0
    )


def summarize(rows, code, name):
    frame = pd.DataFrame(rows)
    trade_count = int(frame.trade_count.sum())
    gross_profit = float(frame.gross_profit.sum())
    gross_loss = float(frame.gross_loss.sum())
    return {
        "symbol": code,
        "name": name,
        "folds": len(frame),
        "mean_oos_return": float(frame.oos_return.mean()),
        "mean_oos_sharpe": float(frame.oos_sharpe.mean()),
        "worst_drawdown": float(frame.oos_max_drawdown.min()),
        "profitable_windows": int((frame.oos_return > 0).sum()),
        "turnover": float(frame.turnover.sum()),
        "trade_count": trade_count,
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "expectancy": (
            float(frame.trade_return_sum.sum() / trade_count) if trade_count else 0.0
        ),
        "win_rate_mean_fold": float(frame.win_rate.mean()),
        "average_holding_period": float(frame.average_holding_period.mean()),
    }


def main():
    summaries, audits = [], []
    print("FIXED_PROTOCOL", {
        "symbols": SYMBOLS,
        "source": "Tencent via AKShare stock_zh_a_hist_tx for every security",
        "adjust": "qfq",
        "target_vol": TARGET_VOL,
        "vol_lookback": VOL_WINDOW,
        "max_position": 1.0,
        "training": TRAIN,
        "test": TEST,
        "embargo": EMBARGO,
        "ema_grid": PARAM_GRID,
        "buy_cost_bps": BUY_COST_BPS,
        "sell_cost_bps": SELL_COST_BPS,
        "execution": "signal at close t; shared evaluator executes from t+1",
    })

    for code, name in SYMBOLS.items():
        df = load_daily(code)
        report = audit(df, code)
        audits.append(report)
        print("ASSET_AUDIT", report)
        if not report["pass"]:
            raise SystemExit(f"AUDIT_FAIL {code}")
        rows = walk_forward(
            df,
            signal,
            PARAM_GRID,
            train=TRAIN,
            test=TEST,
            embargo=EMBARGO,
            buy_cost_bps=BUY_COST_BPS,
            sell_cost_bps=SELL_COST_BPS,
        )
        if rows.empty:
            raise SystemExit(f"NO_OOS_FOLDS {code}")
        summaries.append(summarize(rows.to_dict("records"), code, name))

    result = pd.DataFrame(summaries)
    result = result.sort_values("symbol").reset_index(drop=True)
    print("MULTI_ASSET_MATRIX")
    print(result.to_csv(index=False))
    print("GENERALIZATION_SUMMARY", {
        "symbols_audited": len(audits),
        "symbols_with_positive_mean_oos_sharpe": int((result.mean_oos_sharpe > 0).sum()),
        "symbols_with_positive_mean_oos_return": int((result.mean_oos_return > 0).sum()),
        "median_mean_oos_sharpe": float(result.mean_oos_sharpe.median()),
        "median_mean_oos_return": float(result.mean_oos_return.median()),
        "all_data_from_same_provider": len({x["source"] for x in audits}) == 1,
        "interpretation": (
            "descriptive generalization check only; selected surviving large-cap names "
            "do not remove survivorship or selection bias"
        ),
    })


if __name__ == "__main__":
    main()
