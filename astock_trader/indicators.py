import numpy as np
import pandas as pd

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d=s.diff()
    up=d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn=(-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs=up/dn.replace(0, np.nan)
    return 100-(100/(1+rs))

def atr(df, n=14):
    pc=df["close"].shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def add_indicators(df):
    df=df.copy()
    for n in (5,10,20,60): df[f"ema{n}"]=ema(df.close,n)
    fast,slow=ema(df.close,12),ema(df.close,26)
    df["macd_dif"]=fast-slow
    df["macd_dea"]=ema(df.macd_dif,9)
    df["macd_hist"]=(df.macd_dif-df.macd_dea)*2
    for n in (6,12,24): df[f"rsi{n}"]=rsi(df.close,n)
    df["atr14"]=atr(df,14)
    tp=(df.high+df.low+df.close)/3
    df["vwap"]=(tp*df.volume).cumsum()/df.volume.cumsum().replace(0,np.nan)
    df["obv"]=(np.sign(df.close.diff()).fillna(0)*df.volume).cumsum()
    return df
