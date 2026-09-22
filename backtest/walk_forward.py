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

def evaluate(close:pd.Series,position:pd.Series,cost_bps=10.0,buy_cost_bps=None,sell_cost_bps=None):
    """Evaluate next-bar execution with explicit directional costs.

    cost_bps remains backward compatible. If directional costs are supplied,
    entries pay buy_cost_bps and exits pay sell_cost_bps.
    """
    pos=position.fillna(0).clip(0,1).shift(1).fillna(0)
    ret=close.pct_change().fillna(0)
    delta=pos.diff().fillna(pos)
    buys=delta.clip(lower=0)
    sells=(-delta.clip(upper=0))
    if buy_cost_bps is None: buy_cost_bps=cost_bps
    if sell_cost_bps is None: sell_cost_bps=cost_bps
    costs=buys*(buy_cost_bps/10000.0)+sells*(sell_cost_bps/10000.0)
    net=pos*ret-costs
    equity=(1+net).cumprod()
    dd=equity/equity.cummax()-1
    sd=float(net.std())
    sharpe=float(np.sqrt(252)*net.mean()/sd) if sd>0 else 0.0
    trades=int(((buys+sells)>0).sum())
    return Metrics(float(equity.iloc[-1]-1),sharpe,float(dd.min()),trades)

def expanding_windows(n,train=120,test=40,embargo=5):
    start=train
    while start+embargo+test<=n:
        yield slice(0,start),slice(start+embargo,start+embargo+test)
        start+=test

def walk_forward(df,signal_fn,param_grid,train=120,test=40,embargo=5,cost_bps=10.0,
                 buy_cost_bps=None,sell_cost_bps=None):
    rows=[]
    for fold,(tr,te) in enumerate(expanding_windows(len(df),train,test,embargo),1):
        best=None
        for params in param_grid:
            p=signal_fn(df.iloc[tr],**params)
            m=evaluate(df.close.iloc[tr],p,cost_bps,buy_cost_bps,sell_cost_bps)
            if best is None or m.sharpe>best[0]: best=(m.sharpe,params)
        params=best[1]
        end=te.stop; warm=max(0,te.start-train)
        chunk=df.iloc[warm:end].copy()
        p=signal_fn(chunk,**params)
        # Preserve the bar immediately before OOS so shift(1) is correct at the boundary.
        start=max(0,te.start-warm-1)
        sub_close=chunk.close.iloc[start:]
        sub_pos=p.iloc[start:]
        m=evaluate(sub_close,sub_pos,cost_bps,buy_cost_bps,sell_cost_bps)
        rows.append({"fold":fold,**params,"oos_return":m.total_return,
                     "oos_sharpe":m.sharpe,"oos_max_drawdown":m.max_drawdown,"trades":m.trades})
    return pd.DataFrame(rows)
