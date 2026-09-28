from datetime import date

import pandas as pd

from astock_trader.relative_strength import relative_strength
from astock_trader.scoring import score, score_components
from astock_trader.strategy_config import strategy_config


def _daily(closes):
    return pd.DataFrame({
        "date": pd.date_range("2026-08-03", periods=len(closes), freq="B"),
        "close": closes,
    })


def _frame():
    return pd.DataFrame([{
        "close": 10.0, "low": 9.8, "high": 10.2, "ema5": 10.1,
        "ema10": 10.0, "ema20": 9.9, "macd_dif": 0.2,
        "macd_dea": 0.1, "vwap": 9.9, "rsi12": 60,
        "adx14": 22, "atr14": 0.2, "volume": 1000,
    }])


def _facts():
    return {
        "bias": "BULLISH", "high_state": "HH", "low_state": "HL",
        "breakout": False, "volume_ratio": 1.0,
        "breakout_volume_ratio_threshold": 1.2,
    }


def test_relative_strength_uses_only_completed_common_sessions():
    stock = _daily([100.0] * 21 + [110.0])
    benchmark = _daily([100.0] * 22)
    latest = relative_strength(stock, benchmark, as_of=date(2026, 9, 2))
    assert latest["status"] == "PASS"
    assert latest["as_of"] == "2026-09-01"
    assert round(latest["1d"], 8) == 0.1
    assert round(latest["5d"], 8) == 0.1
    assert round(latest["20d"], 8) == 0.1
    stock.loc[len(stock)] = [pd.Timestamp("2026-09-03"), 10000.0]
    assert relative_strength(stock, benchmark, as_of=date(2026, 9, 2)) == latest


def test_relative_strength_rejects_insufficient_or_unaligned_data():
    stock = _daily([100.0] * 20)
    benchmark = _daily([100.0] * 20)
    assert relative_strength(stock, benchmark, as_of=date(2026, 9, 2))["status"] == "INSUFFICIENT_HISTORY"
    shifted = _daily([100.0] * 22)
    shifted["date"] += pd.Timedelta(days=100)
    assert relative_strength(_daily([100.0] * 22), shifted,
                             as_of=date(2026, 9, 2))["status"] != "PASS"


def test_evidence_components_use_frozen_100_point_weights():
    weights = strategy_config()["weights"]
    assert sum(weights.values()) == 100
    components = score_components(_frame(), mtf_alignment=1.0,
                                  relative_strength={"status": "PASS",
                                                     "1d": 0.01, "5d": 0.02,
                                                     "20d": 0.03},
                                  snapshot=_facts())
    assert set(components) == set(weights)
    assert all(0 <= points <= weights[name] for name, points in components.items())
    assert score(_frame(), 1.0, {"status": "PASS", "1d": 0.01,
                                 "5d": 0.02, "20d": 0.03},
                 snapshot=_facts()) == sum(components.values())


def test_mtf_and_relative_strength_have_their_declared_weights():
    positive = {"status": "PASS", "1d": 0.01, "5d": 0.02, "20d": 0.03}
    negative = {"status": "PASS", "1d": -0.01, "5d": -0.02, "20d": -0.03}
    base = score_components(_frame(), mtf_alignment=0.0,
                            relative_strength=negative, snapshot=_facts())
    full = score_components(_frame(), mtf_alignment=1.0,
                            relative_strength=positive, snapshot=_facts())
    assert base["multi_timeframe"] == 0
    assert full["multi_timeframe"] == 10
    assert base["relative_strength"] == 0
    assert full["relative_strength"] == 10


def test_decision_does_not_add_extra_structure_bonus(monkeypatch):
    from astock_trader import decision

    facts = {**_facts(), "support": 9.8, "resistance": 10.2,
             "support_source": "UNKNOWN", "resistance_source": "UNKNOWN",
             "confirmed_swing_low": None, "breakout_status": "KNOWN_LEVEL",
             "breakout_level": None}
    monkeypatch.setattr(decision, "structure_snapshot", lambda df: facts)
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "STRONG_UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 70)
    out = decision.decide(_frame(), data_ok=False)
    assert out["score"] == 70
    assert out["action"] == "WAIT"


def test_daily_provider_uses_qfq_stock_and_price_index(monkeypatch):
    import akshare as ak
    from astock_trader.relative_strength import fetch_relative_strength

    calls = {}
    dates = pd.date_range("2026-08-03", periods=22, freq="B")
    stock = pd.DataFrame({"日期": dates, "收盘": [100.0] * 21 + [110.0]})
    benchmark = pd.DataFrame({"日期": dates, "收盘": [100.0] * 22})

    def stock_provider(**kwargs):
        calls["stock"] = kwargs
        return stock

    def index_provider(**kwargs):
        calls["index"] = kwargs
        return benchmark

    monkeypatch.setattr(ak, "stock_zh_a_hist", stock_provider)
    monkeypatch.setattr(ak, "stock_zh_index_daily", index_provider)
    result = fetch_relative_strength("002475", date(2026, 9, 2))
    assert result["status"] == "PASS"
    assert calls["stock"]["adjust"] == "qfq"
    assert calls["index"]["symbol"] == "sh000300"


def test_card_displays_evidence_dates_and_missing_state():
    from astock_trader.card import render_card

    base = {"symbol": "002475", "price": 10.0, "regime": "RANGE",
            "structure": "EH/EL", "score": 50, "action": "WAIT",
            "t_action": "WAIT", "resistance": 10.2, "support": 9.8,
            "data_quality": "PASS", "mtf_alignment": 2 / 3,
            "mtf_status": "PASS",
            "relative_strength": {"status": "PASS", "as_of": "2026-09-01",
                                  "1d": 0.01, "5d": -0.02, "20d": 0.03}}
    card = render_card(base)
    assert "2026-09-01" in card
    assert "多周期" in card
    assert "1D +1.00%" in card
    base["relative_strength"] = {"status": "UNAVAILABLE"}
    assert "UNAVAILABLE" in render_card(base)
