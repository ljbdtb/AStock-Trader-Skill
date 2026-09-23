"""Small, dependency-light walk-forward validation helpers."""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Metrics:
    total_return: float
    sharpe: float
    max_drawdown: float
    rebalance_events: int
    turnover: float
    trade_count: int
    profit_factor: float
    expectancy: float
    win_rate: float
    average_win: float
    average_loss: float
    win_loss_ratio: float
    average_holding_period: float
    open_trades: int
    gross_profit: float
    gross_loss: float
    trade_return_sum: float


def reconstruct_trades(executed_position: pd.Series, net_returns: pd.Series):
    """Reconstruct completed flat-to-flat exposure episodes after execution costs."""
    position = executed_position.fillna(0).clip(0, 1).reset_index(drop=True)
    returns = net_returns.fillna(0).reset_index(drop=True)
    outcomes, holding_periods = [], []
    active, compounded, held_days = False, 1.0, 0
    for i, exposure in enumerate(position):
        if not active and exposure > 0:
            active, compounded, held_days = True, 1.0, 0
        if active:
            compounded *= 1.0 + float(returns.iloc[i])
            held_days += int(exposure > 0)
            if exposure <= 0:
                outcomes.append(compounded - 1.0)
                holding_periods.append(held_days)
                active = False
    open_trades = int(active)
    wins = [x for x in outcomes if x > 0]
    losses = [x for x in outcomes if x < 0]
    gross_profit, gross_loss = float(sum(wins)), float(abs(sum(losses)))
    average_win = float(np.mean(wins)) if wins else 0.0
    average_loss = float(np.mean(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )
    win_loss_ratio = average_win / abs(average_loss) if average_loss < 0 else (
        float("inf") if average_win > 0 else 0.0
    )
    return {
        "trade_count": len(outcomes),
        "profit_factor": profit_factor,
        "expectancy": float(np.mean(outcomes)) if outcomes else 0.0,
        "win_rate": len(wins) / len(outcomes) if outcomes else 0.0,
        "average_win": average_win,
        "average_loss": average_loss,
        "win_loss_ratio": win_loss_ratio,
        "average_holding_period": float(np.mean(holding_periods)) if holding_periods else 0.0,
        "open_trades": open_trades,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "trade_return_sum": float(sum(outcomes)),
    }


def evaluate(close, position, cost_bps=10.0, buy_cost_bps=None, sell_cost_bps=None):
    """Evaluate next-bar execution with directional costs and completed trades."""
    pos = position.fillna(0).clip(0, 1).shift(1).fillna(0)
    ret = close.pct_change().fillna(0)
    delta = pos.diff().fillna(pos)
    buys, sells = delta.clip(lower=0), -delta.clip(upper=0)
    if buy_cost_bps is None:
        buy_cost_bps = cost_bps
    if sell_cost_bps is None:
        sell_cost_bps = cost_bps
    costs = buys * (buy_cost_bps / 10000.0) + sells * (sell_cost_bps / 10000.0)
    net = pos * ret - costs
    equity = (1 + net).cumprod()
    drawdown = equity / equity.cummax() - 1
    sd = float(net.std())
    sharpe = float(np.sqrt(252) * net.mean() / sd) if sd > 0 else 0.0
    details = reconstruct_trades(pos, net)
    events = int(((buys + sells) > 0).sum())
    return Metrics(
        total_return=float(equity.iloc[-1] - 1),
        sharpe=sharpe,
        max_drawdown=float(drawdown.min()),
        rebalance_events=events,
        turnover=float((buys + sells).sum()),
        **details,
    )


def expanding_windows(n, train=120, test=40, embargo=5):
    start = train
    while start + embargo + test <= n:
        yield slice(0, start), slice(start + embargo, start + embargo + test)
        start += test


def walk_forward(
    df, signal_fn, param_grid, train=120, test=40, embargo=5, cost_bps=10.0,
    buy_cost_bps=None, sell_cost_bps=None
):
    rows = []
    for fold, (training, testing) in enumerate(expanding_windows(len(df), train, test, embargo), 1):
        best = None
        for params in param_grid:
            train_position = signal_fn(df.iloc[training], **params)
            metrics = evaluate(
                df.close.iloc[training], train_position, cost_bps, buy_cost_bps, sell_cost_bps
            )
            if best is None or metrics.sharpe > best[0]:
                best = (metrics.sharpe, params)
        params = best[1]
        warm = max(0, testing.start - train)
        chunk = df.iloc[warm:testing.stop].copy()
        target_position = signal_fn(chunk, **params)
        start = max(0, testing.start - warm - 1)
        metrics = evaluate(
            chunk.close.iloc[start:], target_position.iloc[start:],
            cost_bps, buy_cost_bps, sell_cost_bps
        )
        rows.append({
            "fold": fold, **params,
            "oos_return": metrics.total_return,
            "oos_sharpe": metrics.sharpe,
            "oos_max_drawdown": metrics.max_drawdown,
            "trade_count": metrics.trade_count,
            "rebalance_events": metrics.rebalance_events,
            "turnover": metrics.turnover,
            "profit_factor": metrics.profit_factor,
            "expectancy": metrics.expectancy,
            "win_rate": metrics.win_rate,
            "average_win": metrics.average_win,
            "average_loss": metrics.average_loss,
            "win_loss_ratio": metrics.win_loss_ratio,
            "average_holding_period": metrics.average_holding_period,
            "open_trades": metrics.open_trades,
            "gross_profit": metrics.gross_profit,
            "gross_loss": metrics.gross_loss,
            "trade_return_sum": metrics.trade_return_sum,
        })
    return pd.DataFrame(rows)
