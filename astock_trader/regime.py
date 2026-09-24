from .structure import structure_snapshot
from .strategy_config import strategy_config

def classify(df,snapshot=None):
    row=df.iloc[-1]; f=snapshot if snapshot is not None else structure_snapshot(df)
    config=strategy_config()["regime"]
    prior_close=float(df.close.iloc[-2]) if len(df)>1 else float(row.close)
    # Risk-relevant event states precede trend and range labels.
    if f["false_breakout"]: return "FALSE_BREAKOUT"
    if (f["prior_bias"]=="BEARISH" and f["prior_swing_high"] is not None
            and prior_close<=f["prior_swing_high"]<row.close): return "REVERSAL"
    if (f["prior_bias"]=="BULLISH" and f["prior_swing_low"] is not None
            and prior_close>=f["prior_swing_low"]>row.close): return "REVERSAL"
    if f["breakout_status"]=="CONFIRMED_BREAKOUT": return "BREAKOUT"
    if f["breakout_status"]=="BREAKOUT_ATTEMPT": return "BREAKOUT_ATTEMPT"
    if f["compression"]: return "RANGE"
    bullish=row.close>row.ema20 and row.ema5>row.ema10>row.ema20
    bearish=row.close<row.ema20 and row.ema5<row.ema10<row.ema20
    if bullish and row.rsi12>=60 and row.adx14>=config["strong_trend_adx_min"]: return "STRONG_UPTREND"
    if bullish: return "UPTREND"
    if bearish: return "DOWNTREND"
    slope=abs(float(row.ema5/row.ema20-1)) if row.ema20 else float("inf")
    in_range=(f["support"] is not None and f["resistance"] is not None
              and f["support"]<=row.close<=f["resistance"])
    if (row.adx14<config["range_adx_max"]
            and slope<=config["range_ema_slope_max_ratio"] and in_range):
        return "RANGE"
    return "UNKNOWN"
