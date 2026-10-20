"""DOE workflow without Qt dependencies."""
from dataclasses import dataclass, field
from copy import deepcopy
import math
import random

from backend.core import doe, factors as factor_tools, sampling
from backend.services.project_service import ProjectService


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
                       "top_n": top_n, "seed": seed, "randomize": randomize},
        initial_results={"screening_result": result}, surrogate_config={})


def response_surface_plan(project, method, rsm_type, alpha_mode, alpha,
                          centers, replicates, seed, randomize):
    return model_plan(project, method, dict(model="RSM", doe_method=rsm_type,
        alpha_mode=alpha_mode, alpha=alpha, centers=centers,
        replicates=replicates, seed=seed, randomize=randomize))


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
                       "levels": levels, "seed": seed, "randomize": randomize},
        groups=groups, initial_results={"taguchi_result": result}, surrogate_config={})


def surrogate_plan(project, method, config, seed):
    if not config:
        raise ValueError("请先在【方案配置】填写模型与试验设计参数。")
    expected = ("Kriging" if "Kriging" in method else
                "SVR" if "SVR" in method else "ANN")
    if config.get("model") != expected:
        raise ValueError(
            f"当前设置属于 {config.get('model')}，与所选 {expected} 不一致。")
    return model_plan(project, method, {**config, "seed": seed})


SAMPLING_METHODS = (
    "Latin Hypercube (LHS)", "最优 LHS", "低差异序列 SOBOL",
    "均匀网格抽样", "稀疏配点法", "随机抽样",
)
MODEL_DESIGNS = {"RSM": ("CCD", "BBD"),
                 **{model: SAMPLING_METHODS for model in ("Kriging", "SVR", "ANN")}}


def model_plan(project, method, config, preview=False):
    """Generate the original DOE choices supported by the selected model."""
    config = deepcopy(config)
    factors = [f for f in _design_factors(project) if f[3] is None]
    _require_design_factors(factors)
    model = config["model"]
    if model not in MODEL_DESIGNS:
        raise ValueError("未知模型类型")
    selected = []
    for name, low, high, fixed in factors:
        low, high = map(float, config.get("bounds", {}).get(name, (low, high)))
        if not all(map(math.isfinite, (low, high))) or high <= low:
            raise ValueError(f"因子 {name} 的试验范围无效；上限须大于下限且均为有限数。")
        selected.append((name, low, high, fixed))
    config["bounds"] = {name: [low, high] for name, low, high, _ in selected}
    seed = int(config.get("seed", 123))
    replicates = int(config.get("replicates", 1))
    if replicates < 1:
        raise ValueError("整表重复次数至少为 1")
    design = config.get("doe_method", MODEL_DESIGNS[model][0])
    if design not in MODEL_DESIGNS[model]:
        raise ValueError(f"{model} 仅支持以下试验设计：{'、'.join(MODEL_DESIGNS[model])}")
    randomize = config.get("randomize", True)
    if design in ("CCD", "BBD"):
        rows, meta = doe.build_response_surface(selected, design,
            config.get("alpha_mode", "face"), config.get("alpha", 1),
            centers=int(config.get("centers", 3)), replicates=replicates,
            seed=seed, randomize=randomize)
    else:
        if design not in SAMPLING_METHODS:
            raise ValueError("未知试验设计方法")
        count = int(config.get("sample_count", 50))
        if not 1 <= count <= 20000:
            raise ValueError("样本点数须在 1～20000 之间")
        actual = count
        if design == "均匀网格抽样" and (len(selected) > 4 or count < 2**len(selected)):
            raise ValueError("均匀网格支持最多 4 个因子，且基础样本点数至少为 2^因子数；请调整点数或选择其他采样方法。")
        if design == "均匀网格抽样" and len(selected) <= 4 and count >= 2**len(selected):
            actual = min(count, max(2, round(count**(1/len(selected))))**len(selected))
        rows = [] if preview else sampling.build_samples(selected, count, design, seed)
        if not preview:
            rows = [dict(row) for _ in range(replicates) for row in rows]
            if randomize:
                random.Random(seed).shuffle(rows)
            else:
                rows.sort(key=lambda row: tuple(row[name] for name, *_ in selected))
        meta = dict(design=design, total_runs=actual * replicates,
                    replicates=replicates, active_factors=[f[0] for f in selected])
    if not preview:
        _validate_model_design(model, rows, selected, config)
    params = dict(meta=meta, model_config=config, doe_method=design,
                  sample_count=len(rows) if not preview else meta["total_runs"])
    initial = {"rsm_result": {"design": meta, "fit": None}} if model == "RSM" else {}
    return DesignPlan(method, rows, params, initial_results=initial,
                      surrogate_config={} if model == "RSM" else config)


def _validate_model_design(model, rows, factors, config):
    import numpy as np
    from backend.core.response_models import _design_matrix
    low = np.array([f[1] for f in factors])
    high = np.array([f[2] for f in factors])
    points = np.array([[row[f[0]] for f in factors] for row in rows])
    coded = (points - (low + high)/2) / ((high - low)/2)
    if model == "RSM":
        matrix, _ = _design_matrix(coded)
        rank = np.linalg.matrix_rank(matrix)
        if rank < matrix.shape[1]:
            raise ValueError(f"当前设计不能识别完整二次模型（矩阵秩 {rank}/{matrix.shape[1]}）；请增加有效设计点或更换试验设计。")
    elif len(rows) < 6:
        raise ValueError("代理模型至少需要 6 个样本，才能进行训练与留出集评估。")
    elif model == "Kriging":
        trend = config.get("model_params", {}).get("trend", "常数（Ordinary）")
        train = np.random.default_rng(2026).permutation(len(rows))[max(1, round(len(rows)*.2)):]
        matrix = (_design_matrix(coded[train])[0] if "二次" in trend else
                  np.column_stack([np.ones(len(train)), coded[train]]) if "一次" in trend else np.ones((len(train), 1)))
        if np.linalg.matrix_rank(matrix) < matrix.shape[1]:
            raise ValueError("当前设计的训练子集无法识别 Kriging 趋势项；请增加样本或降低趋势阶次。")


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
