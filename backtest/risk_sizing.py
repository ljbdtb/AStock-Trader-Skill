"""Causal volatility-based exposure sizing."""
import numpy as np
import pandas as pd


def volatility_target_exposure(close, target_vol, lookback, max_position=1.0):
    """Return close-time target exposure; evaluate() applies the sole next-bar shift."""
    if target_vol <= 0:
        raise ValueError("target_vol must be positive")
    if lookback < 2:
        raise ValueError("lookback must be at least 2 sessions")
    if not 0 < max_position <= 1:
        raise ValueError("max_position must be in (0, 1]")
    returns = close.pct_change()
    realized_vol = returns.rolling(lookback, min_periods=lookback).std() * np.sqrt(252)
    exposure = (target_vol / realized_vol).replace([np.inf, -np.inf], np.nan)
    return exposure.clip(lower=0, upper=max_position).fillna(0.0)
