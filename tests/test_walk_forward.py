import pandas as pd
from backtest.walk_forward import evaluate,expanding_windows

def test_position_is_shifted_to_prevent_lookahead():
    close=pd.Series([100.,110.,110.])
    pos=pd.Series([1.,0.,0.])
    m=evaluate(close,pos,cost_bps=0)
    assert m.total_return==0

def test_embargo_gap():
    tr,te=next(expanding_windows(300,train=120,test=40,embargo=5))
    assert tr.stop==120
    assert te.start==125
