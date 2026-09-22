# AStock-Trader-Skill

A rule-based A-share short-term trading analysis skill focused on **market regime, multi-factor scoring, T-trading state, and risk control**.

> This project produces decision-support signals, not guaranteed forecasts or investment advice.

## v0.1

- AKShare-first market data adapter (extensible to Tushare)
- EMA / MACD / RSI / ATR / ADX / Bollinger / OBV / VWAP indicators
- Market regime classifier
- 0-100 multi-factor score
- Position-aware decision engine
- Hard risk gate for concentrated positions
- Compact JSON / trading-card output
- Backtest-ready strategy core

## Quick start

```bash
pip install -r requirements.txt
python main.py 002475
```

Optional position context:

```bash
python main.py 002475 --cost 56 --shares 2200 --portfolio-weight 0.95
```

## Design principle

Indicators do not vote blindly. The engine first classifies market regime, then interprets momentum, trend, volume and volatility in context. Risk rules override signal scores.

See `SKILL.md` for agent behavior and `config/strategy.yaml` for tunable parameters.
