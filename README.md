# AStock-Trader-Skill

A rule-based A-share short-term decision-support skill.

## v0.2
- AKShare/Eastmoney 1m/5m/15m data
- EMA, MACD, RSI, ATR, ADX, Bollinger, OBV, VWAP
- multi-timeframe alignment
- breakout / false-breakout detection with volume confirmation
- market-regime state machine
- 0-100 factor score
- core/T-position aware signals
- concentration risk gate
- compact trading card
- Backtrader starter strategy + tests

> Signals are decision support, not guaranteed forecasts. Data providers can be delayed or unavailable.

## Run
```bash
pip install -r requirements.txt
python main.py 002475 --cost 56 --shares 2200 --portfolio-weight 0.95
python main.py 002475 --json
```

Default output is intentionally short: state, score, action, T-action, support/resistance and invalidation reference.

See `SKILL.md` and `config/strategy.yaml`.
