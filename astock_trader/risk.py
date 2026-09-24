from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd


def market_data_quality(df, meta, now=None, max_age_minutes=15):
    if not meta or meta.get("error") or not meta.get("data_time") or df.empty:
        return False
    required={"time","open","high","low","close","volume"}
    if not required.issubset(df.columns):
        return False
    bars=df[list(required)]
    if bars.isna().any().any():
        return False
    if not np.isfinite(df[["open","high","low","close","volume"]].to_numpy()).all():
        return False
    times=pd.to_datetime(df["time"],errors="coerce")
    if times.isna().any() or times.duplicated().any() or not times.is_monotonic_increasing:
        return False
    if ((df[["open","high","low","close"]]<=0).any().any()
            or (df["volume"]<0).any()
            or (df["high"]<df[["open","close","low"]].max(axis=1)).any()
            or (df["low"]>df[["open","close","high"]].min(axis=1)).any()):
        return False
    market_tz=timezone(timedelta(hours=8))
    try:
        stamp=datetime.fromisoformat(meta["data_time"])
        if stamp.tzinfo is None:
            stamp=stamp.replace(tzinfo=market_tz)
    except (TypeError,ValueError):
        return False
    if times.iloc[-1].to_pydatetime().replace(tzinfo=market_tz)!=stamp:
        return False
    now=now or datetime.now(market_tz)
    age=now.astimezone(market_tz)-stamp.astimezone(market_tz)
    return timedelta(minutes=-1)<=age<=timedelta(minutes=max_age_minutes)


def gate_decision(action,t_action,position,data_ok,concentration_limit=0.50):
    if not data_ok or position is None:
        return "WAIT","WAIT"
    if action not in {"HOLD","WAIT","REDUCE"}:
        action="WAIT"
    if t_action not in {"WAIT","SELL_T","BUYBACK_T"}:
        t_action="WAIT"
    if action=="HOLD" and position.total_shares==0:
        action="WAIT"
    if action=="REDUCE" and position.sellable_shares==0:
        action="WAIT"
    if action=="REDUCE":
        t_action="WAIT"
    if t_action=="SELL_T" and position.sellable_t_shares==0:
        t_action="WAIT"
    if t_action=="BUYBACK_T" and (position.buyback_remaining==0
            or position.portfolio_weight is None
            or position.portfolio_weight>concentration_limit):
        t_action="WAIT"
    return action,t_action


def apply_risk_gate(action, portfolio_weight=None, concentration_limit=0.50):
    if portfolio_weight is not None and portfolio_weight > concentration_limit:
        if action in {"BUY", "ADD"}:
            return "HOLD"
    return action

def structural_stop(row, atr_multiple=1.5):
    return float(row["close"] - atr_multiple*row["atr14"])
