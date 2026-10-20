"""Present existing analysis results as reusable overview sections (no computation)."""
import math


def display(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        if math.isnan(value):
            return "—"
        if math.isinf(value):
            return "+∞" if value > 0 else "−∞"
        return f"{value:.5g}"
    return str(value)


def named(item):
    return f"{item.name}（{item.unit}）" if item.unit else item.name


def details(mapping, prefix=""):
    """Flatten small parameter dictionaries for a shared key/value details view."""
    rows = []
    for key, value in mapping.items():
        if key == "groups":
            continue
        label = f"{prefix} / {key}" if prefix else str(key)
        if isinstance(value, dict):
            rows.extend(details(value, label))
        else:
            rows.append((label, display(value)))
    return rows


def section(title, headers=(), rows=(), message=""):
    return dict(title=title, headers=headers, rows=rows, message=message)


def _model_results(project, labels):
    surrogate = "代理模型" in project.design_method
    result = project.surrogate_result if surrogate else project.rsm_result
    items = result.get("responses" if surrogate else "fit", {})
    rows, errors, extra = [], [], []
    for name, item in items.items():
        if item.get("error"):
            errors.append(section(f"{labels.get(name, name)} · 分析失败", message=item["error"]))
            continue
        if surrogate:
            rows.append([labels.get(name, name), item.get("r2_test"), item.get("mape_test_%")])
            extra += [(f"{name} / 训练与测试样本", f"{item.get('train_samples')} / {item.get('test_samples')}"),
                      (f"{name} / 训练耗时（s）", display(item.get("train_time_s")))]
            extra += details(item.get("params", {}), f"{name} / 模型参数")
        else:
            rows.append([labels.get(name, name), item.get("r2"), item.get("adj_r2"), item.get("rmse")])
            extra += [(f"{name} / 模型与残差自由度", f"{item.get('df_model')} / {item.get('df_residual')}")]
    title = "模型训练结果" if surrogate else "二次响应面拟合结果"
    headers = ["响应", "测试集 R²", "相对误差指标（%）"] if surrogate else ["响应", "拟合 R²", "调整 R²", "拟合 RMSE"]
    note = ("下一步：在「交叉验证与残差」检查预测误差，再进行鲁棒优化。" if surrogate else
            "RMSE 单位同响应。下一步：检查「显著性 / LOF」与「交叉验证与残差」，再进行鲁棒优化。")
    if surrogate:
        extra.append(("相对误差指标口径", "测试集平均绝对误差 / 测试集响应绝对值均值 × 100%"))
    sections = [section(title, headers, rows, note)] if rows else []
    return sections + errors, extra, len(rows), len(errors)


def _screening_results(project, labels):
    result = project.screening_result
    sections, extra = [], []
    for name, item in result.get("response_analysis", {}).items():
        effects = item.get("effects", [])[:project.design_params.get("top_n", 5)]
        sections.append(section(f"重点主效应 · {labels.get(name, name)}",
            ["因子", "高−低效应", "主效应平方占比（%）"],
            [[e["name"], e["effect"], e["share"]] for e in effects],
            "效应单位同响应。下一步：在「筛选主效应」查看完整效应与设计诊断，再决定后续研究因子。"))
        extra += [(f"{name} / 效应口径", "高水平平均响应 − 低水平平均响应；平方占比不等于总方差贡献或统计显著性。"),
                  (f"{name} / 纯误差说明", item.get("note", ""))]
    errors = result.get("errors", {})
    count = len(sections)
    sections += [section(f"{name} · 分析失败", message=message) for name, message in errors.items()]
    extra += [("设计诊断", result.get("diagnostic_summary", ""))]
    return sections, extra, count, len(errors)


def _taguchi_results(project, labels):
    result = project.taguchi_result
    sections, extra = [], []
    units = {f.name: named(f) for f in project.factors}
    for name, item in result.get("response_analysis", {}).items():
        best = item.get("best_levels", {})
        if best:
            sections.append(section(f"候选水平组合 · {labels.get(name, name)}", ["控制因子", "候选水平"],
                [[units.get(factor, factor), level] for factor, level in best.items()],
                "候选组合基于水平主效应，需要确认试验；不同响应的推荐分别显示。"))
        matched = [run for run in item.get("runs", []) if best and run["settings"] == best]
        metric = "S/N（dB）" if item.get("has_replication") else "均值指标"
        if matched:
            rows = [[run["mean"], run["std"], run["metric"]] for run in matched]
            sections.append(section(f"候选组合的已试验统计 · {labels.get(name, name)}",
                ["均值", "标准差", metric], rows, "均值与标准差单位同响应。"))
        else:
            sections.append(section(f"试验组统计 · {labels.get(name, name)}",
                ["内表组", "均值", "标准差", metric],
                [[r["inner"], r["mean"], r["std"], r["metric"]] for r in item.get("runs", [])],
                "候选组合尚未试验，表中列出已有试验组。" if best else "约束响应仅描述观测结果，不推荐最优水平。"))
        extra += [(f"{name} / 信噪比类型", item.get("feature", "")),
                  (f"{name} / 分析说明", item.get("note", ""))]
        if not item.get("has_replication"):
            sections[-1]["message"] += " 没有外表或重复观测，仅作均值分析，不能评估稳健性。"
    errors = result.get("errors", {})
    sections += [section(f"{name} · 分析失败", message=message) for name, message in errors.items()]
    extra.append(("水平推荐说明", result.get("recommendation", "")))
    return sections, extra, len(result.get("response_analysis", {})), len(errors)


def overview(project):
    """Return method-independent information, readiness, sections and details."""
    method = project.design_method or ""
    meta = project.design_params.get("meta", {}) or {}
    config = project.surrogate_config or {}
    responses = [r for r in project.responses if r.name]
    labels = {r.name: named(r) for r in responses}
    total = len(project.doe_matrix)
    readiness = []
    for response in responses:
        count = 0
        for row in project.doe_matrix:
            try:
                count += math.isfinite(float(row.get(response.name)))
            except (ValueError, TypeError, OverflowError):
                pass
        readiness.append((labels[response.name], count, total))
    ready = bool(total and responses) and all(n == total for _, n, _ in readiness)
    design = config.get("doe_method", "—")
    render = _model_results
    if "筛选" in method:
        design, render = meta.get("kind", "两水平筛选"), _screening_results
    elif "田口" in method:
        design, render = f"内表 {meta.get('inner_label', '—')} × 外表 {meta.get('outer_label', '—')}", _taguchi_results
    elif "响应曲面" in method:
        design = meta.get("design", "响应曲面")
    sections, extra, successes, errors = render(project, labels) if method else ([], [], 0, 0)
    if not method:
        status, next_step = "尚未生成方案", "下一步：到「方案配置」生成试验方案。"
    elif not ready:
        status, next_step = "等待响应数据", "下一步：到「数据管理」填入或导入完整的有效响应数据。"
    elif errors:
        status, next_step = "部分响应分析失败" if successes else "分析失败", "请查看下方各响应的具体原因。"
    elif successes:
        status, next_step = "分析已完成", "当前数据与分析结果已就绪。"
    else:
        action = "计算筛选主效应" if "筛选" in method else "计算田口信噪比" if "田口" in method else "仅建模与统计分析"
        status, next_step = "等待分析", f"下一步：使用页面上方「{action}」。"
    if not sections:
        sections = [section("分析结果", message="尚未执行分析。" if ready else "响应数据就绪后显示当前方案的分析结果。")]
    return dict(information=[("当前方法", method or "未选择"), ("试验次数", f"{total} 次"),
                             ("设计 / 采样方式", design)], readiness=readiness, status=status,
                next_step=next_step, sections=sections, details=extra + details(meta))
