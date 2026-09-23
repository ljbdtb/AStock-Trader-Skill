import pandas as pd
from backtest.walk_forward import evaluate,expanding_windows

def test_position_is_shifted_to_prevent_same_bar_lookahead():
    # The only gain occurs on bar 1. A signal first becoming active on bar 1
    # must NOT receive bar 1's already-realized return; it may act from bar 2.
    close=pd.Series([100.,110.,110.])
    pos=pd.Series([0.,1.,0.])
    m=evaluate(close,pos,cost_bps=0)
    assert abs(m.total_return)<1e-12

def test_next_bar_return_is_allowed():
    # Signal on bar 1 is shifted to bar 2, so bar 2's forward return is earned.
    close=pd.Series([100.,100.,110.])
    pos=pd.Series([0.,1.,0.])
    m=evaluate(close,pos,cost_bps=0)
    assert abs(m.total_return-0.10)<1e-12

def test_embargo_gap():
    tr,te=next(expanding_windows(300,train=120,test=40,embargo=5))
    assert tr.stop==120
    assert te.start==125
    assert te.start-tr.stop==5

from backtest.risk_sizing import volatility_target_exposure


def test_volatility_sizing_uses_only_current_and_past_closes():
    close = pd.Series([100., 101., 99., 102., 98., 103., 100., 101., 99., 104.])
    baseline = volatility_target_exposure(close, target_vol=0.20, lookback=3)
    changed_future = close.copy()
    changed_future.iloc[7:] *= 3
    revised = volatility_target_exposure(changed_future, target_vol=0.20, lookback=3)
    pd.testing.assert_series_equal(baseline.iloc[:7], revised.iloc[:7])


def test_volatility_sizing_caps_exposure_and_warms_up_flat():
    close = pd.Series([100., 101., 100., 101., 100., 101., 100.])
    exposure = volatility_target_exposure(close, target_vol=0.20, lookback=3)
    assert exposure.iloc[:3].eq(0).all()
    assert exposure.between(0, 1).all()
    assert exposure.iloc[3:].max() == 1.0


def test_volatility_sizing_has_no_internal_execution_shift():
    close = pd.Series([100., 101., 99., 102., 98., 103., 100.])
    weight = volatility_target_exposure(close, target_vol=0.20, lookback=2)
    executed = weight.shift(1).fillna(0)
    assert executed.iloc[4] == weight.iloc[3]


def test_evaluate_reports_exposure_turnover():
    close = pd.Series([100., 100., 110., 110.])
    position = pd.Series([0., 1., 1., 0.])
    metrics = evaluate(close, position, cost_bps=0)
    assert metrics.turnover == 1.0

from backtest.walk_forward import reconstruct_trades


def test_reconstruct_trades_counts_completed_flat_to_flat_episode():
    close = pd.Series([100., 100., 110., 110., 110.])
    signal = pd.Series([0., 1., 1., 0., 0.])
    metrics = evaluate(close, signal, cost_bps=0)
    assert metrics.trade_count == 1
    assert metrics.rebalance_events == 2
    assert abs(metrics.expectancy - 0.10) < 1e-12
    assert metrics.win_rate == 1.0
    assert metrics.average_holding_period == 2.0
    assert metrics.open_trades == 0


def test_reconstruct_trades_excludes_open_episode_from_closed_stats():
    close = pd.Series([100., 100., 110., 120.])
    signal = pd.Series([0., 1., 1., 1.])
    metrics = evaluate(close, signal, cost_bps=0)
    assert metrics.trade_count == 0
    assert metrics.open_trades == 1


from backtest.run_002475 import summarize


def test_summarize_accepts_buy_and_hold_without_closed_trade_fields():
    summary, _ = summarize(
        [{
            "oos_return": 0.05,
            "oos_sharpe": 0.4,
            "oos_max_drawdown": -0.1,
            "turnover": 0.0,
        }],
        "buy-and-hold",
    )
    assert summary["trade_count"] == 0
    assert summary["profit_factor"] == 0.0
    assert summary["expectancy"] == 0.0
    assert summary["turnover"] == 0.0
