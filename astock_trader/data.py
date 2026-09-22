"""Market data layer.

Architecture adapted from mature A-share multi-source projects, but implemented
locally so provider behavior, timestamps and failure state stay explicit.
"""
from datetime import datetime
import time
import pandas as pd

SOURCE_HEALTH={}

def _market(code):
    return "sh" if str(code).startswith(("60","68","9")) else "sz"

def _record(source,ok,error=None):
    x=SOURCE_HEALTH.setdefault(source,{"ok":0,"fail":0,"last_error":None})
    x["ok" if ok else "fail"]+=1
    x["last_error"]=None if ok else str(error)

def normalize(df):
    mapping={"时间":"time","日期":"time","开盘":"open","收盘":"close","最高":"high",
             "最低":"low","成交量":"volume","成交额":"amount"}
    df=df.rename(columns={k:v for k,v in mapping.items() if k in df.columns})
    for c in ("open","high","low","close","volume"):
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    if "time" in df: df["time"]=pd.to_datetime(df["time"],errors="coerce")
    return df.dropna(subset=["open","high","low","close","volume"]).reset_index(drop=True)

def realtime_quote(symbol):
    """Best-effort quote with provider fallback. Never fabricates missing data."""
    import requests
    code=str(symbol).zfill(6); market=_market(code)
    providers=[
      ("tencent",lambda: _quote_tencent(requests,market,code)),
      ("eastmoney",lambda: _quote_eastmoney(requests,code)),
    ]
    errors=[]
    for name,fn in providers:
        try:
            q=fn()
            if q:
                _record(name,True); q["provider"]=name
                q["fetched_at"]=datetime.now().astimezone().isoformat()
                return q
        except Exception as e:
            _record(name,False,e); errors.append(f"{name}:{e}")
    raise RuntimeError("all realtime providers failed: "+"; ".join(errors))

def _quote_tencent(requests,market,code):
    url=f"https://qt.gtimg.cn/q={market}{code}"
    r=requests.get(url,timeout=5); r.raise_for_status()
    text=r.content.decode("gbk",errors="ignore")
    if '~' not in text: return None
    a=text.split('"')[1].split("~")
    if len(a)<35: return None
    return {"symbol":code,"name":a[1],"price":float(a[3]),"pre_close":float(a[4]),
            "open":float(a[5]),"volume":float(a[6]),"high":float(a[33]),"low":float(a[34])}

def _quote_eastmoney(requests,code):
    secid=("1." if _market(code)=="sh" else "0.")+code
    r=requests.get("https://push2.eastmoney.com/api/qt/stock/get",
      params={"secid":secid,"fields":"f43,f44,f45,f46,f47,f48,f57,f58,f60"},timeout=5)
    r.raise_for_status(); d=r.json().get("data")
    if not d: return None
    return {"symbol":code,"name":d.get("f58",""),"price":d["f43"]/100,
            "high":d["f44"]/100,"low":d["f45"]/100,"open":d["f46"]/100,
            "volume":d.get("f47",0),"amount":d.get("f48",0),"pre_close":d["f60"]/100}

def fetch_intraday(symbol,period="5",retries=2):
    """Minute bars via AKShare/Eastmoney, with explicit timestamp metadata."""
    import akshare as ak
    last=None
    for attempt in range(retries+1):
        try:
            df=normalize(ak.stock_zh_a_hist_min_em(symbol=str(symbol).zfill(6),period=period,adjust=""))
            if df.empty: raise RuntimeError("empty minute bars")
            stamp=df.time.iloc[-1].isoformat() if "time" in df and pd.notna(df.time.iloc[-1]) else None
            _record("akshare_eastmoney",True)
            return df,{"provider":"AKShare/Eastmoney","data_time":stamp,
                       "fetched_at":datetime.now().astimezone().isoformat()}
        except Exception as e:
            last=e; _record("akshare_eastmoney",False,e)
            if attempt<retries: time.sleep(.5*(attempt+1))
    raise RuntimeError(f"minute data failed: {last}")

def fetch_frames(symbol,periods=("1","5","15")):
    frames={}; metas={}
    for p in periods:
        try: frames[p],metas[p]=fetch_intraday(symbol,p)
        except Exception as e: metas[p]={"error":str(e)}
    return frames,metas

def healthcheck(symbol="000001"):
    out={"sources":SOURCE_HEALTH.copy()}
    try:
        q=realtime_quote(symbol); out["realtime"]={"ok":True,"provider":q["provider"]}
    except Exception as e: out["realtime"]={"ok":False,"error":str(e)}
    try:
        _,m=fetch_intraday(symbol,"5",0); out["minute"]={"ok":True,**m}
    except Exception as e: out["minute"]={"ok":False,"error":str(e)}
    out["sources"]=SOURCE_HEALTH.copy()
    return out
