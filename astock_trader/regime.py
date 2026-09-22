def classify(row, prev=None):
    bullish = row["close"] > row["ema20"] and row["ema5"] > row["ema10"] > row["ema20"]
    bearish = row["close"] < row["ema20"] and row["ema5"] < row["ema10"] < row["ema20"]
    if bullish and row["rsi12"] >= 60:
        return "STRONG_UPTREND"
    if bullish:
        return "UPTREND"
    if bearish:
        return "DOWNTREND"
    return "RANGE"
