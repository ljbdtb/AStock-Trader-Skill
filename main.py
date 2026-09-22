import argparse,json
from astock_trader.data import fetch_frames
from astock_trader.indicators import add_indicators
from astock_trader.multitimeframe import timeframe_snapshot,alignment
from astock_trader.decision import decide
from astock_trader.card import render_card
from astock_trader.state import AnalysisState,StateStore,materially_changed

def main():
    p=argparse.ArgumentParser(); p.add_argument("symbol")
    p.add_argument("--cost",type=float); p.add_argument("--shares",type=int)
    p.add_argument("--portfolio-weight",type=float); p.add_argument("--json",action="store_true")
    p.add_argument("--state-file",default=".astock_state.json")
    a=p.parse_args()
    frames,metas=fetch_frames(a.symbol)
    ready={k:add_indicators(v) for k,v in frames.items() if len(v)>=25}
    if not ready: raise RuntimeError("No usable market data")
    base=ready["5"] if "5" in ready else next(iter(ready.values()))
    snaps={k:timeframe_snapshot(v) for k,v in frames.items() if len(v)>=25}
    out=decide(base,a.portfolio_weight,alignment(snaps))
    meta=metas.get("5") or next(iter(metas.values()))
    out.update({"symbol":a.symbol,"cost":a.cost,"shares":a.shares,
      "data_time":meta.get("data_time"),"provider":meta.get("provider"),"timeframes":list(ready)})
    store=StateStore(a.state_file); prev=store.get(a.symbol)
    changed=materially_changed(prev,out)
    out["changed"]=changed
    if not changed: out["status_message"]="维持上一判断"
    store.put(AnalysisState(a.symbol,out["regime"],out["action"],out.get("t_action"),
                            out["score"],out["support"],out["resistance"],out.get("data_time")))
    if a.json: print(json.dumps(out,ensure_ascii=False,indent=2))
    elif not changed: print(f'{a.symbol} | {out["price"]:.2f}\n维持上一判断 | {out["action"]} | T仓 {out.get("t_action","WAIT")}')
    else: print(render_card(out))
if __name__=="__main__": main()
