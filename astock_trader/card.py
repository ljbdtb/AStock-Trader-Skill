def render_card(result):
    invalidation=result.get("structural_invalidation_level")
    invalidation_text=f"{invalidation:.2f}" if invalidation is not None else "不可判定"
    action_text=result["action"]
    if result.get("risk_active") and action_text!="REDUCE":
        action_text=f'{action_text} | {result.get("decision_status", "STRUCTURAL_RISK_ACTIVE")}'
    limits=[]
    if action_text=="REDUCE":
        limits.append(f'可减核心仓上限: ≤{result.get("max_reducible_qty", 0)}股')
    if result.get("t_action")=="SELL_T":
        limits.append(f'可卖T仓上限: ≤{result.get("max_sell_t_qty", 0)}股')
    if result.get("t_action")=="BUYBACK_T":
        limits.append(f'可接回T仓上限: ≤{result.get("max_buyback_t_qty", 0)}股')
    reason_codes=result.get("risk_reason_codes") or []
    reason=('结构失效确认' if "STRUCTURE_INVALIDATED" in reason_codes
            else ", ".join(reason_codes))
    evidence=[]
    if "mtf_alignment" in result:
        evidence.append(f'多周期一致性: {result["mtf_alignment"]:.0%} | {result.get("mtf_status","UNKNOWN")}')
    relative=result.get("relative_strength")
    if isinstance(relative,dict):
        if relative.get("status")=="PASS":
            periods=" | ".join(f'{key.upper()} {relative[key]:+.2%}' for key in ("1d","5d","20d"))
            evidence.append(f'相对沪深300价格指数 ({relative["as_of"]}): {periods}')
        else:
            evidence.append(f'相对沪深300: {relative.get("status","UNAVAILABLE")}')
    lines = [
        f'{result["symbol"]} | {result["price"]:.2f}',
        '决策辅助建议（非委托）',
        f'状态: {result["regime"]} | 评分: {result["score"]}/100',
        f'结构: {result.get("structure", "未知")}',
        *evidence,
        f'核心动作: {action_text} | T仓动作: {result.get("t_action","WAIT")}',
        *([f'原因: {reason}'] if reason else []),
        *limits,
        f'压力: {result["resistance"]:.2f} | 支撑: {result["support"]:.2f}',
        f'失效参考: {invalidation_text}',
        f'数据质量: {result.get("data_quality", "UNKNOWN")} | 数据: {result.get("data_time","unknown")} | {result.get("provider","unknown")}',
    ]
    return "\n".join(lines)
