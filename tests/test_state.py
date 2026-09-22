from astock_trader.state import AnalysisState, materially_changed

def test_unchanged_state():
    p=AnalysisState("002475","UPTREND","HOLD","WAIT",70)
    c={"regime":"UPTREND","action":"HOLD","t_action":"WAIT","score":72}
    assert materially_changed(p,c) is False

def test_regime_change():
    p=AnalysisState("002475","UPTREND","HOLD","WAIT",70)
    c={"regime":"FALSE_BREAKOUT","action":"REDUCE","t_action":"SELL_T","score":50}
    assert materially_changed(p,c) is True
