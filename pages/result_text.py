"""Plain-text presenters for design and model results."""


def _responses(project):
    return [item for item in project.responses if item.name]


def _count_filled(project, response_name):
    count = 0
    for row in project.doe_matrix or []:
        try:
            float(row.get(response_name))
        except (TypeError, ValueError):
            continue
        count += 1
    return count


def summary(project):
    method = project.design_method or ""
    if not method:
        return "尚未在【方案配置】生成任何方案。"
    meta = (project.design_params or {}).get("meta") or {}
    lines = [f"【当前方案】{method}", ""]
    if meta:
        lines.append("【设计结构】")
        for key, value in meta.items():
            if key != "groups":
                lines.append(f"  {key} = {value}")
    lines.append("")
    matrix = project.doe_matrix or []
    lines.append(f"试验次数：{len(matrix)}")
    for response in _responses(project):
        lines.append(
            f"响应 [{response.name}]：已填入 "
            f"{_count_filled(project, response.name)} / {len(matrix)} 行")
    lines.append("")
    missing = [
        response.name for response in _responses(project)
        if not matrix or _count_filled(project, response.name) != len(matrix)
    ]
    if missing:
        lines.append(
            f"提示：响应 {missing} 数据不足，请先在【数据管理】填入/导入结果后再执行分析。")
    else:
        lines.append("响应数据齐备，可执行设计优化与后端分析。")
    return "\n".join(lines)


def screening(project):
    result = project.screening_result or {}
    lines = [
        "【筛选设计：主效应分析】",
        result.get("analysis_status", "等待分析"),
        result.get("diagnostic_summary", ""),
        result.get("conclusion", ""),
    ]
    for name, message in result.get("errors", {}).items():
        lines.append(f"{name}：{message}")
    lines.append("各响应的有符号效应、纯误差、中心点曲率和混杂提示见【筛选主效应】页。")
    return "\n".join(lines)


def response_surface(project):
    result = project.rsm_result or {}
    if not result:
        return "尚未生成响应曲面方案。请在【方案配置】选择响应曲面设计并点击生成。"
    lines = ["【响应曲面设计结果】"]
    design = result.get("design") or {}
    for key, value in design.items():
        if key != "groups":
            lines.append(f"  {key} = {value}")
    lines.append("")
    fit = result.get("fit")
    if not fit:
        lines.append(result.get(
            "message",
            "请在【数据管理】填入响应数据后，点击【执行后端分析并更新结果】。"))
        return "\n".join(lines)
    for response_name, response_fit in fit.items():
        if response_fit.get("error"):
            lines.append(f"◆ 响应：{response_name}：{response_fit['error']}")
            continue
        lines.append(f"◆ 响应：{response_name}")
        lines.append(
            f"  R² = {response_fit['r2']} ｜ "
            f"调整 R² = {response_fit['adj_r2']} ｜ "
            f"RMSE = {response_fit['rmse']} ｜ "
            f"模型自由度 {response_fit['df_model']} / "
            f"残差自由度 {response_fit['df_residual']}")
        lines.append(
            f"  编码 z=(x−中心)/半跨度：{response_fit.get('coding', {})}")
        lines.append("  编码变量系数（按绝对值排序）：")
        coefficients = sorted(
            response_fit["coefficients"],
            key=lambda item: abs(item[1]), reverse=True)
        for name, value in coefficients[:8]:
            lines.append(f"    {name} = {value:+.5g}")
        optimum = response_fit.get("optimum")
        if optimum:
            lines.append(
                f"  模型优选设置：{optimum.get('x')} → "
                f"预测 {optimum.get('predicted'):.5g}")
        lines.append("")
    return "\n".join(lines)


def taguchi(project):
    result = project.taguchi_result or {}
    lines = [
        "【田口设计：按响应的稳健水平分析】",
        result.get("summary", ""),
        result.get("analysis_status", "等待响应数据"),
        result.get("recommendation", ""),
    ]
    for name, levels in result.get("best_levels_by_response", {}).items():
        lines.append(f"{name} 的候选水平：{levels}")
    for name, message in result.get("errors", {}).items():
        lines.append(f"{name}：{message}")
    lines.append("内表组均值/标准差、因子水平表、均值与信噪比图见【田口稳健分析】页。")
    return "\n".join(lines)


def surrogate(project):
    result = project.surrogate_result or {}
    config = project.surrogate_config or {}
    lines = ["【代理模型训练结果】"]
    if not config:
        lines.append("尚未配置代理模型。请在【方案配置】选择代理模型方法并打开设置窗口。")
        return "\n".join(lines)
    lines.append(
        f"模型：{config.get('model')} ｜ 样本 {config.get('sample_count')} 点"
        f" ｜ 抽样方法 {config.get('doe_method')}")
    lines.append("")
    response_results = result.get("responses") or {}
    if not response_results:
        lines.append("尚未执行训练。填入响应数据后点击【执行后端分析并更新结果】。")
        return "\n".join(lines)
    for response_name, item in response_results.items():
        if item.get("error"):
            lines.append(f"响应 {response_name}：{item['error']}")
            continue
        lines.append(f"◆ 响应：{response_name}")
        lines.append(
            f"  测试集平均相对误差 {item.get('mape_test_%')}% ｜ "
            f"R² = {item.get('r2_test')} ｜ "
            f"训练样本 {item.get('train_samples')} / "
            f"测试样本 {item.get('test_samples')} ｜ "
            f"耗时 {item.get('train_time_s')}s")
        lines.append(f"  模型参数：{item.get('params') or {}}")
        lines.append("")
    return "\n".join(lines)
