from .indicators import add_indicators

def timeframe_snapshot(df):
    d=add_indicators(df)
    r=d.iloc[-1]
    return {
        "close":float(r.close),
        "ema20":float(r.ema20),
        "macd_positive":bool(r.macd_dif>r.macd_dea),
        "rsi12":float(r.rsi12),
        "above_vwap":bool(r.close>r.vwap),
    }

def alignment(frames):
    if not frames: return 0.5
    votes=[]
    for x in frames.values():
        votes.append(x["close"]>x["ema20"] and x["macd_positive"])
    return sum(votes)/len(votes)
