import pandas as pd
import pytest

from astock_trader.structure import (
    confirmed_pivots, historical_structure_features, market_structure,
    structure_features,
)


def bars(highs, lows=None, closes=None):
    lows = lows if lows is not None else [0.0] * len(highs)
    closes = closes if closes is not None else [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=len(highs), freq="D"),
        "high": highs, "low": lows, "close": closes,
        "volume": [1000] * len(highs),
    })


def test_pivot_high_is_unavailable_until_second_right_bar():
    df = bars([1, 2, 5, 2, 1])
    for t in (2, 3):
        assert [p for p in confirmed_pivots(df, as_of=t) if p.type == "HIGH"] == []
    high = [p for p in confirmed_pivots(df, as_of=4) if p.type == "HIGH"]
    assert len(high) == 1
    assert (high[0].event_index, high[0].confirmed_index, high[0].price) == (2, 4, 5)
    assert high[0].event_time == df.time.iloc[2]
    assert high[0].confirmed_at == df.time.iloc[4]


@pytest.mark.parametrize("second,expected", [(6, "HH"), (4, "LH")])
def test_high_state_and_swing_change_only_on_confirmation(second, expected):
    df = bars([1, 2, 5, 2, 1, 2, second, 2, 1])
    for t in (6, 7):
        state = market_structure(df, as_of=t)
        assert state["high_state"] == "NA"
        assert state["swing_high"] == 5
    state = market_structure(df, as_of=8)
    assert state["high_state"] == expected
    assert state["swing_high"] == second


@pytest.mark.parametrize("second,expected", [(2, "HL"), (0, "LL")])
def test_low_state_and_swing_change_only_on_confirmation(second, expected):
    df = bars([10] * 9, [5, 4, 1, 4, 5, 4, second, 4, 5])
    for t in (6, 7):
        state = market_structure(df, as_of=t)
        assert state["low_state"] == "NA"
        assert state["swing_low"] == 1
    state = market_structure(df, as_of=8)
    assert state["low_state"] == expected
    assert state["swing_low"] == second


def test_future_mutation_cannot_change_as_of_structure():
    df = bars([1, 2, 5, 2, 1, 2, 6, 2, 1, 3])
    baseline_history = historical_structure_features(df)
    for t in (5, 6, 7, 8):
        changed = df.copy()
        changed.loc[t+1:, ["high", "low", "close", "volume"]] = [100, -50, 20, 9000]
        assert market_structure(df, as_of=t) == market_structure(changed, as_of=t)
        pd.testing.assert_series_equal(
            pd.Series(structure_features(df, as_of=t)),
            pd.Series(structure_features(changed, as_of=t)))
        changed_history = historical_structure_features(changed)
        for past in range(t + 1):
            pd.testing.assert_series_equal(
                pd.Series(baseline_history[past]),
                pd.Series(changed_history[past]))


def test_breakout_reference_was_available_before_breakout_bar():
    df = bars([1, 2, 5, 2, 1, 2, 7], closes=[0.5, 1, 4, 1, 0.5, 1, 6])
    feature = structure_features(df, as_of=6)
    assert feature["breakout_status"] == "BREAKOUT_ATTEMPT"
    assert not feature["breakout"]
    assert feature["prev_high"] == 5
    assert feature["breakout_reference_index"] == 2
    assert feature["breakout_reference_available_index"] < 6
    assert [p.confirmed_index for p in confirmed_pivots(df, as_of=6)
            if p.type == "HIGH" and p.event_index == 2] == [4]


def test_historical_feature_at_every_bar_matches_live_prefix():
    df = bars([1, 2, 5, 2, 1, 2, 6, 2, 1, 3, 7, 3, 1])
    features = historical_structure_features(df)
    assert len(features) == len(df)
    for t, feature in enumerate(features):
        expected = structure_features(df.iloc[:t + 1])
        pd.testing.assert_series_equal(pd.Series(feature), pd.Series(expected))
    assert features[7]["swing_high"] == 5
    assert features[8]["swing_high"] == 6
