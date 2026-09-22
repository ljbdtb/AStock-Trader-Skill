from dataclasses import dataclass

@dataclass
class Position:
    shares:int=0
    cost:float|None=None
    portfolio_weight:float|None=None
    t_shares:int=0

    @property
    def concentrated(self):
        return self.portfolio_weight is not None and self.portfolio_weight>0.50
