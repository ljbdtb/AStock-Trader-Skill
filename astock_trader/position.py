from dataclasses import dataclass
from datetime import date
from math import isfinite

@dataclass
class Position:
    shares:int=0
    cost:float|None=None
    portfolio_weight:float|None=None
    t_shares:int=0

    @property
    def concentrated(self):
        return self.portfolio_weight is not None and self.portfolio_weight>0.50


@dataclass
class PositionLedger:
    trading_date: date
    core_shares: int = 0
    t_shares: int = 0
    bought_core_today: int = 0
    bought_t_today: int = 0
    sold_t_today: int = 0
    bought_back_t_today: int = 0
    cost_basis: float | None = None
    portfolio_weight: float | None = None
    sold_core_today: int = 0

    def __post_init__(self):
        self._validate()

    def _validate(self):
        quantities = (self.core_shares, self.t_shares, self.bought_core_today,
                      self.bought_t_today, self.sold_t_today,
                      self.bought_back_t_today, self.sold_core_today)
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0
               for n in quantities):
            raise ValueError("share counts must be nonnegative integers")
        if self.bought_core_today > self.core_shares or self.bought_t_today > self.t_shares:
            raise ValueError("today's purchases cannot exceed holdings")
        if self.bought_back_t_today > self.sold_t_today:
            raise ValueError("buybacks cannot exceed today's T sales")
        if self.bought_back_t_today > self.bought_t_today:
            raise ValueError("buybacks must be included in today's T purchases")
        if (self.portfolio_weight is not None
                and (not isfinite(self.portfolio_weight)
                     or not 0 <= self.portfolio_weight <= 1)):
            raise ValueError("portfolio weight must be between zero and one")

    @property
    def total_shares(self):
        return self.core_shares + self.t_shares

    @property
    def bought_today(self):
        return self.bought_core_today + self.bought_t_today

    @property
    def sellable_core_shares(self):
        return self.core_shares - self.bought_core_today

    @property
    def sellable_t_shares(self):
        return self.t_shares - self.bought_t_today

    @property
    def sellable_shares(self):
        return self.sellable_core_shares + self.sellable_t_shares

    @property
    def buyback_remaining(self):
        return self.sold_t_today - self.bought_back_t_today

    @property
    def sold_today(self):
        return self.sold_core_today + self.sold_t_today

    def sell_core(self, shares):
        if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0:
            raise ValueError("sale quantity must be a positive integer")
        if shares > self.sellable_core_shares:
            raise ValueError("T+1: insufficient sellable core inventory")
        self.core_shares -= shares
        self.sold_core_today += shares
        self._validate()

    def sell_t(self, shares):
        if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0:
            raise ValueError("sale quantity must be a positive integer")
        if shares > self.sellable_t_shares:
            raise ValueError("T+1: insufficient sellable T inventory")
        self.t_shares -= shares
        self.sold_t_today += shares
        self._validate()

    def buyback_t(self, shares):
        if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0:
            raise ValueError("buyback quantity must be a positive integer")
        if shares > self.buyback_remaining:
            raise ValueError("buyback exceeds today's T sales")
        self.t_shares += shares
        self.bought_t_today += shares
        self.bought_back_t_today += shares
        self._validate()

    def rollover(self, next_trading_date):
        if next_trading_date <= self.trading_date:
            raise ValueError("trading date must advance")
        self.trading_date = next_trading_date
        self.bought_core_today = 0
        self.bought_t_today = 0
        self.sold_t_today = 0
        self.sold_core_today = 0
        self.bought_back_t_today = 0
        self._validate()
