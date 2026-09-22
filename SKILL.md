---
name: astock-trader
description: Analyze A-share short-term price action using live/minute data, technical indicators, market regime, multi-factor scoring, position context and risk rules. Produce a compact decision card.
---

# AStock Trader Skill

## Goal
Given an A-share symbol and optional position context, fetch the freshest available data, compute indicators, classify the market regime, score the setup, apply risk constraints, and return a concise decision-support card.

## Required workflow
1. Validate symbol and data timestamp.
2. Fetch market data. Prefer AKShare; allow provider fallback.
3. Never present stale/delayed data as exchange-level real-time data.
4. Compute indicators from raw OHLCV; do not infer indicators from prose.
5. Classify regime before interpreting overbought/oversold indicators.
6. Compute the multi-factor score.
7. Apply position/risk gates. Risk rules override technical signals.
8. Emit one of: HOLD, WAIT, BUY_T, SELL_T, REDUCE.
9. Always include invalidation conditions.
10. If no meaningful state change occurred, say the previous decision remains valid rather than inventing a new trade.

## Regimes
STRONG_UPTREND, UPTREND, RANGE, BREAKOUT, FALSE_BREAKOUT, REVERSAL, DOWNTREND.

## Default factor weights
- price_structure: 25
- trend: 15
- volume_price: 15
- vwap: 10
- momentum: 10
- volatility: 5
- relative_strength: 10
- multi_timeframe: 10

## Risk rules
- Never convert a high technical score into an automatic add-position instruction.
- When portfolio concentration exceeds configured threshold, disable ADD_POSITION; only HOLD/WAIT/T/REDUCE are allowed.
- Separate core position from T-position.
- Structural invalidation and ATR-based stops have priority over oscillator signals.
- RSI overbought alone is not a sell signal in an uptrend.
- Main-fund-flow style vendor metrics are secondary evidence, never proof of institutional intent.

## Compact output
Default response should be compact:

```text
SYMBOL | PRICE | DATA_TIME
REGIME: ...
SCORE: ../100
ACTION: ...
RESISTANCE: ...
SUPPORT: ...
T: ...
INVALIDATION: ...
DATA: provider / delay-quality
```

Only provide a long explanation when explicitly requested.
