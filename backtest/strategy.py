try:
    import backtrader as bt
except ImportError:
    bt=None

if bt:
    class RegimeStrategy(bt.Strategy):
        params=(("fast",5),("slow",20),("atr_period",14),("atr_mult",1.5))
        def __init__(self):
            self.fast=bt.ind.EMA(period=self.p.fast)
            self.slow=bt.ind.EMA(period=self.p.slow)
            self.atr=bt.ind.ATR(period=self.p.atr_period)
        def next(self):
            if not self.position and self.fast[0]>self.slow[0]:
                self.buy()
            elif self.position and self.fast[0]<self.slow[0]:
                self.close()
