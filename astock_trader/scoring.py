"""Fixed, bounded evidence score for decision support.

Weights are read from config/strategy.yaml and must sum to 100. Each component
has a declared maximum; no additional score adjustments are permitted later.
These are frozen v1 hypotheses, not parameters selected from OOS outcomes.
"""
import math

from .strategy_config import strategy_config
from .structure import structure_snapshot


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _above(left, right):
    a, b = _number(left), _number(right)
    return a is not None and b is not None and a > b


def score_components(df, mtf_alignment=0.5, relative_strength=None, snapshot=None):
    weights = strategy_config()["weights"]
    if sum(weights.values()) != 100:
        raise ValueError("evidence weights must sum to 100")
    f = snapshot if snapshot is not None else structure_snapshot(df)
    row = df.iloc[-1]
    bias = f.get("bias")
    price_structure = (
        weights["price_structure"] if bias == "BULLISH"
        else 0 if bias == "BEARISH"
        else round(weights["price_structure"] * 0.5)
    )
    trend = (
        weights["trend"] if _above(row.get("ema5"), row.get("ema10"))
        and _above(row.get("ema10"), row.get("ema20"))
        and _above(row.get("close"), row.get("ema20"))
        else round(weights["trend"] * 0.5)
        if _above(row.get("close"), row.get("ema20")) else 0
    )
    threshold = _number(f.get("breakout_volume_ratio_threshold"))
    volume_ratio = _number(f.get("volume_ratio"))
    volume_price = (
        weights["volume_price"] if f.get("breakout") and
        threshold is not None and volume_ratio is not None and volume_ratio >= threshold
        else 0
    )
    vwap = weights["vwap"] if _above(row.get("close"), row.get("vwap")) else 0
    momentum = (
        round(weights["momentum"] * 0.5) if _above(row.get("macd_dif"), row.get("macd_dea")) else 0
    )
    rsi = _number(row.get("rsi12"))
    if rsi is not None and 50 <= rsi <= 75:
        momentum += weights["momentum"] - round(weights["momentum"] * 0.5)
    atr, close = _number(row.get("atr14")), _number(row.get("close"))
    # An observed, finite ATR earns the volatility-data component. Directional
    # volatility thresholds require separate pre-registered research.
    volatility = weights["volatility"] if atr is not None and close is not None and 0 < atr < close else 0
    rs = 0
    if isinstance(relative_strength, dict) and relative_strength.get("status") == "PASS":
        for horizon, points in (("1d", 2), ("5d", 3), ("20d", 5)):
            value = _number(relative_strength.get(horizon))
            if value is not None and value > 0:
                rs += points
    alignment = _number(mtf_alignment)
    mtf = round(weights["multi_timeframe"] * max(0, min(1, alignment))) if alignment is not None else 0
    result = {
        "price_structure": price_structure,
        "trend": trend,
        "volume_price": volume_price,
        "vwap": vwap,
        "momentum": momentum,
        "volatility": volatility,
        "relative_strength": rs,
        "multi_timeframe": mtf,
    }
    for name, points in result.items():
        if not 0 <= points <= weights[name]:
            raise ValueError(f"evidence component out of bounds: {name}")
    return result


def score(df, mtf_alignment=0.5, relative_strength=None, snapshot=None):
    return sum(score_components(df, mtf_alignment, relative_strength, snapshot).values())
