from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from math import isfinite
import numpy as np
import pandas as pd
from .strategy_config import strategy_config


@dataclass(frozen=True)
class StructuralInvalidation:
    reference_level: float | None
    reference_type: str
    atr: float | None
    atr_buffer: float | None
    invalidation_level: float | None
    breached: bool
    confirmed: bool
    active: bool
    status: str
    reason_codes: tuple[str, ...]


def structural_invalidation(snapshot, close, low, atr, data_ok=True, previous=None):
    """Evaluate a confirmed higher-low level already present in StructureSnapshot."""
    previous = previous or {}
    was_active = bool(previous.get("active"))
    previous_reference = previous.get("reference_level") if was_active else None
    previous_reference_type = previous.get("reference_type", "CONFIRMED_HIGHER_LOW")
    reference = snapshot.get("confirmed_swing_low")
    valid_reference = (snapshot.get("low_state") == "HL"
                       and snapshot.get("support_source") == "CONFIRMED_SWING"
                       and reference is not None and isfinite(float(reference))
                       and float(reference) > 0)
    reference_type = "CONFIRMED_HIGHER_LOW"
    valid_atr = atr is not None and isfinite(float(atr)) and float(atr) > 0
    if not data_ok:
        return StructuralInvalidation(
            previous_reference, previous_reference_type if was_active else "UNKNOWN",
            None, None, previous.get("invalidation_level") if was_active else None,
            False, False, was_active, "WAIT_DATA",
            ("DATA_STALE_NO_NEW_INVALIDATION",))
    new_higher_low = (was_active and valid_reference
                      and previous_reference is not None
                      and float(reference) > float(previous_reference))
    if was_active and not new_higher_low and previous_reference is not None:
        reference = previous_reference
        reference_type = previous_reference_type
        valid_reference = True
    if not valid_reference or not valid_atr:
        reason = "NO_CONFIRMED_HIGHER_LOW" if not valid_reference else "ATR_UNAVAILABLE"
        return StructuralInvalidation(
            float(reference) if valid_reference else None,
            reference_type if valid_reference else "UNKNOWN",
            float(atr) if valid_atr else None, None, None, False, False,
            was_active, "UNAVAILABLE", (reason,))
    buffer = float(atr) * strategy_config()["risk"]["structural_atr_buffer"]
    level = float(reference) - buffer
    breached = float(low) < level
    confirmed = float(close) < level
    active = confirmed or (was_active and not (
        new_higher_low and float(close) >= level))
    status = ("CONFIRMED_INVALIDATION" if confirmed else
              "RECOVERY" if active and was_active else
              "BREACH" if breached else "INTACT")
    reason_codes = (("STRUCTURE_INVALIDATED",) if confirmed else
                    ("STRUCTURAL_RISK_ACTIVE",) if active else
                    ("INTRABAR_BREACH_UNCONFIRMED",) if breached else ())
    return StructuralInvalidation(float(reference), reference_type,
                                  float(atr), buffer, level, breached,
                                  confirmed, active, status, reason_codes)


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


def gate_decision(action,t_action,position,data_ok,concentration_limit=0.50,
                  invalidation=None):
    if not data_ok or position is None:
        return "WAIT","WAIT"
    if action not in {"HOLD","WAIT","REDUCE"}:
        action="WAIT"
    if t_action not in {"WAIT","SELL_T","BUYBACK_T"}:
        t_action="WAIT"
    if invalidation is not None and invalidation.active:
        action="REDUCE"
        t_action="WAIT"
    if action=="HOLD" and position.total_shares==0:
        action="WAIT"
    if action=="REDUCE" and position.sellable_core_shares==0:
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
