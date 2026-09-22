import pandas as pd
from astock_trader.indicators import add_indicators
from astock_trader.decision import decide

def test_engine_runs():
    n=100
    df=pd.DataFrame({
        "open":[10+i*.01 for i in range(n)],
        "high":[10.1+i*.01 for i in range(n)],
        "low":[9.9+i*.01 for i in range(n)],
        "close":[10.05+i*.01 for i in range(n)],
        "volume":[1000+i for i in range(n)],
    })
    out=decide(add_indicators(df),0.95)
    assert 0 <= out["score"] <= 100
    assert out["action"] in {"HOLD","WAIT","BUY_T","SELL_T","REDUCE"}
