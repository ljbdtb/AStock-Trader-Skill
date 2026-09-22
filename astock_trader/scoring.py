def score(row):
    s=50
    s += 8 if row["close"] > row["ema20"] else -8
    s += 6 if row["ema5"] > row["ema10"] else -6
    s += 6 if row["macd_dif"] > row["macd_dea"] else -6
    s += 5 if row["close"] > row["vwap"] else -5
    if 50 <= row["rsi12"] <= 75: s += 5
    elif row["rsi12"] < 40: s -= 5
    return max(0,min(100,int(round(s))))
