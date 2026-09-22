import numpy as np
import pandas as pd

def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-(100/(1+up/dn.replace(0,np.nan)))
def atr(df,n=14):
    pc=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()
def adx(df,n=14):
    up=df.high.diff(); down=-df.low.diff()
    plus=pd.Series(np.where((up>down)&(up>0),up,0.0),index=df.index)
    minus=pd.Series(np.where((down>up)&(down>0),down,0.0),index=df.index)
    a=atr(df,n).replace(0,np.nan)
    p=100*plus.ewm(alpha=1/n,adjust=False).mean()/a
    m=100*minus.ewm(alpha=1/n,adjust=False).mean()/a
    return (100*(p-m).abs()/(p+m).replace(0,np.nan)).ewm(alpha=1/n,adjust=False).mean()
def add_indicators(df):
    df=df.copy()
    for n in (5,10,20,60): df[f"ema{n}"]=ema(df.close,n)
    fast,slow=ema(df.close,12),ema(df.close,26)
    df["macd_dif"]=fast-slow; df["macd_dea"]=ema(df.macd_dif,9)
    df["macd_hist"]=(df.macd_dif-df.macd_dea)*2
    for n in (6,12,24): df[f"rsi{n}"]=rsi(df.close,n)
    df["atr14"]=atr(df,14); df["adx14"]=adx(df,14)
    mid=df.close.rolling(20).mean(); std=df.close.rolling(20).std()
    df["boll_mid"]=mid; df["boll_upper"]=mid+2*std; df["boll_lower"]=mid-2*std
    tp=(df.high+df.low+df.close)/3
    df["vwap"]=(tp*df.volume).cumsum()/df.volume.cumsum().replace(0,np.nan)
    df["obv"]=(np.sign(df.close.diff()).fillna(0)*df.volume).cumsum()
    return df
