def render_card(result):
    return (
        f'{result["symbol"]} | {result["price"]:.2f}\n'
        f'状态: {result["regime"]} | 评分: {result["score"]}/100\n'
        f'动作: {result["action"]} | T仓: {result.get("t_action","WAIT")}\n'
        f'压力: {result["resistance"]:.2f} | 支撑: {result["support"]:.2f}\n'
        f'失效参考: {result["atr_stop"]:.2f}\n'
        f'数据: {result.get("data_time","unknown")} | {result.get("provider","unknown")}'
    )
