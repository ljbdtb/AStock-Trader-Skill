def render_card(result):
    invalidation=result.get("structural_invalidation_level")
    invalidation_text=f"{invalidation:.2f}" if invalidation is not None else "不可判定"
    action_text=result["action"]
    if action_text=="REDUCE":
        action_text=f'REDUCE {result.get("reduce_quantity", 0)}股'
    elif result.get("risk_active"):
        action_text=f'{action_text} | {result.get("decision_status", "STRUCTURAL_RISK_ACTIVE")}'
    return (
        f'{result["symbol"]} | {result["price"]:.2f}\n'
        f'状态: {result["regime"]} | 评分: {result["score"]}/100\n'
        f'动作: {action_text} | T仓: {result.get("t_action","WAIT")}\n'
        f'压力: {result["resistance"]:.2f} | 支撑: {result["support"]:.2f}\n'
        f'失效参考: {invalidation_text}\n'
        f'数据: {result.get("data_time","unknown")} | {result.get("provider","unknown")}'
    )
