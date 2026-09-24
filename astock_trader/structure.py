from dataclasses import dataclass


@dataclass(frozen=True)
class Pivot:
    type: str
    price: float
    event_index: int
    confirmed_index: int
    event_time: object = None
    confirmed_at: object = None


def _as_of_end(df, as_of):
    if as_of is None:
        return len(df)
    if not isinstance(as_of, int) or not 0 <= as_of < len(df):
        raise ValueError("as_of must be a valid positional bar index")
    return as_of + 1


def confirmed_pivots(df, as_of=None, left=2, right=2, lookback=None):
    """Return pivots only once their right-hand confirmation bar is visible."""
    end = _as_of_end(df, as_of)
    start = max(0, end - lookback) if lookback is not None else 0
    visible = df.iloc[start:end]
    pivots = []
    for local_index in range(left, len(visible) - right):
        event_index = start + local_index
        confirmed_index = event_index + right
        window = visible.iloc[local_index-left:local_index+right+1]
        event_time = df.time.iloc[event_index] if "time" in df else None
        confirmed_at = df.time.iloc[confirmed_index] if "time" in df else None
        high = float(df.high.iloc[event_index])
        low = float(df.low.iloc[event_index])
        if high >= float(window.high.max()):
            pivots.append(Pivot("HIGH", high, event_index, confirmed_index,
                                event_time, confirmed_at))
        if low <= float(window.low.min()):
            pivots.append(Pivot("LOW", low, event_index, confirmed_index,
                                event_time, confirmed_at))
    return pivots

def market_structure(df,lookback=60,as_of=None):
    pivots=confirmed_pivots(df,as_of=as_of,lookback=lookback)
    highs=[p for p in pivots if p.type=="HIGH"]
    lows=[p for p in pivots if p.type=="LOW"]
    high_state=low_state="NA"
    if len(highs)>=2: high_state="HH" if highs[-1].price>highs[-2].price else "LH"
    if len(lows)>=2: low_state="HL" if lows[-1].price>lows[-2].price else "LL"
    if high_state=="HH" and low_state=="HL": bias="BULLISH"
    elif high_state=="LH" and low_state=="LL": bias="BEARISH"
    else: bias="MIXED"
    return {"high_state":high_state,"low_state":low_state,"bias":bias,
            "swing_high":highs[-1].price if highs else None,
            "swing_low":lows[-1].price if lows else None}

def structure_features(df,lookback=20,as_of=None):
    visible=df.iloc[:_as_of_end(df,as_of)]
    r=visible.tail(min(lookback+2,len(visible))).copy(); prev=r.iloc[:-1]; row=r.iloc[-1]
    prev_high=float(prev.high.max()) if len(prev) else float(row.high)
    prev_low=float(prev.low.min()) if len(prev) else float(row.low)
    reference_index=(len(visible)-len(r)+int(prev.high.to_numpy().argmax())
                     if len(prev) else None)
    vol_ma=float(visible.volume.rolling(20,min_periods=5).mean().iloc[-1])
    vol_ratio=float(row.volume/vol_ma) if vol_ma else 1.0
    s=market_structure(visible)
    return {"prev_high":prev_high,"prev_low":prev_low,
      "breakout":float(row.close)>prev_high,"breakdown":float(row.close)<prev_low,
      "breakout_reference_index":reference_index,
      "breakout_reference_available_index":reference_index,
      "volume_ratio":vol_ratio,**s}


def historical_structure_features(df,lookback=20):
    """Slow, causal reference implementation for historical feature generation."""
    return [structure_features(df.iloc[:t+1],lookback=lookback)
            for t in range(len(df))]

def detect_false_breakout(df,lookback=20):
    if len(df)<lookback+2:return False
    prior=df.iloc[-lookback-1:-1]; level=float(prior.high.max()); last=df.iloc[-1]
    recent=df.iloc[-3:]; pierced=float(recent.high.max())>level
    rejection=float(last.close)<level and float(last.close)<float(last.vwap)
    return pierced and rejection
