"""002475 data/cost audit. Gate strategy interpretation on audit PASS."""
import akshare as ak
import pandas as pd\nfrom backtest.walk_forward import walk_forward

SYMBOL="002475"; START="20150101"; END="20260922"; ADJUST="qfq"

def load_daily():
    raw=ak.stock_zh_a_hist(symbol=SYMBOL,period="daily",start_date=START,end_date=END,adjust=ADJUST)
    df=raw.rename(columns={"日期":"date","开盘":"open","收盘":"close","最高":"high",
      "最低":"low","成交量":"volume","成交额":"amount"})
    df["date"]=pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)

def audit(df):
    cols=["date","open","high","low","close","volume"]
    missing={c:int(df[c].isna().sum()) for c in cols}
    dup=int(df.date.duplicated().sum())
    bad_ohlc=int(((df.high<df[["open","close","low"]].max(axis=1))|
                  (df.low>df[["open","close","high"]].min(axis=1))|
                  (df[["open","high","low","close"]]<=0).any(axis=1)).sum())
    nonpositive_volume=int((df.volume<=0).sum())
    monotonic=bool(df.date.is_monotonic_increasing)
    return {"rows":len(df),"first":str(df.date.iloc[0].date()),"last":str(df.date.iloc[-1].date()),
      "missing":missing,"duplicate_dates":dup,"bad_ohlc":bad_ohlc,
      "nonpositive_volume":nonpositive_volume,"monotonic_dates":monotonic,
      "source":"AKShare stock_zh_a_hist / Eastmoney","adjust":ADJUST}

def ema_signal(df,fast=10,slow=20):
    fast_ma=df.close.ewm(span=fast,adjust=False).mean()
    slow_ma=df.close.ewm(span=slow,adjust=False).mean()
    return (fast_ma>slow_ma).astype(float)

def cost_audit():
    # Baseline model must be explicit. Broker commission is user-specific.
    return {
      "broker_commission_bps_each_side":2.5,
      "transfer_and_exchange_regulatory_bps_each_side":0.541,
      "stamp_tax_bps_sell_only":5.0,
      "slippage_bps_each_side":5.0,
      "buy_cost_bps":2.5+0.541+5.0,\n      "sell_cost_bps":2.5+0.541+5.0+5.0,\n      "approx_round_trip_bps":2*(2.5+0.541+5.0)+5.0,
      "note":"Conservative baseline; broker commission/slippage are assumptions, not universal facts."}

def main():
    df=load_daily(); a=audit(df); c=cost_audit()
    ok=(sum(a["missing"].values())==0 and a["duplicate_dates"]==0 and a["bad_ohlc"]==0
        and a["monotonic_dates"] and a["rows"]>500)
    print("AUDIT_STATUS", "PASS" if ok else "FAIL")
    print("DATA_AUDIT",a)
    print("COST_AUDIT",c)
    if not ok: raise SystemExit(2)
    grid=[{"fast":5,"slow":20},{"fast":10,"slow":20},{"fast":10,"slow":30},{"fast":20,"slow":60}]
    out=walk_forward(df,ema_signal,grid,train=500,test=120,embargo=5,
        buy_cost_bps=c["buy_cost_bps"],sell_cost_bps=c["sell_cost_bps"])
    print("OOS_RESULTS")
    print(out.to_csv(index=False))
    print("OOS_SUMMARY",{"folds":len(out),"mean_return":round(float(out.oos_return.mean()),6),
      "mean_sharpe":round(float(out.oos_sharpe.mean()),4),
      "worst_drawdown":round(float(out.oos_max_drawdown.min()),6),"trades":int(out.trades.sum())})

if __name__=="__main__": main()
