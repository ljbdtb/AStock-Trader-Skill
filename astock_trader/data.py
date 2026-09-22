import pandas as pd
from datetime import datetime

def normalize(df):
    mapping={"时间":"time","日期":"time","开盘":"open","收盘":"close","最高":"high","最低":"low","成交量":"volume","成交额":"amount"}
    df=df.rename(columns={k:v for k,v in mapping.items() if k in df.columns})
    for c in ("open","high","low","close","volume"): df[c]=pd.to_numeric(df[c],errors="coerce")
    if "time" in df: df["time"]=pd.to_datetime(df["time"],errors="coerce")
    return df.dropna(subset=["open","high","low","close","volume"]).reset_index(drop=True)

def fetch_intraday(symbol,period="5"):
    import akshare as ak
    df=normalize(ak.stock_zh_a_hist_min_em(symbol=symbol,period=period,adjust=""))
    stamp=df.time.iloc[-1].isoformat() if "time" in df and pd.notna(df.time.iloc[-1]) else None
    return df,{"provider":"AKShare/Eastmoney","data_time":stamp,"fetched_at":datetime.now().astimezone().isoformat()}

def fetch_frames(symbol,periods=("1","5","15")):
    frames={}; metas={}
    for p in periods:
        try: frames[p],metas[p]=fetch_intraday(symbol,p)
        except Exception as e: metas[p]={"error":str(e)}
    return frames,metas
