# Research integration gap: decision engine vs. validated backtest

Date: 2026-09-23  
Branch: `research/002475-risk-sizing`  
Scope: stage D preparation only. The production decision engine is **not** claimed to be backtested or ready for automated trading.

## A/B/C validation snapshot

The current validated benchmark remains a daily EMA walk-forward, not the Regime/Structure/T/risk decision engine.

- Data audit for 002475 passed: 2,833 daily bars, 2015-01-05 through 2026-09-22, zero missing OHLCV, duplicate dates, invalid OHLC, or nonpositive volume. The completed A/B run reported Eastmoney as its actual source; the fallback path is explicit and was used on earlier transient failures.
- Parameter grid: target volatility 15/20/25%, lookback 15/20/30/40 sessions, exposure cap 100%. The predeclared local rule returned `STABLE` (9/9 local cells had positive mean OOS Sharpe; center Sharpe 0.4680 and local 25th percentile 0.4680). This is local consistency under that rule, not proof of economic edge.
- Base-cost EMA + 20% volatility target: mean OOS return 6.10%, Sharpe 0.4680, worst drawdown -15.24%, 9/19 profitable windows. The 2x cost scenario retained 5.67% mean return, Sharpe 0.4110, worst drawdown -15.63%; it is `PASS` under the frozen cost-sensitivity rule (2x return remains positive and above half of base).
- Trade-level evidence is weaker: at base cost, 54 completed exposure episodes had Profit Factor 0.853 and expectancy -0.00304 per episode; 10 fold-end episodes remained open and are excluded from closed-trade statistics. Thus the frozen cost rule passes, but the closed-trade statistics do not establish positive trade expectancy.
- The same EMA + risk protocol was tested on 002475, 002594, 300750, 601138, 300308, and 600519. All six data audits passed using Tencent back-adjusted (`hfq`) prices. The sample produced positive mean OOS return on 6/6 symbols and positive mean OOS Sharpe on 5/6; the median symbol mean Sharpe was 0.2398. The sample is a hand-selected set of currently surviving large-cap names, so it does not remove survivorship or selection bias.
- The multi-stock run uses `hfq`; the earlier 002475 baseline uses `qfq`. Do not compare their absolute reported returns as if the data convention were identical. AKShare documents that forward-adjusted prices can become negative and recommends back-adjusted prices for quantitative research ([AKShare stock data documentation](https://github.com/akfamily/akshare/blob/main/docs/data/stock/stock.md)).

Workflow evidence: [tests](https://github.com/ljbdtb/AStock-Trader-Skill/actions/runs/35846031076) · [full A/B/C backtest and artifact](https://github.com/ljbdtb/AStock-Trader-Skill/actions/runs/35846031103).

## Decision-engine gap inventory

| Area | Current evidence in code | Backtest blocker / required contract |
|---|---|---|
| Regime coverage | `astock_trader/regime.py::classify` emits BREAKOUT, FALSE_BREAKOUT, STRONG_UPTREND, UPTREND, DOWNTREND, RANGE. | The requested REVERSAL state is absent. Define mutually exclusive state precedence and transition rules before fitting any thresholds. |
| Structure timing | `structure.py::_pivots(left=2,right=2)` confirms pivots using two bars to the right. | A pivot at bar t is only knowable at t+2. A backtest must evaluate each decision on a prefix ending at that decision bar and must not make the pivot available earlier. Add perturb-future invariance tests. |
| Core action / concentration | `decision.py::decide` emits only HOLD, REDUCE, or WAIT. `risk.py::apply_risk_gate` only blocks BUY/ADD. | The concentration gate currently cannot block a core BUY/ADD because none is emitted, and it is not applied to `t_action`; a concentrated portfolio may still receive BUY_T. Define risk precedence for all net-increasing intents, including T buys. |
| T+1 and inventory | `trading_rules.py::same_day_sellable` computes a scalar sellable share count; `t_signal` emits a direction. `Position` stores total shares and T shares. | There is no fill/lot ledger, core-vs-T allocation transition, cash/quantity sizing, partial-fill handling, or daily inventory simulator. Directional signals alone cannot validate legal T+1 execution or round-trip P&L. |
| Data readiness | `data.py` records provider success/failure and quote fetch time; `fetch_frames` can return per-period errors. | The decision path has no hard freshness/partial-bar/duplicate/order gate. On missing or stale inputs it must fail closed (WAIT / DATA_INVALID) instead of producing a normal action from incomplete frames. |
| Multi-timeframe / relative strength | `decision.py::decide` and `scoring.py::score` default MTF alignment and relative strength to 0.5. `multitimeframe.py` has snapshot helpers but no synchronized historical as-of join in the backtest. | The current score can silently use neutral placeholders. Build point-in-time aligned MTF/index/sector context or mark the score incomplete and suppress decision-grade output. |
| VWAP semantics | `indicators.py::add_indicators` computes cumulative VWAP across the supplied frame. | This is session VWAP only when input is a single session of intraday bars. For multi-session/daily history it is cumulative across sessions and unsuitable as a daily rolling/session reference. Define timeframe-specific VWAP and test day-boundary reset. |
| Risk execution | `risk.py::structural_stop` returns close minus 1.5 ATR; `decide` reports it. | No stop-trigger/fill simulation, gap/slippage treatment, lot rounding, exposure path, or portfolio-level risk accounting exists. A printed stop is not evidence that the risk control was executable. |
| Historical validation | `backtest/run_002475.py` and `run_multi_asset.py` use EMA signals plus volatility sizing. | Neither runs the Regime/Structure/Score/T+1/portfolio-risk decision path. Current A/B/C evidence must not be presented as a backtest of the final Skill. |

## Required integration contract before engine OOS

1. **Point-in-time input:** expose a decision function over an as-of prefix `df[:t]`; all daily/intraday/index/sector frames must be aligned to information actually available at t. Enforce the shared rule: signal at close t, one execution shift in the evaluator, and no internal second shift.
2. **Fail-closed data gate:** require fresh timestamps, complete bars, unique increasing timestamps, valid OHLCV, and all required timeframes/context. Missing context must be explicit; do not substitute neutral values in a decision-grade run.
3. **Explicit state and intent:** specify allowed Regime transitions, core and T inventories, buy/sell quantities, and which intents change net exposure. Apply concentration and stop/risk constraints before every net-increasing action, including BUY_T.
4. **Event-driven A-share execution:** simulate T+1 sellable inventory, lot size, cash, fees, sell-side stamp tax, slippage, next-bar fills, gaps, partial fills, and unfilled orders. Separate open inventory at fold end from completed trades.
5. **Pre-result tests:** future-perturbation invariance; two-bar pivot confirmation; no same-day sale of new buys; no T buy above concentration limit; core inventory untouched by T transitions; one-bar execution delay; stale/partial data fail-closed; day-reset VWAP; and cost directionality.
6. **Frozen validation:** freeze strategy state rules and gates before the next OOS run. Use the same walk-forward dates, embargo, costs, and asset list; report every symbol/window, completed and open inventory episodes, turnover, PF/expectancy, exposure, drawdown, and benchmark. Do not select rules based on OOS results.

## Stage-D status

- EMA + volatility risk-sizing research: `CANDIDATE`, not a demonstrated robust edge.
- 200-day trend filter: `REJECT` versus baseline Sharpe.
- Final Regime/Structure/T+1/Risk decision engine: `NOT READY FOR OOS` until the integration contract and tests above are implemented.
- Live automated order decisions: `NOT READY`. Use remains analysis / paper-tracking only.
- No changes have been merged to `main`.
