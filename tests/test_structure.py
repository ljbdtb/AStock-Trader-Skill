import pandas as pd
from astock_trader.indicators import add_indicators
from astock_trader.structure import structure_features

def test_breakout_detection():
    n=30
    close=[10+i*.01 for i in range(n)]
    df=pd.DataFrame({"open":close,"high":[x+.05 for x in close],
      "low":[x-.05 for x in close],"close":close,"volume":[1000]*n})
    df.loc[n-1,["close","high","volume"]]=[11,11.1,3000]
    f=structure_features(add_indicators(df))
    assert f["breakout"]
    assert f["volume_ratio"]>1
