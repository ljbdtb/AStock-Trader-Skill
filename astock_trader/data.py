import pandas as pd

def normalize(df):
    mapping={"时间":"time","日期":"time","开盘":"open","收盘":"close","最高":"high","最低":"low","成交量":"volume","成交额":"amount"}
    df=df.rename(columns={k:v for k,v in mapping.items() if k in df.columns})
    for c in ("open","high","low","close","volume"):
        df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.dropna(subset=["open","high","low","close","volume"]).reset_index(drop=True)

def fetch_intraday(symbol, period="5"):
    import akshare as ak
    df=ak.stock_zh_a_hist_min_em(symbol=symbol,period=period,adjust="")
    return normalize(df)
