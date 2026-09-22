import pandas as pd
from astock_trader.structure import market_structure

def test_structure_returns_states():
    x=[10,11,10.4,12,11,13,12,14,13,15]
    df=pd.DataFrame({"high":[v+.2 for v in x],"low":[v-.2 for v in x]})
    r=market_structure(df,lookback=60)
    assert r["bias"] in {"BULLISH","BEARISH","MIXED"}
