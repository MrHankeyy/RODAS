"""Extracted design evaluation algorithms; preserve v0.1 calculations."""
from __future__ import annotations
import itertools
import math
import random
import statistics
import time
try:
    import numpy as _np
    HAS_NUMPY = True
except Exception:
    _np = None
    HAS_NUMPY = False
from . import factors as de
from .factors import _isfinite
from .response_models import model_grad_x, model_hess_diag_x, model_predict


def _sigma_of_factor(f, k_design):
    """因子不确定性标准差。"""
    lo, hi = de.factor_limits(f)
    if f.uncertainty == "概率":
        try:
            return max(0.0, float(f.param2)) ** 0.5
        except (TypeError, ValueError):
            return (hi - lo) / 6.0
    if f.source == "环境" or f.nominal_lower != "":
        # Existing moment approximation: actual environmental width or design deviation width.
        return (float(f.param2) - float(f.param1)) / (2.0 * max(1.0, k_design))
    # For actual environmental intervals (and legacy design ranges), half-width = k·σ.
    return (hi - lo) / (2.0 * max(1.0, k_design))


def robust_moments(model, x_design, context, k_design, include_residual=True):
    """在设计点 x_design(设计因子名->值) 处计算任一响应的均值 μ 与标准差 σ。"""
    inputs = context["inputs"]
    names = context["names"]
    x = [de.factor_center(f, x_design if f.source == "设计" else None) for f in inputs]
    x = _np.array(x, float)
    mu = model_predict(model, x)
    grad = model_grad_x(model, x)
    hess = model_hess_diag_x(model, x)
    sigma = []
    for f, idx in zip(inputs, range(len(inputs))):
        sigma.append(_sigma_of_factor(f, k_design))
    sigma = _np.array(sigma, float)
    # 一阶 + 二阶矩修正
    curvature = 0.5 * float(_np.sum((hess * sigma ** 2)))
    mu_mean = mu + curvature
    var1 = float(_np.sum((grad * sigma) ** 2))
    var2 = float(_np.sum(0.5 * ((hess * sigma ** 2) ** 2)))
    var_res = model["residual_std"] ** 2 if include_residual else 0.0
    sigma_out = math.sqrt(var1 + var2 + var_res)
    return mu_mean, sigma_out


def _response_ref(resp):
    """返回响应参考界限 (上限/目标)。"""
    if resp.feature == "望目":
        try:
            return float(resp.lower), float(resp.upper)
        except (TypeError, ValueError):
            return None, None
    try:
        return float(resp.robust_limit)
    except (TypeError, ValueError):
        return None


def _desirability(resp, mu, data_min, data_max):
    """期望值转换为 0~1 的望性值 d（越大越好）。"""
    if resp.feature == "望大":
        ref = _response_ref(resp)
        lo = ref if ref is not None else min(data_min, mu)
        hi = max(data_max, ref if ref is not None else mu)
        if hi <= lo:
            hi = lo + 1.0
        return max(0.0, min(1.0, (mu - lo) / (hi - lo)))
    if resp.feature == "望小":
        ref = _response_ref(resp)
        hi = ref if ref is not None else max(data_max, mu)
        lo = min(data_min, ref if ref is not None else mu)
        if hi <= lo:
            hi = lo + 1.0
        return max(0.0, min(1.0, (hi - mu) / (hi - lo)))
    ref = _response_ref(resp)
    if not isinstance(ref, tuple) or len(ref) != 2:
        return 0.5
    lo, hi = ref
    if lo is None or hi is None:
        return 0.5
    target = (lo + hi) / 2.0
    tol = (hi - lo) / 2.0
    if tol <= 0:
        tol = 1.0
    return max(0.0, 1.0 - abs(mu - target) / tol)


def _constraint_limits(resp):
    """约束型响应的界限信息：(类型, 界限)。"""
    if resp.feature == "望小":
        ref = _response_ref(resp)
        return ("upper", ref) if ref is not None else ("upper", None)
    if resp.feature == "望大":
        ref = _response_ref(resp)
        return ("lower", ref) if ref is not None else ("lower", None)
    ref = _response_ref(resp)
    if not isinstance(ref, tuple) or len(ref) != 2:
        return ("both", (None, None))
    lo, hi = ref
    return ("both", (lo, hi)) if lo is not None and hi is not None else ("both", (None, None))


def _response_scale(model):
    """按响应数据幅度归一化，不让拟合精度改变优化目标的权重。"""
    values = [float(v) for v in model.get("predicted", []) if _isfinite(v)]
    if not values:
        return 1.0
    span = max(values) - min(values)
    return span if span > 1e-12 else max(max(abs(v) for v in values), 1.0)


def evaluate_design(context, x_design, k_design, weight_r, use_constraints=False,
                    k_constraint=6.0, resp_stds=None):
    """设计点评估。返回 dict{obj, mean_perf, std_norm, infeas, details}。"""
    models = context["models"]
    resp_objs, resp_cons, details = [], [], []
    data_min, data_max = {}, {}
    for name, m in models.items():
        data_min[name] = float(_np.min(m["predicted"])) if m["predicted"] else 0.0
        data_max[name] = float(_np.max(m["predicted"])) if m["predicted"] else 1.0
    std_sum, perf_sum, wsum = 0.0, 0.0, 0.0
    infeas = 0.0
    sigma_limits = context.get("sigma_limits", {})
    for resp in project_responses(context):
        m = models.get(resp.name)
        if m is None:
            continue
        mu, sigma = robust_moments(m, x_design, context, k_design)
        if resp.name in sigma_limits:
            bound = sigma_limits[resp.name]
            infeas += max(0.0, sigma - bound) / max(abs(bound), 1e-12)
            details.append({"name": resp.name, "sigma": sigma, "sigma_limit": bound, "margin": bound - sigma})
        d = _desirability(resp, mu, data_min[resp.name], data_max[resp.name])
        scale = _response_scale(m)
        std_n = sigma / max(scale, 1e-12)
        # 是否约束
        is_cons = self_is_constraint(resp)
        if is_cons:
            kind, lim = _constraint_limits(resp)
            if use_constraints and (lim is None or
                                    (kind == "both" and None in lim)):
                raise ValueError(f"约束响应 {resp.name} 未设置有效的约束界限。")
            if kind == "upper" and lim is not None:
                infeas_in = max(0.0, mu + k_constraint * sigma - lim)
            elif kind == "lower" and lim is not None:
                infeas_in = max(0.0, lim - (mu - k_constraint * sigma))
            elif kind == "both":
                lo, hi = lim
                infeas_in = 0.0
                if lo is not None:
                    infeas_in += max(0.0, lo - (mu - k_constraint * sigma))
                if hi is not None:
                    infeas_in += max(0.0, (mu + k_constraint * sigma) - hi)
            else:
                infeas_in = 0.0
            limit_scale = abs(lim if isinstance(lim, (int, float))
                              else ((lim[1] or 0.0) if lim else 0.0))
            if use_constraints:
                infeas += infeas_in / max(limit_scale, 1.0)
            resp_cons.append({"name": resp.name, "mu": mu, "sigma": sigma, "d": d})
        if not is_cons or "目标" in resp.kind:
            resp_objs.append({"name": resp.name, "mu": mu, "sigma": sigma, "d": d})
            perf_sum += d
            std_sum += std_n
            wsum += 1.0
    if not resp_objs:
        # 全为约束时，用第一个响应的 σ 作为目标并保持可行
        perf_sum = 1.0
        std_sum = sum(c["sigma"] / max(_response_scale(models[c["name"]]), 1e-12) for c in resp_cons) if resp_cons else 0.0
        wsum = len(resp_cons) or 1
    mean_perf = perf_sum / max(wsum, 1)
    std_norm = std_sum / max(wsum, 1)
    # 目标（最小化）
    obj = [1.0 - mean_perf, std_norm]
    if infeas > 0:
        obj = [v + 100.0 * infeas for v in obj]
    return {"obj": obj, "mean_perf": mean_perf, "std_norm": std_norm,
            "infeas": infeas, "objectives": resp_objs, "constraints": resp_cons,
            "details": details, "x": dict(x_design)}


def project_responses(context):
    return context["_responses"]


def self_is_constraint(resp):
    # 稳定性阈值属于目标的望性参考，只有用户明确勾选“约束响应”
    # 时才把该响应从目标集合移入约束集合。
    return "约束" in getattr(resp, "kind", "")


def design_inputs(context):
    return [f for f in context["inputs"] if f.source == "设计"]
