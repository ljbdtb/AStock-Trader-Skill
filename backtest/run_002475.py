"""002475 data/cost audit. Gate strategy interpretation on audit PASS."""
import akshare as ak
import pandas as pd

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

def cost_audit():
    # Baseline model must be explicit. Broker commission is user-specific.
    return {
      "broker_commission_bps_each_side":2.5,
      "transfer_and_exchange_regulatory_bps_each_side":0.541,
      "stamp_tax_bps_sell_only":5.0,
      "slippage_bps_each_side":5.0,
      "approx_round_trip_bps":2*(2.5+0.541+5.0)+5.0,
      "note":"Conservative baseline; broker commission/slippage are assumptions, not universal facts."}

def main():
    df=load_daily(); a=audit(df); c=cost_audit()
    ok=(sum(a["missing"].values())==0 and a["duplicate_dates"]==0 and a["bad_ohlc"]==0
        and a["monotonic_dates"] and a["rows"]>500)
    print("AUDIT_STATUS", "PASS" if ok else "FAIL")
    print("DATA_AUDIT",a)
    print("COST_AUDIT",c)
    if not ok: raise SystemExit(2)

if __name__=="__main__": main()
