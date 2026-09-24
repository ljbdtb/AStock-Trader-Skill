from .regime import classify
from .scoring import score
from .risk import gate_decision,structural_stop
from .structure import structure_snapshot
from .trading_rules import t_signal

def decide(df,portfolio_weight=None,mtf_alignment=0.5,relative_strength=0.5,
           position=None,data_ok=False):
    row=df.iloc[-1]; f=structure_snapshot(df)
    regime=classify(df,snapshot=f)
    points=score(df,mtf_alignment,relative_strength,snapshot=f)
    if f["bias"]=="BULLISH": points=min(100,points+5)
    elif f["bias"]=="BEARISH": points=max(0,points-5)
    if regime in {"BREAKOUT","STRONG_UPTREND"} and points>=70: action="HOLD"
    elif regime in {"DOWNTREND","FALSE_BREAKOUT"} and points<45: action="REDUCE"
    else: action="WAIT"
    sellable=position.sellable_shares if position is not None else 0
    t_action=t_signal(regime,row,position)
    action,t_action=gate_decision(action,t_action,position,data_ok)
    support=f["support"] if f["support"] is not None else float(row.low)
    resistance=f["resistance"] if f["resistance"] is not None else float(row.high)
    return {"price":round(float(row.close),3),"regime":regime,"score":points,"action":action,
      "t_action":t_action,"structure":f'{f["high_state"]}/{f["low_state"]}',
      "structure_bias":f["bias"],"support":round(float(support),3),
      "resistance":round(float(resistance),3),
      "resistance_source":f["resistance_source"],
      "support_source":f["support_source"],
      "breakout_status":f["breakout_status"],
      "breakout_level":f["breakout_level"],
      "atr_stop":round(structural_stop(row),3),
      "volume_ratio":round(f["volume_ratio"],2),"sellable_shares":sellable,
      "sellable_t_shares":position.sellable_t_shares if position is not None else 0,
      "buyback_remaining":position.buyback_remaining if position is not None else 0,
      "data_quality":"PASS" if data_ok else "FAIL"}
