"""Small, dependency-light walk-forward validation helpers."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass
class Metrics:
    total_return:float
    sharpe:float
    max_drawdown:float
    trades:int

def evaluate(close:pd.Series,position:pd.Series,cost_bps=10.0):
    # Shift position: today's signal can only earn from the next bar onward.
    pos=position.fillna(0).clip(0,1).shift(1).fillna(0)
    ret=close.pct_change().fillna(0)
    turnover=pos.diff().abs().fillna(pos.abs())
    net=pos*ret-turnover*(cost_bps/10000.0)
    equity=(1+net).cumprod()
    dd=equity/equity.cummax()-1
    sd=float(net.std())
    sharpe=float(np.sqrt(252)*net.mean()/sd) if sd>0 else 0.0
    return Metrics(float(equity.iloc[-1]-1),sharpe,float(dd.min()),int((turnover>0).sum()))

def expanding_windows(n,train=120,test=40,embargo=5):
    start=train
    while start+embargo+test<=n:
        yield slice(0,start),slice(start+embargo,start+embargo+test)
        start+=test

def walk_forward(df,signal_fn,param_grid,train=120,test=40,embargo=5,cost_bps=10.0):
    rows=[]
    for fold,(tr,te) in enumerate(expanding_windows(len(df),train,test,embargo),1):
        best=None
        for params in param_grid:
            p=signal_fn(df.iloc[tr],**params)
            m=evaluate(df.close.iloc[tr],p,cost_bps)
            if best is None or m.sharpe>best[0]: best=(m.sharpe,params)
        params=best[1]
        # Give indicators warm-up history, score returns only on the OOS slice.
        end=te.stop; warm=max(0,te.start-train)
        chunk=df.iloc[warm:end].copy()
        p=signal_fn(chunk,**params)
        offset=te.start-warm
        m=evaluate(chunk.close.iloc[offset:],p.iloc[offset:],cost_bps)
        rows.append({"fold":fold,**params,"oos_return":m.total_return,
                     "oos_sharpe":m.sharpe,"oos_max_drawdown":m.max_drawdown,"trades":m.trades})
    return pd.DataFrame(rows)
