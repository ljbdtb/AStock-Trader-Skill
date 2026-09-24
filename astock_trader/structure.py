from dataclasses import dataclass
from .strategy_config import strategy_config


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

def market_structure(df,lookback=None,as_of=None,tolerance_ratio=None):
    if lookback is None:
        lookback=strategy_config()["structure"]["pivot_lookback"]
    pivots=confirmed_pivots(df,as_of=as_of,lookback=lookback)
    highs=[p for p in pivots if p.type=="HIGH"]
    lows=[p for p in pivots if p.type=="LOW"]
    if tolerance_ratio is None:
        tolerance_ratio=strategy_config()["structure"]["equal_level_tolerance_ratio"]
    high_state=low_state="NA"
    if len(highs)>=2:
        delta=highs[-1].price-highs[-2].price
        tolerance=max(abs(highs[-1].price),abs(highs[-2].price))*tolerance_ratio
        high_state="EH" if abs(delta)<=tolerance else ("HH" if delta>0 else "LH")
    if len(lows)>=2:
        delta=lows[-1].price-lows[-2].price
        tolerance=max(abs(lows[-1].price),abs(lows[-2].price))*tolerance_ratio
        low_state="EL" if abs(delta)<=tolerance else ("HL" if delta>0 else "LL")
    if high_state=="HH" and low_state=="HL": bias="BULLISH"
    elif high_state=="LH" and low_state=="LL": bias="BEARISH"
    else: bias="MIXED"
    return {"high_state":high_state,"low_state":low_state,"bias":bias,
            "swing_high":highs[-1].price if highs else None,
            "swing_low":lows[-1].price if lows else None}

def _base_structure_features(df,lookback,volume_lookback,volume_min_periods):
    visible=df
    r=visible.tail(min(lookback+2,len(visible))).copy(); prev=r.iloc[:-1]; row=r.iloc[-1]
    prev_high=float(prev.high.max()) if len(prev) else float(row.high)
    prev_low=float(prev.low.min()) if len(prev) else float(row.low)
    vol_ma=float(visible.volume.rolling(
        volume_lookback,min_periods=volume_min_periods).mean().iloc[-1])
    vol_ratio=float(row.volume/vol_ma) if vol_ma else 1.0
    s=market_structure(visible)
    return {"prev_high":prev_high,"prev_low":prev_low,
      "breakdown":float(row.close)<prev_low,"volume_ratio":vol_ratio,**s}


def historical_structure_features(df,lookback=None):
    """Slow, causal reference implementation for historical feature generation."""
    return [structure_features(df.iloc[:t+1],lookback=lookback)
            for t in range(len(df))]


def _known_resistance(df, before, lookback, pivot_lookback):
    if before <= 0:
        return None, "UNKNOWN", None, None
    highs=[p for p in confirmed_pivots(df,as_of=before-1,lookback=pivot_lookback)
           if p.type=="HIGH"]
    if highs:
        pivot=highs[-1]
        return pivot.price,"CONFIRMED_SWING",pivot.event_index,pivot.confirmed_index
    start=max(0,before-lookback)
    prior=df.high.iloc[start:before]
    event=start+int(prior.to_numpy().argmax())
    return float(prior.max()),"HISTORICAL_RANGE_FALLBACK",event,event


def _breakout_state(df,config,lookback):
    hold_bars=config["structure"]["breakout_hold_bars"]
    rejection_bars=config["structure"]["breakout_rejection_bars"]
    min_close_position=config["structure"]["breakout_close_position_min"]
    min_volume_ratio=config["signals"]["breakout_volume_ratio"]
    volume_lookback=config["structure"]["volume_ratio_lookback"]
    volume_min_periods=config["structure"]["volume_ratio_min_periods"]
    active=None
    result={"breakout_status":"KNOWN_LEVEL","breakout_level":None,
            "breakout_event_index":None,"breakout_event_time":None,
            "confirmation_index":None,"confirmation_time":None,
            "resistance_source":"UNKNOWN","reference_event_index":None,
            "reference_available_index":None}
    for t in range(1,len(df)):
        row=df.iloc[t]
        if active is not None and t-active["breakout_event_index"]>rejection_bars:
            active=None
        if active is not None:
            result=active.copy()
            if float(row.close)<=active["breakout_level"]:
                result["breakout_status"]="FALSE_BREAKOUT"
                active=None
                continue
            if (t-active["breakout_event_index"]+1>=hold_bars
                    and active["qualified"]):
                result["breakout_status"]="CONFIRMED_BREAKOUT"
                if result["confirmation_index"] is None:
                    result["confirmation_index"]=t
                    result["confirmation_time"]=df.time.iloc[t] if "time" in df else None
                active=result.copy()
            else:
                result["breakout_status"]="BREAKOUT_ATTEMPT"
            continue
        level,source,event,available=_known_resistance(
            df,t,lookback,config["structure"]["pivot_lookback"])
        result={"breakout_status":"KNOWN_LEVEL","breakout_level":level,
                "breakout_event_index":None,"breakout_event_time":None,
                "confirmation_index":None,"confirmation_time":None,
                "resistance_source":source,"reference_event_index":event,
                "reference_available_index":available}
        if level is None or float(row.high)<=level:
            continue
        result["breakout_event_index"]=t
        result["breakout_event_time"]=df.time.iloc[t] if "time" in df else None
        if float(row.close)<=level:
            result["breakout_status"]="FALSE_BREAKOUT"
            continue
        spread=float(row.high-row.low)
        close_position=(float(row.close-row.low)/spread) if spread>0 else 0
        volume_mean=(float(df.volume.iloc[:t+1].tail(volume_lookback).mean())
                     if t+1>=volume_min_periods else 0)
        volume_ratio=float(row.volume/volume_mean) if volume_mean>0 else 0
        result["qualified"]=(close_position>=min_close_position
                             and volume_ratio>=min_volume_ratio)
        result["breakout_status"]="BREAKOUT_ATTEMPT"
        active=result.copy()
    result.pop("qualified",None)
    return result


def structure_snapshot(df,as_of=None,lookback=None):
    visible=df.iloc[:_as_of_end(df,as_of)]
    config=strategy_config()
    if lookback is None:
        lookback=config["signals"]["breakout_lookback"]
    base=_base_structure_features(
        visible,lookback,config["structure"]["volume_ratio_lookback"],
        config["structure"]["volume_ratio_min_periods"])
    prior=market_structure(visible.iloc[:-1]) if len(visible)>1 else {
        "bias":"MIXED","swing_high":None,"swing_low":None}
    breakout=_breakout_state(visible,config,lookback)
    resistance=breakout["breakout_level"]
    lows=[p for p in confirmed_pivots(
        visible,lookback=config["structure"]["pivot_lookback"]) if p.type=="LOW"]
    if lows:
        support=lows[-1].price
        support_source="CONFIRMED_SWING"
    elif len(visible)>1:
        support=float(visible.low.iloc[:-1].tail(lookback).min())
        support_source="HISTORICAL_RANGE_FALLBACK"
    else:
        support=None
        support_source="UNKNOWN"
    return {**base,**breakout,
            "as_of":len(visible)-1,
            "structure_state":base["bias"],
            "confirmed_swing_high":base["swing_high"],
            "confirmed_swing_low":base["swing_low"],
            "prior_bias":prior["bias"],
            "prior_swing_high":prior["swing_high"],
            "prior_swing_low":prior["swing_low"],
            "resistance":resistance,"support":support,
            "support_source":support_source,
            "breakout_reference_index":breakout["reference_event_index"],
            "breakout_reference_available_index":breakout["reference_available_index"],
            "breakout_volume_ratio_threshold":config["signals"]["breakout_volume_ratio"],
            "prev_high":resistance if resistance is not None else base["prev_high"],
            "breakout":breakout["breakout_status"]=="CONFIRMED_BREAKOUT",
            "false_breakout":breakout["breakout_status"]=="FALSE_BREAKOUT",
            "compression":base["high_state"]=="EH" and base["low_state"]=="EL",
            "expansion":breakout["breakout_status"]=="CONFIRMED_BREAKOUT"}


def historical_structure_snapshots(df):
    return [structure_snapshot(df.iloc[:t+1]) for t in range(len(df))]


def structure_features(df,lookback=None,as_of=None):
    return structure_snapshot(df,as_of=as_of,lookback=lookback)

def detect_false_breakout(df,lookback=20):
    return structure_snapshot(df)["false_breakout"]
