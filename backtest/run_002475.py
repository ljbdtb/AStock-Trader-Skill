"""First reproducible 002475 OOS baseline. No hand-tuning to results."""
import akshare as ak
import pandas as pd
from backtest.walk_forward import walk_forward

def load_daily():
    df=ak.stock_zh_a_hist(symbol="002475",period="daily",
        start_date="20150101",end_date="20260922",adjust="qfq")
    df=df.rename(columns={"日期":"date","开盘":"open","收盘":"close","最高":"high",
                          "最低":"low","成交量":"volume","成交额":"amount"})
    df["date"]=pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)

def ema_signal(df,fast=10,slow=20):
    # Deliberately simple baseline; execution lag is enforced in evaluate().
    f=df.close.ewm(span=fast,adjust=False).mean()
    s=df.close.ewm(span=slow,adjust=False).mean()
    return (f>s).astype(float)

def main():
    df=load_daily()
    grid=[{"fast":5,"slow":20},{"fast":10,"slow":20},
          {"fast":10,"slow":30},{"fast":20,"slow":60}]
    out=walk_forward(df,ema_signal,grid,train=500,test=120,embargo=5,cost_bps=15)
    print("symbol=002475 source=AKShare/Eastmoney adjust=qfq cost_bps=15 embargo=5")
    print(out.to_csv(index=False))
    if len(out):
        print("SUMMARY",{
          "folds":len(out),
          "mean_oos_return":round(float(out.oos_return.mean()),6),
          "mean_oos_sharpe":round(float(out.oos_sharpe.mean()),4),
          "worst_oos_drawdown":round(float(out.oos_max_drawdown.min()),6),
          "trades":int(out.trades.sum())})
if __name__=="__main__": main()
