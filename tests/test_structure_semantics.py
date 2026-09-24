import pandas as pd

from astock_trader.indicators import add_indicators
from astock_trader.structure import (
    market_structure, structure_snapshot, structure_features,
    historical_structure_snapshots, historical_structure_features,
)


def test_equal_highs_and_lows_are_neutral_structure():
    highs = [1, 2, 5, 2, 1, 2, 5.003, 2, 1]
    lows = [5, 4, 1, 4, 5, 4, 1.0005, 4, 5]
    frame = pd.DataFrame({"high": highs, "low": lows})
    result = market_structure(frame)
    assert result["high_state"] == "EH"
    assert result["low_state"] == "EL"
    assert result["bias"] != "BEARISH"


def test_intraday_vwap_resets_by_date_but_not_at_lunch():
    frame = pd.DataFrame({
        "time": pd.to_datetime([
            "2026-09-23 11:25", "2026-09-23 13:05",
            "2026-09-24 09:35", "2026-09-24 09:40"]),
        "open": [10, 20, 30, 40],
        "high": [10, 20, 30, 40],
        "low": [10, 20, 30, 40],
        "close": [10, 20, 30, 40],
        "volume": [1, 3, 2, 2],
    })
    result = add_indicators(frame)
    assert result.vwap.iloc[1] == 17.5
    assert result.vwap.iloc[2] == 30
    assert result.vwap.iloc[3] == 35


def test_daily_bars_do_not_take_intraday_vwap_reset_path():
    frame = pd.DataFrame({
        "time": pd.to_datetime(["2026-09-23", "2026-09-24"]),
        "open": [10, 20], "high": [10, 20], "low": [10, 20],
        "close": [10, 20], "volume": [1, 1],
    })
    assert add_indicators(frame).vwap.iloc[1] == 15


def breakout_bars(second_close=None, first_close=5.9):
    highs = [1, 2, 5, 2, 1, 6]
    lows = [0, 0, 0, 0, 0, 4]
    closes = [0.5, 1, 4, 1, 0.5, first_close]
    volumes = [1000, 1000, 1000, 1000, 1000, 2000]
    if second_close is not None:
        highs.append(6)
        lows.append(4)
        closes.append(second_close)
        volumes.append(1500)
    return pd.DataFrame({
        "time": pd.date_range("2026-09-24 09:30", periods=len(highs), freq="5min"),
        "open": closes, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "vwap": [5.0] * len(highs),
    })


def test_cross_bar_rejection_is_causal_and_reuses_attempt_level():
    frame = breakout_bars(second_close=4.8)
    attempt = structure_snapshot(frame, as_of=5)
    rejected = structure_snapshot(frame, as_of=6)
    assert attempt["breakout_status"] == "BREAKOUT_ATTEMPT"
    assert not attempt["false_breakout"]
    assert rejected["breakout_status"] == "FALSE_BREAKOUT"
    assert rejected["false_breakout"]
    assert attempt["breakout_level"] == rejected["breakout_level"] == 5
    assert rejected["resistance"] == 5
    assert rejected["resistance_source"] == "CONFIRMED_SWING"
    assert rejected["breakout_event_index"] == 5
    assert rejected["reference_available_index"] == 4
    assert rejected["breakout_reference_index"] == 2
    assert rejected["breakout_reference_available_index"] == 4


def test_same_bar_pierce_and_rejection_is_false_breakout():
    frame = breakout_bars(first_close=4.5)
    result = structure_snapshot(frame)
    assert result["breakout_status"] == "FALSE_BREAKOUT"
    assert result["breakout_level"] == result["resistance"] == 5


def test_breakout_requires_hold_and_volume_confirmation():
    frame = breakout_bars(second_close=5.8)
    attempt = structure_snapshot(frame, as_of=5)
    confirmed = structure_snapshot(frame, as_of=6)
    assert attempt["breakout_status"] == "BREAKOUT_ATTEMPT"
    assert confirmed["breakout_status"] == "CONFIRMED_BREAKOUT"
    assert confirmed["confirmation_index"] == 6
    assert confirmed["confirmation_time"] == frame.time.iloc[6]
    assert confirmed["breakout_level"] == attempt["breakout_level"] == 5


def test_breakout_without_volume_confirmation_stays_an_attempt():
    frame = breakout_bars(second_close=5.8)
    frame.loc[5, "volume"] = 1000
    assert structure_snapshot(frame)["breakout_status"] == "BREAKOUT_ATTEMPT"


def test_range_fallback_reference_is_known_before_attempt():
    frame = pd.DataFrame({
        "high": [1.0, 2.0, 3.0], "low": [0.0, 0.0, 1.0],
        "close": [0.5, 1.0, 2.5], "volume": [1000, 1000, 2000],
        "vwap": [1.0, 1.0, 1.0],
    })
    result = structure_snapshot(frame)
    assert result["resistance_source"] == "HISTORICAL_RANGE_FALLBACK"
    assert result["breakout_level"] == result["resistance"] == 2
    assert result["reference_available_index"] == 1


def test_breakout_history_matches_prefix_and_future_mutation():
    frame = breakout_bars(second_close=4.8)
    history = historical_structure_snapshots(frame)
    changed = frame.copy()
    changed.loc[6, ["high", "low", "close", "volume"]] = [9, 4, 8, 9000]
    assert history[5] == structure_snapshot(frame.iloc[:6])
    assert history[5] == structure_snapshot(changed, as_of=5)
    assert history[5]["breakout_status"] == "BREAKOUT_ATTEMPT"
    assert history[6]["breakout_status"] == "FALSE_BREAKOUT"


def test_public_feature_api_uses_authoritative_breakout_semantics():
    frame = breakout_bars(second_close=4.8)
    attempt = structure_features(frame, as_of=5)
    rejected = structure_features(frame, as_of=6)
    assert attempt["breakout_status"] == "BREAKOUT_ATTEMPT"
    assert not attempt["breakout"]
    assert rejected["false_breakout"]
    assert rejected["resistance"] == rejected["breakout_level"] == 5
    assert historical_structure_features(frame)[6] == historical_structure_snapshots(frame)[6]
