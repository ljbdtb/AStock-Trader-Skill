from .regime import classify
from .scoring import score
from .risk import apply_risk_gate, structural_stop
from .structure import structure_features

def decide(df,portfolio_weight=None,mtf_alignment=0.5,relative_strength=0.5):
    row=df.iloc[-1]; regime=classify(df); points=score(df,mtf_alignment,relative_strength)
    f=structure_features(df)
    if regime in {"BREAKOUT","STRONG_UPTREND"} and points>=70: action="HOLD"
    elif regime in {"DOWNTREND","FALSE_BREAKOUT"} and points<45: action="REDUCE"
    else: action="WAIT"
    t_action="WAIT"
    if regime=="FALSE_BREAKOUT": t_action="SELL_T"
    elif regime in {"UPTREND","STRONG_UPTREND"} and row.close<=row.vwap*1.003 and row.rsi12<65: t_action="BUY_T"
    action=apply_risk_gate(action,portfolio_weight)
    recent=df.tail(min(20,len(df)))
    return {"price":round(float(row.close),3),"regime":regime,"score":points,"action":action,
      "t_action":t_action,"support":round(float(recent.low.min()),3),
      "resistance":round(float(max(f["prev_high"],row.high)),3),
      "atr_stop":round(structural_stop(row),3),"volume_ratio":round(f["volume_ratio"],2)}
