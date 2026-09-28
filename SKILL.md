---
name: astock-trader
description: Use when a user asks for A-share short-term or swing position analysis, such as whether to hold or reduce 002475, how to manage a T-position, or whether an existing position is sellable today.
---

# AStock Trader decision support

This skill gives **recommendations, not orders**. It never connects to a broker, places or cancels orders, confirms fills, or changes a real account. The human decides whether and how to act.

For a stock request, use this repository's `main.py` with the symbol and, when available, a complete user-provided position snapshot: trading date, core/T shares, same-day core/T buys, same-day T sales and buybacks; cost and portfolio weight are useful context. Do not infer holdings or today's transactions. For an account-specific question such as "can I sell now?", partial details (for example, only today's buys and T sales) do not establish sellable inventory: return `WAIT` on that question and do not give a quantity bound. Symbol-only market analysis may be described separately, clearly labeled as not position-specific. Read the JSON result so data quality, structure, risk reasons, and legal quantity upper bounds remain visible. If the data is stale, do not turn a `WAIT` into a buy or sell suggestion.

Interpret `HOLD`, `WAIT`, `SELL_T`, `BUYBACK_T`, and `REDUCE` as decision recommendations. `max_reducible_qty`, `max_sell_t_qty`, and `max_buyback_t_qty` are legal upper bounds under the provided state, **not recommended exact trade sizes**. A structural invalidation may override a high evidence score, but `REDUCE` means consider lowering core-position risk, not liquidate or sell all.

The analysis uses data quality, indicators, one causal Structure snapshot, regime, multi-timeframe evidence, completed-session CSI300 relative strength, a fixed 100-point score, T+1 position constraints and the recommendation safety gate. Relative strength is based on qfq-adjusted stock prices versus a price index without dividends; check its as-of date and report unavailable evidence explicitly. State the data timestamp, action, relevant support/resistance and invalidation level, risk reason, and any applicable upper bound. If no safe action is supported, say `WAIT` rather than inventing a trade. See `README.md` for local usage and product non-goals.
