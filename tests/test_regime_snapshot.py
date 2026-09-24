import pandas as pd

from astock_trader import decision, regime, scoring
from astock_trader.indicators import add_indicators
from astock_trader.structure import structure_snapshot


def frame(highs, lows, last_close=None):
    close = [(h + l) / 2 for h, l in zip(highs, lows)]
    if last_close is not None:
        close[-1] = last_close
    result = pd.DataFrame({
        "high": highs, "low": lows, "close": close,
        "open": close, "volume": [1000] * len(highs),
        "vwap": [sum(close) / len(close)] * len(highs),
    })
    result["ema5"] = result.close - 0.1
    result["ema10"] = result.close - 0.2
    result["ema20"] = result.close - 0.3
    result["rsi12"] = 70.0
    result["adx14"] = 25.0
    return result


def test_bullish_reversal_needs_prior_bearish_structure_break():
    highs = [11, 12, 16, 12, 11, 12, 13, 15, 13, 12, 13, 13, 17]
    lows = [8, 7, 6, 7, 5, 6, 6, 7, 6, 4, 5, 6, 7]
    data = frame(highs, lows, last_close=16.5)
    snapshot = structure_snapshot(data)
    assert snapshot["prior_bias"] == "BEARISH"
    assert snapshot["prior_swing_high"] == 15
    assert regime.classify(data, snapshot=snapshot) == "REVERSAL"


def test_reversal_is_not_repeated_without_a_new_structure_cross():
    highs = [11, 12, 16, 12, 11, 12, 13, 15, 13, 12, 13, 16, 17]
    lows = [8, 7, 6, 7, 5, 6, 6, 7, 6, 4, 5, 6, 7]
    data = frame(highs, lows, last_close=16.5)
    data.loc[11, "close"] = 15.5
    snapshot = structure_snapshot(data)
    assert snapshot["prior_bias"] == "BEARISH"
    assert regime.classify(data, snapshot=snapshot) != "REVERSAL"


def test_bearish_reversal_needs_prior_bullish_structure_break():
    highs = [11, 12, 16, 12, 11, 12, 13, 17, 13, 12, 13, 13, 14]
    lows = [8, 7, 6, 7, 5, 6, 7, 8, 7, 6, 7, 8, 4]
    data = frame(highs, lows, last_close=5)
    snapshot = structure_snapshot(data)
    assert snapshot["prior_bias"] == "BULLISH"
    assert snapshot["prior_swing_low"] == 6
    assert regime.classify(data, snapshot=snapshot) == "REVERSAL"


def test_equal_swing_range_is_explicit_and_not_bearish():
    data = frame([11, 12, 16, 12, 11, 12, 16.005, 12, 11],
                 [8, 7, 5, 7, 8, 7, 5.003, 7, 8])
    data["adx14"] = 12.0
    data["ema5"] = data.close
    data["ema10"] = data.close
    data["ema20"] = data.close
    snapshot = structure_snapshot(data)
    assert snapshot["compression"]
    assert regime.classify(data, snapshot=snapshot) == "RANGE"


def test_momentum_only_is_not_reversal_and_trend_not_range():
    data = frame([10 + i for i in range(30)], [9 + i for i in range(30)])
    snapshot = structure_snapshot(data)
    assert snapshot["prior_bias"] != "BEARISH"
    assert regime.classify(data, snapshot=snapshot) != "REVERSAL"
    assert regime.classify(data, snapshot=snapshot) != "RANGE"


def test_false_breakout_and_attempt_precede_strong_trend():
    from test_structure_semantics import breakout_bars

    rejected = frame_from_breakout(breakout_bars(second_close=4.8))
    assert regime.classify(rejected, snapshot=structure_snapshot(rejected)) == "FALSE_BREAKOUT"
    attempt = rejected.iloc[:6]
    assert regime.classify(attempt, snapshot=structure_snapshot(attempt)) == "BREAKOUT_ATTEMPT"
    confirmed = frame_from_breakout(breakout_bars(second_close=5.8))
    assert regime.classify(confirmed, snapshot=structure_snapshot(confirmed)) == "BREAKOUT"


def frame_from_breakout(data):
    data = data.copy()
    data["ema5"] = data.close - 0.1
    data["ema10"] = data.close - 0.2
    data["ema20"] = data.close - 0.3
    data["rsi12"] = 70.0
    data["adx14"] = 25.0
    return data


def test_decision_uses_one_authoritative_structure_snapshot(monkeypatch):
    data = pd.DataFrame({
        "open": [10 + i * .01 for i in range(40)],
        "high": [10.1 + i * .01 for i in range(40)],
        "low": [9.9 + i * .01 for i in range(40)],
        "close": [10.05 + i * .01 for i in range(40)],
        "volume": [1000] * 40,
    })
    data = add_indicators(data)
    actual = structure_snapshot(data)
    calls = []

    def once(frame):
        calls.append(1)
        return actual

    monkeypatch.setattr(decision, "structure_snapshot", once)
    monkeypatch.setattr(regime, "structure_snapshot",
                        lambda frame: (_ for _ in ()).throw(AssertionError("regime recomputed structure")))
    monkeypatch.setattr(scoring, "structure_snapshot",
                        lambda frame: (_ for _ in ()).throw(AssertionError("score recomputed structure")))
    output = decision.decide(data)
    assert len(calls) == 1
    assert output["resistance"] == round(actual["resistance"], 3)
    assert output["support"] == round(actual["support"], 3)
    assert output["breakout_level"] == actual["breakout_level"]
