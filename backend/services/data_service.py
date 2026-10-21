"""Method-independent inspection of saved observations; never fits a model."""
import math


def data_overview(project):
    method = project.design_method or ""
    meta = project.design_params.get("meta", {}) or {}
    design = project.surrogate_config.get("doe_method", "—")
    if "筛选" in method:
        design = meta.get("kind", "两水平筛选")
    elif "田口" in method:
        design = f"内表 {meta.get('inner_label', '—')} × 外表 {meta.get('outer_label', '—')}"
    elif "响应曲面" in method:
        design = meta.get("design", "响应曲面")
    total = len(project.doe_matrix)
    readiness, issues = [], []
    for response in project.responses:
        if not response.name:
            continue
        count = 0
        for index, row in enumerate(project.doe_matrix, 1):
            value = row.get(response.name)
            try:
                valid = math.isfinite(float(value))
            except (ValueError, TypeError, OverflowError):
                valid = False
            if valid:
                count += 1
            else:
                reason = "缺失" if value is None or not str(value).strip() else "非有限数值或非数字"
                issues.append({"数据行": index, "响应": response.name, "问题": reason})
        readiness.append((response.name, count, total))
    return dict(information=[("当前方法", method or "未选择"), ("试验次数", f"{total} 次"),
                             ("设计 / 采样方式", design)],
                readiness=readiness, issues=issues,
                ready=bool(total and readiness) and all(n == total for _, n, _ in readiness))
