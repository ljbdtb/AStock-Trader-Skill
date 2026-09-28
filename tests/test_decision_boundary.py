from datetime import date
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from astock_trader.position import PositionLedger


def _frame():
    return pd.DataFrame([{"close": 10.0, "low": 9.8, "high": 10.2,
                          "atr14": 1.0, "vwap": 10.0, "rsi12": 50,
                          "macd_hist": 0.1, "volume": 1000}])


def _facts():
    return {"bias": "MIXED", "high_state": "NA", "low_state": "NA",
            "confirmed_swing_low": None, "support": 9.8,
            "support_source": "UNKNOWN", "resistance": 10.2,
            "resistance_source": "UNKNOWN", "breakout_status": "KNOWN_LEVEL",
            "breakout_level": None, "volume_ratio": 1.0}


def test_sell_t_exposes_only_allowed_upper_bound(monkeypatch):
    from astock_trader import decision

    monkeypatch.setattr(decision, "structure_snapshot", lambda df: _facts())
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "FALSE_BREAKOUT")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 50)
    position = PositionLedger(date(2026, 9, 24), core_shares=100,
                              t_shares=300, bought_t_today=100)
    out = decision.decide(_frame(), position=position, data_ok=True)
    assert out["t_action"] == "SELL_T"
    assert out["max_sell_t_qty"] == 200
    assert out["max_buyback_t_qty"] == 0
    assert "order_qty" not in out


def test_buyback_t_exposes_only_allowed_upper_bound(monkeypatch):
    from astock_trader import decision

    monkeypatch.setattr(decision, "structure_snapshot", lambda df: _facts())
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 50)
    position = PositionLedger(date(2026, 9, 24), core_shares=100,
                              t_shares=100, sold_t_today=200,
                              portfolio_weight=0.3)
    out = decision.decide(_frame(), position=position, data_ok=True)
    assert out["t_action"] == "BUYBACK_T"
    assert out["max_buyback_t_qty"] == 200
    assert out["max_sell_t_qty"] == 0
    assert "order_qty" not in out


def test_blocked_t_action_has_no_allowed_quantity(monkeypatch):
    from astock_trader import decision

    monkeypatch.setattr(decision, "structure_snapshot", lambda df: _facts())
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 50)
    position = PositionLedger(date(2026, 9, 24), core_shares=100,
                              t_shares=100, sold_t_today=200,
                              portfolio_weight=0.6)
    out = decision.decide(_frame(), position=position, data_ok=True)
    assert out["t_action"] == "WAIT"
    assert out["max_buyback_t_qty"] == 0
    assert out["max_sell_t_qty"] == 0


@pytest.mark.parametrize("option", ["--execute", "--live", "--broker",
                                    "--place-order", "--auto-trade"])
def test_cli_rejects_execution_option_before_loading_market_data(option):
    main = Path(__file__).resolve().parents[1] / "main.py"
    result = subprocess.run([sys.executable, str(main), "002475", option],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert f"unrecognized arguments: {option}" in result.stderr


def test_recommendation_is_deterministic_for_same_inputs(monkeypatch):
    from astock_trader import decision

    monkeypatch.setattr(decision, "structure_snapshot", lambda df: _facts())
    monkeypatch.setattr(decision, "classify", lambda df, snapshot: "UPTREND")
    monkeypatch.setattr(decision, "score", lambda *args, **kwargs: 50)
    position = PositionLedger(date(2026, 9, 24), core_shares=100,
                              t_shares=100, sold_t_today=200,
                              portfolio_weight=0.3)
    frame = _frame()
    assert decision.decide(frame, position=position, data_ok=True) == \
           decision.decide(frame, position=position, data_ok=True)


def test_card_explains_structural_reduce_as_decision_support():
    from astock_trader.card import render_card

    card = render_card({"symbol": "002475", "price": 9.7,
                        "regime": "UPTREND", "structure": "HH/HL",
                        "score": 90, "action": "REDUCE", "t_action": "WAIT",
                        "max_reducible_qty": 1600,
                        "risk_reason_codes": ["STRUCTURE_INVALIDATED"],
                        "resistance": 11, "support": 10,
                        "structural_invalidation_level": 9.75,
                        "data_quality": "PASS", "data_time": "09:35",
                        "provider": "example"})
    assert "决策辅助建议（非委托）" in card
    assert "结构: HH/HL" in card
    assert "数据质量: PASS" in card
    assert "原因: 结构失效确认" in card
    assert "可减核心仓上限: ≤1600股" in card
    assert "SELL 1600" not in card
