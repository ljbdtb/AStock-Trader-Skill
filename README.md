# AStock-Trader-Skill

AStock-Trader-Skill is an A-share short-term/swing **decision-support engine, not an automated trading system**. It fetches market data, checks freshness, analyzes indicators, structure and regime, applies user-provided position and T+1 constraints, then displays recommendations. A person remains responsible for every trading decision and any execution.

## Evidence model

The fixed 100-point evidence budget comes from `config/strategy.yaml`: structure 25, trend 15, volume/price 15, VWAP 10, momentum 10, volatility 5, CSI300 relative strength 10, and 1/5/15-minute alignment 10. There is no extra Structure bonus in the decision layer. Missing relative-strength or incomplete multi-timeframe evidence earns no points; neither can override a risk gate. These component rules are research hypotheses, **not validated trading edges**.

Relative strength is the stock's qfq-adjusted daily price return minus the CSI300 **price-index** return over 1, 5 and 20 common completed sessions. The intraday decision date is excluded from the daily calculation. This benchmark omits dividends, so the comparison is not a total-return or investable alpha estimate. The JSON and card show the as-of date or an unavailable status; do not present unavailable evidence as neutral or current.

## What it does

- Market analysis, structure/regime classification, and evidence scoring.
- Risk-aware `HOLD`, `WAIT`, `SELL_T`, `BUYBACK_T`, or `REDUCE` recommendations.
- T+1-aware decision constraints and legal *upper bounds*, not exact order sizes.
- Paper/simulated position transitions and backtesting/research.

## What it does not do

No broker API or connection, order placement/router, automatic execution, fill handling, cancel/replace, live trading loop, execution scheduler, automatic brokerage position sync, real-money account control, or `LIVE_TRADING` mode. `PositionLedger` holds user-provided or simulated state for validating a recommendation; its `sell_t`, `buyback_t`, `sell_core`, and `rollover` methods only simulate state transitions. They do not execute or confirm trades.

## Run locally

Install dependencies with `pip install -r requirements.txt`, then run:

```bash
python main.py 002475 --json
```

Without a complete current-day position snapshot, the decision gate returns `WAIT`. For position-aware paper analysis, replace the date and quantities with your actual inputs:

```bash
python main.py 002475 --trading-date YYYY-MM-DD --core-shares 2000 --t-shares 200 --bought-core-today 0 --bought-t-today 0 --sold-t-today 0 --bought-back-t-today 0 --shares 2200 --cost 56 --portfolio-weight 0.30 --json
```

`--shares` must equal core plus T shares. `--portfolio-weight` is a fraction (for example, `0.30` means 30%). The JSON fields `max_reducible_qty`, `max_sell_t_qty`, and `max_buyback_t_qty` are **permitted upper bounds for the displayed recommendation**, never instructions to sell or buy that amount. No `--execute`, `--live`, `--broker`, `--place-order`, or `--auto-trade` mode exists.

Check the data timestamp, quality result, risk reason codes and current position state before interpreting a recommendation. Provider data may be delayed or unavailable. Passing tests does not establish out-of-sample trading advantage or suitability for autonomous real-money decisions.

## Local historical-data acceptance

When the public provider is unreachable, save a per-symbol bundle and replay it through the same decision path:

```
acceptance-data/
  002475/
    1m.csv
    5m.csv
    15m.csv
    daily_stock.csv
    daily_csi300.csv
```

Intraday CSVs require `time,open,high,low,close,volume`; daily files require `date,close`. Timestamps must be unique and already sorted, and OHLC values must be internally valid. Parquet files with the same stems are also accepted when a parquet engine is installed. Do not mix CSV and Parquet for the same stem.

```bash
python -m backtest.decision_replay --input-dir ./acceptance-data --output decision-replay-report.json --max-samples 120
```

Local files default to `SYNTHETIC_FIXTURE`, so synthetic tests cannot pass real-data acceptance. For an independently sourced real-history bundle, explicitly attest its origin with `--input-origin REAL_HISTORICAL`. This is only a user-provided label; the tool records checksums and provenance fields but cannot authenticate where the data came from. Acceptance still requires at least three symbols with 30 or more decisions each, more than one observed regime, and zero schema, causality, and decision-trace failures. An incomplete result must not be treated as Phase 1 PASS.

See [SKILL.md](SKILL.md) and [config/strategy.yaml](config/strategy.yaml).
