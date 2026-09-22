from astock_trader.data import healthcheck
if __name__=="__main__":
    r=healthcheck("002475")
    print(r)
    if not r.get("realtime",{}).get("ok") and not r.get("minute",{}).get("ok"):
        raise SystemExit(1)
