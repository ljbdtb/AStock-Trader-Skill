from .regime import classify
from .scoring import score
from .risk import apply_risk_gate, structural_stop

def decide(df, portfolio_weight=None):
    row=df.iloc[-1]
    regime=classify(row)
    points=score(row)
    if regime=="STRONG_UPTREND" and points>=70:
        action="HOLD"
    elif regime=="DOWNTREND" and points<40:
        action="REDUCE"
    else:
        action="WAIT"
    action=apply_risk_gate(action,portfolio_weight)
    recent=df.tail(min(20,len(df)))
    return {
        "price": round(float(row.close),3),
        "regime": regime,
        "score": points,
        "action": action,
        "support": round(float(recent.low.min()),3),
        "resistance": round(float(recent.high.max()),3),
        "atr_stop": round(structural_stop(row),3),
    }
