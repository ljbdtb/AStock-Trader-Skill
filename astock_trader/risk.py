def apply_risk_gate(action, portfolio_weight=None, concentration_limit=0.50):
    if portfolio_weight is not None and portfolio_weight > concentration_limit:
        if action in {"BUY", "ADD"}:
            return "HOLD"
    return action

def structural_stop(row, atr_multiple=1.5):
    return float(row["close"] - atr_multiple*row["atr14"])
