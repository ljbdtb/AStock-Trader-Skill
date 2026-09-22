import argparse, json
from astock_trader.data import fetch_intraday
from astock_trader.indicators import add_indicators
from astock_trader.decision import decide

def main():
    p=argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--cost",type=float)
    p.add_argument("--shares",type=int)
    p.add_argument("--portfolio-weight",type=float)
    p.add_argument("--period",default="5")
    a=p.parse_args()
    df=add_indicators(fetch_intraday(a.symbol,a.period))
    out=decide(df,a.portfolio_weight)
    out.update({"symbol":a.symbol,"cost":a.cost,"shares":a.shares})
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
