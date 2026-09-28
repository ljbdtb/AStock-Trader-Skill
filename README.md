# AStock-Trader-Skill

AStock-Trader-Skill is an A-share short-term/swing **decision-support engine, not an automated trading system**. It fetches market data, checks freshness, analyzes indicators, structure and regime, applies user-provided position and T+1 constraints, then displays recommendations. A person remains responsible for every trading decision and any execution.

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

See [SKILL.md](SKILL.md) and [config/strategy.yaml](config/strategy.yaml).
