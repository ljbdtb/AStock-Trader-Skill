from .structure import structure_snapshot

def score(df, mtf_alignment=0.5, relative_strength=0.5, snapshot=None):
    r=df.iloc[-1]; f=snapshot if snapshot is not None else structure_snapshot(df); s=50
    s += 8 if r.close>r.ema20 else -8
    s += 6 if r.ema5>r.ema10>r.ema20 else -4
    s += 6 if r.macd_dif>r.macd_dea else -6
    s += 5 if r.close>r.vwap else -5
    s += 5 if f["volume_ratio"]>=f["breakout_volume_ratio_threshold"] and f["breakout"] else 0
    s += 5 if 50<=r.rsi12<=75 else (-4 if r.rsi12<40 else 0)
    s += 4 if r.adx14>=20 else 0
    s += round((mtf_alignment-.5)*12)
    s += round((relative_strength-.5)*10)
    return max(0,min(100,int(round(s))))
