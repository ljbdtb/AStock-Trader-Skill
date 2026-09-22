def _pivots(df,left=2,right=2):
    highs=[]; lows=[]
    for i in range(left,len(df)-right):
        w=df.iloc[i-left:i+right+1]
        if float(df.high.iloc[i])>=float(w.high.max()): highs.append((i,float(df.high.iloc[i])))
        if float(df.low.iloc[i])<=float(w.low.min()): lows.append((i,float(df.low.iloc[i])))
    return highs,lows

def market_structure(df,lookback=60):
    d=df.tail(min(lookback,len(df))).reset_index(drop=True)
    highs,lows=_pivots(d)
    high_state=low_state="NA"
    if len(highs)>=2: high_state="HH" if highs[-1][1]>highs[-2][1] else "LH"
    if len(lows)>=2: low_state="HL" if lows[-1][1]>lows[-2][1] else "LL"
    if high_state=="HH" and low_state=="HL": bias="BULLISH"
    elif high_state=="LH" and low_state=="LL": bias="BEARISH"
    else: bias="MIXED"
    return {"high_state":high_state,"low_state":low_state,"bias":bias,
            "swing_high":highs[-1][1] if highs else None,
            "swing_low":lows[-1][1] if lows else None}

def structure_features(df,lookback=20):
    r=df.tail(min(lookback+2,len(df))).copy(); prev=r.iloc[:-1]; row=r.iloc[-1]
    prev_high=float(prev.high.max()) if len(prev) else float(row.high)
    prev_low=float(prev.low.min()) if len(prev) else float(row.low)
    vol_ma=float(df.volume.rolling(20,min_periods=5).mean().iloc[-1])
    vol_ratio=float(row.volume/vol_ma) if vol_ma else 1.0
    s=market_structure(df)
    return {"prev_high":prev_high,"prev_low":prev_low,
      "breakout":float(row.close)>prev_high,"breakdown":float(row.close)<prev_low,
      "volume_ratio":vol_ratio,**s}

def detect_false_breakout(df,lookback=20):
    if len(df)<lookback+2:return False
    prior=df.iloc[-lookback-1:-1]; level=float(prior.high.max()); last=df.iloc[-1]
    recent=df.iloc[-3:]; pierced=float(recent.high.max())>level
    rejection=float(last.close)<level and float(last.close)<float(last.vwap)
    return pierced and rejection
