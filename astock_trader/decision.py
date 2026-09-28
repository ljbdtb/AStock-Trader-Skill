from .regime import classify
from .scoring import score
from .risk import gate_decision,structural_invalidation
from .structure import structure_snapshot
from .trading_rules import t_signal

def decide(df,portfolio_weight=None,mtf_alignment=0.5,relative_strength=0.5,
           position=None,data_ok=False,previous_risk=None):
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
    invalidation=structural_invalidation(
        f,close=float(row.close),low=float(row.low),atr=row.get("atr14"),
        data_ok=data_ok,previous=previous_risk)
    action,t_action=gate_decision(
        action,t_action,position,data_ok,invalidation=invalidation)
    max_reducible_qty=(position.sellable_core_shares
                       if action=="REDUCE" and position is not None else 0)
    max_sell_t_qty=(position.sellable_t_shares
                    if t_action=="SELL_T" and position is not None else 0)
    max_buyback_t_qty=(position.buyback_remaining
                       if t_action=="BUYBACK_T" and position is not None else 0)
    if not data_ok:
        decision_status="WAIT_DATA"
    elif invalidation.active and max_reducible_qty==0:
        decision_status="REDUCE_BLOCKED_T1"
    else:
        decision_status=action
    risk_codes=list(invalidation.reason_codes)
    if invalidation.active and data_ok and position is not None:
        if position.sellable_core_shares==0:
            risk_codes.append("REDUCE_BLOCKED_BY_T1")
        elif position.bought_core_today>0:
            risk_codes.append("REDUCE_LIMITED_BY_T1")
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
      "structural_reference_level":invalidation.reference_level,
      "structural_reference_type":invalidation.reference_type,
      "structural_invalidation_level":invalidation.invalidation_level,
      "structural_invalidation_confirmed":invalidation.confirmed,
      "structural_invalidation_reason_codes":invalidation.reason_codes,
      "risk_active":invalidation.active,"risk_status":invalidation.status,
      "risk_reason_codes":risk_codes,"decision_status":decision_status,
      "max_reducible_qty":max_reducible_qty,
      "max_sell_t_qty":max_sell_t_qty,
      "max_buyback_t_qty":max_buyback_t_qty,
      "volume_ratio":round(f["volume_ratio"],2),"sellable_shares":sellable,
      "sellable_t_shares":position.sellable_t_shares if position is not None else 0,
      "buyback_remaining":position.buyback_remaining if position is not None else 0,
      "data_quality":"PASS" if data_ok else "FAIL"}
