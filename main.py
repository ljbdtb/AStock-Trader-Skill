import argparse,json
from astock_trader.data import fetch_frames
from astock_trader.indicators import add_indicators
from astock_trader.multitimeframe import timeframe_snapshot,alignment
from astock_trader.decision import decide
from astock_trader.card import render_card

def main():
    p=argparse.ArgumentParser(); p.add_argument("symbol")
    p.add_argument("--cost",type=float); p.add_argument("--shares",type=int)
    p.add_argument("--portfolio-weight",type=float); p.add_argument("--json",action="store_true")
    a=p.parse_args()
    frames,metas=fetch_frames(a.symbol)
    ready={k:add_indicators(v) for k,v in frames.items() if len(v)>=25}
    if not ready: raise RuntimeError("No usable market data")
    base=ready.get("5") or next(iter(ready.values()))
    snaps={k:timeframe_snapshot(v) for k,v in frames.items() if len(v)>=25}
    out=decide(base,a.portfolio_weight,alignment(snaps))
    meta=metas.get("5") or next(iter(metas.values()))
    out.update({"symbol":a.symbol,"cost":a.cost,"shares":a.shares,
      "data_time":meta.get("data_time"),"provider":meta.get("provider"),"timeframes":list(ready)})
    print(json.dumps(out,ensure_ascii=False,indent=2) if a.json else render_card(out))
if __name__=="__main__": main()
