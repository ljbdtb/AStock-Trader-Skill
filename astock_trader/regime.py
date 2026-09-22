from .structure import structure_features, detect_false_breakout

def classify(df):
    row=df.iloc[-1]; f=structure_features(df)
    if detect_false_breakout(df): return "FALSE_BREAKOUT"
    if f["breakout"] and f["volume_ratio"]>=1.2: return "BREAKOUT"
    bullish=row.close>row.ema20 and row.ema5>row.ema10>row.ema20
    bearish=row.close<row.ema20 and row.ema5<row.ema10<row.ema20
    if bullish and row.rsi12>=60 and row.adx14>=20: return "STRONG_UPTREND"
    if bullish: return "UPTREND"
    if bearish: return "DOWNTREND"
    return "RANGE"
