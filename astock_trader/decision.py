from .regime import classify
from .scoring import score
from .risk import apply_risk_gate,structural_stop
from .structure import structure_features
from .trading_rules import t_signal

def decide(df,portfolio_weight=None,mtf_alignment=0.5,relative_strength=0.5,
           total_shares=0,today_bought=0,t_shares=0):
    row=df.iloc[-1]; regime=classify(df); f=structure_features(df)
    points=score(df,mtf_alignment,relative_strength)
    if f["bias"]=="BULLISH": points=min(100,points+5)
    elif f["bias"]=="BEARISH": points=max(0,points-5)
    if regime in {"BREAKOUT","STRONG_UPTREND"} and points>=70: action="HOLD"
    elif regime in {"DOWNTREND","FALSE_BREAKOUT"} and points<45: action="REDUCE"
    else: action="WAIT"
    sellable=max(0,int(total_shares)-int(today_bought))
    t_action=t_signal(regime,row,has_t_inventory=(t_shares>0 and sellable>0))
    action=apply_risk_gate(action,portfolio_weight)
    support=f["swing_low"] if f["swing_low"] is not None else float(df.tail(20).low.min())
    resistance=f["swing_high"] if f["swing_high"] is not None else float(df.tail(20).high.max())
    return {"price":round(float(row.close),3),"regime":regime,"score":points,"action":action,
      "t_action":t_action,"structure":f'{f["high_state"]}/{f["low_state"]}',
      "structure_bias":f["bias"],"support":round(float(support),3),
      "resistance":round(float(resistance),3),"atr_stop":round(structural_stop(row),3),
      "volume_ratio":round(f["volume_ratio"],2),"sellable_shares":sellable}
