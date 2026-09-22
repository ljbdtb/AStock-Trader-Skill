def structure_features(df, lookback=20):
    r=df.tail(min(lookback+2,len(df))).copy()
    prev=r.iloc[:-1]
    row=r.iloc[-1]
    prev_high=float(prev.high.max()) if len(prev) else float(row.high)
    prev_low=float(prev.low.min()) if len(prev) else float(row.low)
    breakout=float(row.close)>prev_high
    breakdown=float(row.close)<prev_low
    vol_ma=float(df.volume.rolling(20,min_periods=5).mean().iloc[-1])
    vol_ratio=float(row.volume/vol_ma) if vol_ma else 1.0
    return {"prev_high":prev_high,"prev_low":prev_low,"breakout":breakout,
            "breakdown":breakdown,"volume_ratio":vol_ratio}

def detect_false_breakout(df, lookback=20):
    if len(df)<lookback+2: return False
    prior=df.iloc[-lookback-1:-1]
    level=float(prior.high.max())
    last=df.iloc[-1]
    recent=df.iloc[-3:]
    pierced=float(recent.high.max())>level
    return pierced and float(last.close)<level and float(last.close)<float(last.vwap)
