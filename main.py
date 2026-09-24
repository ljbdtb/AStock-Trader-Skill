import argparse,json
from datetime import date
from astock_trader.data import fetch_frames
from astock_trader.indicators import add_indicators
from astock_trader.multitimeframe import timeframe_snapshot,alignment
from astock_trader.decision import decide
from astock_trader.card import render_card
from astock_trader.state import AnalysisState,StateStore,materially_changed
from astock_trader.position import PositionLedger
from astock_trader.risk import market_data_quality

POSITION_FIELDS=("trading_date","core_shares","t_shares","bought_core_today",
                 "bought_t_today","sold_t_today","bought_back_t_today")

def position_from_args(args):
    supplied=[getattr(args,name) is not None for name in POSITION_FIELDS]
    if not any(supplied):
        return None
    if not all(supplied):
        raise ValueError("complete position snapshot required for T+1 decisions")
    position=PositionLedger(
        date.fromisoformat(args.trading_date),args.core_shares,args.t_shares,
        args.bought_core_today,args.bought_t_today,args.sold_t_today,
        args.bought_back_t_today,args.cost,args.portfolio_weight)
    if args.shares is not None and args.shares!=position.total_shares:
        raise ValueError("--shares does not match core_shares + t_shares")
    return position

def main():
    p=argparse.ArgumentParser(); p.add_argument("symbol")
    p.add_argument("--cost",type=float); p.add_argument("--shares",type=int)
    p.add_argument("--portfolio-weight",type=float); p.add_argument("--json",action="store_true")
    p.add_argument("--trading-date")
    for name in POSITION_FIELDS[1:]:
        p.add_argument("--"+name.replace("_","-"),type=int)
    p.add_argument("--state-file",default=".astock_state.json")
    a=p.parse_args()
    position=position_from_args(a)
    frames,metas=fetch_frames(a.symbol)
    ready={k:add_indicators(v) for k,v in frames.items() if len(v)>=25}
    if not ready: raise RuntimeError("No usable market data")
    base=ready["5"] if "5" in ready else next(iter(ready.values()))
    snaps={k:timeframe_snapshot(v) for k,v in frames.items() if len(v)>=25}
    data_ok=("5" in ready and market_data_quality(frames["5"],metas.get("5")))
    current_position=(position if position is not None and "5" in ready
                      and position.trading_date==frames["5"].time.iloc[-1].date()
                      else None)
    out=decide(base,a.portfolio_weight,alignment(snaps),position=current_position,
               data_ok=data_ok)
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
