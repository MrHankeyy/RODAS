"""DOE workflow without Qt dependencies."""
from dataclasses import dataclass, field

from rams.core import doe, factors as factor_tools, sampling
from rams.services.project_service import ProjectService


@dataclass
class DesignPlan:
    method: str
    rows: list
    params: dict
    groups: list | None = None
    initial_results: dict = field(default_factory=dict)
    surrogate_config: dict | None = None


def _design_factors(project):
    return factor_tools.simple_factors(
        [item for item in project.factors if item.source != "环境"])


def _noise_factors(project):
    return factor_tools.simple_factors(
        [item for item in project.factors if item.source == "环境"])


def screening_plan(project, method, kind, seed, centers, replicates,
                   randomize, top_n):
    factors = _design_factors(project)
    _require_design_factors(factors)
    rows, meta = doe.build_screening(
        factors, kind, seed=seed, centers=centers, replicates=replicates,
        randomize=randomize)
    result = {
        "factor_rankings": [], "main_effects": [], "plot_points": [],
        "stability_impact": [], "response_effects": {},
        "response_analysis": {},
        "diagnostic_summary":
            f"{meta['kind']}，{meta['total_runs']} 次试验。{meta['diagnostic']}",
        "conclusion": "方案已生成，尚无响应数据；不生成先验因子排名。",
        "analysis_status": "等待响应数据",
    }
    return DesignPlan(
        method, rows, {"doe_family": meta["kind"], "meta": meta,
                       "top_n": top_n},
        initial_results={"screening_result": result})


def response_surface_plan(project, method, rsm_type, alpha_mode, alpha,
                          centers, replicates, seed, randomize):
    factors = _design_factors(project)
    _require_design_factors(factors)
    rows, meta = doe.build_response_surface(
        factors, rsm_type, alpha_mode, alpha, centers=centers,
        replicates=replicates, seed=seed, randomize=randomize)
    result = {
        "design": meta,
        "fit": None,
        "message": ("试验设计已生成；在【数据管理】填入响应后，"
                    "可到【设计优化】拟合响应曲面。"),
    }
    return DesignPlan(
        method, rows, {"meta": meta},
        initial_results={"rsm_result": result})


def taguchi_plan(project, method, inner, outer, levels, seed, replicates,
                 randomize, snr_mode):
    control = _design_factors(project)
    noise = _noise_factors(project)
    _require_design_factors(control)
    if noise and outer == "无":
        raise ValueError(
            "当前存在环境（噪声）因子，田口外表不能为“无”；"
            "请选择外表正交表，或先在【业务建模】中移除环境因子。")
    rows, meta = doe.build_taguchi(
        control, noise, inner, outer, levels, seed=seed,
        replicates=replicates, randomize=randomize)
    groups = meta.get("groups") or []
    result = {
        **meta,
        "array_name": meta["inner_label"],
        "outer_label": meta["outer_label"],
        "inner_runs": meta["inner_runs"],
        "outer_runs": meta["outer_runs"],
        "has_outer": meta["has_outer"],
        "levels": meta["levels"],
        "factor_levels": meta["factor_levels"],
        "noise_levels": meta.get("noise_levels", {}),
        "orthogonal_array": [],
        "signal_to_noise": [],
        "best_levels": {},
        "groups": groups,
        "recommendation": (
            "内表×外表叉积试验已完成安排。在【数据管理】填入各次试验响应后，"
            "可到【设计优化】计算均值响应表、S/N 表并给出待确认的候选水平组合。"),
        "summary": (
            f"已按内表 {meta['inner_label']}（{meta['inner_runs']} 组）×"
            f"外表 {meta['outer_label']}（{meta['outer_runs']} 组）生成"
            f" {meta['total_runs']} 次叉积试验。"),
    }
    return DesignPlan(
        method, rows, {"meta": meta, "snr_mode": snr_mode,
                       "levels": levels},
        groups=groups, initial_results={"taguchi_result": result})


def surrogate_plan(project, method, config, seed):
    factors = _design_factors(project)
    _require_design_factors(factors)
    if not config:
        raise ValueError("尚未设置代理模型参数，请先点击【打开建模设置窗口…】。")
    expected = ("Kriging" if "Kriging" in method else
                "SVR" if "SVR" in method else "ANN")
    if config.get("model") != expected:
        raise ValueError(
            f"当前窗口中的设置属于 {config.get('model')}，"
            f"与所选 {expected} 不一致，请重新打开对应模型的设置窗口。")
    bounds = config.get("bounds") or {}
    sample_factors = []
    for name, low, high, fixed in factors:
        selected_low, selected_high = bounds.get(name, [low, high])
        sample_factors.append((name, selected_low, selected_high, fixed))
    rows = sampling.build_samples(
        sample_factors, config["sample_count"], config["doe_method"],
        seed=seed)
    params = {
        "surrogate_config": config,
        "sample_count": config["sample_count"],
        "doe_method": config["doe_method"],
    }
    return DesignPlan(
        method, rows, params, surrogate_config=config)


def commit_plan(project, plan):
    matrix = materialize_matrix(project, plan.rows, plan.groups)
    ProjectService.for_project(project).commit_design(
        method=plan.method,
        params=plan.params,
        matrix=matrix,
        initial_results=plan.initial_results,
        surrogate_config=plan.surrogate_config)
    return matrix


def materialize_matrix(project, rows, groups=None):
    responses = [item.name for item in project.responses if item.name]
    factor_names = [item.name for item in project.factors if item.name]
    names = factor_names + responses
    reserved = {"Run_ID", "内表组号", "外表组号", "重复组号"}
    if len(set(names)) != len(names) or set(names) & reserved:
        raise ValueError(
            "因子和响应名称必须互不重复，且不能使用试验编号/组号等保留列名")
    matrix = []
    for index, row in enumerate(rows):
        record = {"Run_ID": index + 1, **row}
        for factor in project.factors:
            if factor.name and factor.is_fixed:
                try:
                    record[factor.name] = float(factor.fixed_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"固定因子 {factor.name} 缺少有效固定值") from exc
        if groups is not None:
            record["内表组号"] = groups[index]["inner"] + 1
            if groups[index]["outer"] is not None:
                record["外表组号"] = groups[index]["outer"] + 1
            record["重复组号"] = groups[index].get("replicate", 0) + 1
        for name in responses:
            record[name] = ""
        matrix.append(record)
    return matrix


def _require_design_factors(factors):
    if not factors:
        raise ValueError(
            "未发现设计因子，无法生成方案。请先在【业务建模】添加设计因子。")
