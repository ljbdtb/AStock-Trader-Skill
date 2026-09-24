"""A-share execution constraints and T-position state machine."""

def same_day_sellable(total_shares,today_bought):
    # A-share ordinary stocks are generally T+1: shares bought today are not sellable today.
    return max(0,int(total_shares)-int(today_bought))

def t_signal(regime,row,position=None):
    if position is None:
        return "WAIT"
    if regime=="FALSE_BREAKOUT" and position.sellable_t_shares>0:
        return "SELL_T"
    if regime in {"UPTREND","STRONG_UPTREND"} and position.buyback_remaining>0:
        near_vwap=abs(float(row.close)/float(row.vwap)-1)<=0.003
        momentum_ok=float(row.rsi12)<65 and float(row.macd_hist)>=0
        if near_vwap and momentum_ok:
            return "BUYBACK_T"
    return "WAIT"
