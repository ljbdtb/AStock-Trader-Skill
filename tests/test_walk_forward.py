import pandas as pd
from backtest.walk_forward import evaluate,expanding_windows

def test_position_is_shifted_to_prevent_same_bar_lookahead():
    # The only gain occurs on bar 1. A signal first becoming active on bar 1
    # must NOT receive bar 1's already-realized return; it may act from bar 2.
    close=pd.Series([100.,110.,110.])
    pos=pd.Series([0.,1.,0.])
    m=evaluate(close,pos,cost_bps=0)
    assert abs(m.total_return)<1e-12

def test_next_bar_return_is_allowed():
    # Signal on bar 1 is shifted to bar 2, so bar 2's forward return is earned.
    close=pd.Series([100.,100.,110.])
    pos=pd.Series([0.,1.,0.])
    m=evaluate(close,pos,cost_bps=0)
    assert abs(m.total_return-0.10)<1e-12

def test_embargo_gap():
    tr,te=next(expanding_windows(300,train=120,test=40,embargo=5))
    assert tr.stop==120
    assert te.start==125
    assert te.start-tr.stop==5
