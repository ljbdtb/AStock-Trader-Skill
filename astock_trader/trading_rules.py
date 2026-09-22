"""A-share execution constraints and T-position state machine."""

def same_day_sellable(total_shares,today_bought):
    # A-share ordinary stocks are generally T+1: shares bought today are not sellable today.
    return max(0,int(total_shares)-int(today_bought))

def t_signal(regime,row,has_t_inventory=True):
    # SELL_T requires inventory that is legally sellable.
    if regime=="FALSE_BREAKOUT" and has_t_inventory:
        return "SELL_T"
    # BUY_T is a pullback/reclaim setup, not a blind dip-buy.
    if regime in {"UPTREND","STRONG_UPTREND"}:
        near_vwap=abs(float(row.close)/float(row.vwap)-1)<=0.003
        momentum_ok=float(row.rsi12)<65 and float(row.macd_hist)>=0
        if near_vwap and momentum_ok:
            return "BUY_T"
    return "WAIT"
