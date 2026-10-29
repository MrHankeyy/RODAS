"""Extracted response models algorithms; preserve v0.1 calculations."""
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
from .factors import factor_limits


def _design_matrix(X):
    """二次模型设计阵：1 + 线性 + 平方 + 两两交互。"""
    if not HAS_NUMPY:
        raise RuntimeError("需要 numpy 支持回归计算")
    n, k = X.shape
    cols = [_np.ones(n)]
    labels = ["常数项"]
    for j in range(k):
        cols.append(X[:, j])
        labels.append(f"x{j + 1}")
        cols.append(X[:, j] ** 2)
        labels.append(f"x{j + 1}²")
    for i in range(k):
        for j in range(i + 1, k):
            cols.append(X[:, i] * X[:, j])
            labels.append(f"x{i + 1}·x{j + 1}")
    return _np.column_stack(cols), labels


def fit_response_surface(X, y):
    """最小二乘拟合二次响应面，返回系数、拟合优度与预测值。"""
    A, labels = _design_matrix(X)
    n, p = A.shape
    if _np.linalg.matrix_rank(A) < p:
        raise ValueError("试验数据不能识别完整二次模型")
    coef, *_ = _np.linalg.lstsq(A, y, rcond=None)
    y_hat = A @ coef
    ss_tot = float(_np.sum((y - y.mean()) ** 2)) or 1e-12
    ss_res = float(_np.sum((y - y_hat) ** 2))
    r2 = max(0.0, 1.0 - ss_res / ss_tot)
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / max(n - p, 1)
    rmse = math.sqrt(ss_res / max(n, 1))
    return {
        "coefficients": list(zip(labels, [round(float(c), 6) for c in coef])),
        "r2": round(r2, 6),
        "adj_r2": round(adj_r2, 6),
        "rmse": round(rmse, 6),
        "df_model": p - 1,
        "df_residual": n - p,
        "predicted": [float(v) for v in y_hat],
    }


def quadratic_optimum(fit_result, X_min, X_max, objective, target=None, samples=8000):
    """在可行域内随机采样搜索二次模型的优选点。objective: max/min/target。"""
    if not HAS_NUMPY:
        return None
    rng = _np.random.default_rng(2026)
    k = len(X_min)
    X = rng.uniform(0, 1, size=(samples, k)) * (_np.array(X_max) - _np.array(X_min)) + _np.array(X_min)
    A, _ = _design_matrix(X)
    pred = A @ _np.array([c for _, c in fit_result["coefficients"]])
    if objective == "max":
        idx = int(_np.argmax(pred))
    elif objective == "min":
        idx = int(_np.argmin(pred))
    else:
        t = float(target)
        idx = int(_np.argmin(_np.abs(pred - t)))
    return {
        "x": [round(float(v), 6) for v in X[idx]],
        "predicted": round(float(pred[idx]), 6),
    }


def screening_from_responses(factors, doe_matrix, response_name):
    """根据已填响应按 ± 编码计算主效应（中心点自动剔除）。"""
    lows, highs = {}, {}
    for f in factors:
        lo, hi = factor_limits(f)
        lows[f.name], highs[f.name] = lo, hi
    vals_by_sign = {f.name: {"+": [], "-": []} for f in factors}
    for row in doe_matrix:
        try:
            y = float(row.get(response_name, ""))
        except (TypeError, ValueError):
            continue
        for f in factors:
            try:
                v = float(row.get(f.name))
            except (TypeError, ValueError):
                continue
            mid = (lows[f.name] + highs[f.name]) / 2.0
            if abs(v - mid) < 1e-9:
                continue
            vals_by_sign[f.name]["-" if v < mid else "+"].append(y)
    effects = {}
    for f in factors:
        plus = vals_by_sign[f.name]["+"]
        minus = vals_by_sign[f.name]["-"]
        if plus and minus:
            effects[f.name] = statistics.mean(plus) - statistics.mean(minus)
    return effects


def _design_terms(k):
    """返回二次模型项与名称。"""
    terms = [("const", None, None)]
    names = ["常数"]
    for i in range(k):
        terms.append(("linear", i, None))
        names.append(f"x{i + 1}")
        terms.append(("quad", i, i))
        names.append(f"x{i + 1}²")
    for i in range(k):
        for j in range(i + 1, k):
            terms.append(("cross", i, j))
            names.append(f"x{i + 1}·x{j + 1}")
    return terms, names


def _design_row(z, terms):
    row = []
    for kind, i, j in terms:
        if kind == "const":
            row.append(1.0)
        elif kind == "linear":
            row.append(z[i])
        elif kind == "quad":
            row.append(z[i] ** 2)
        else:
            row.append(z[i] * z[j])
    return _np.array(row)


def _quad_hess_diag(terms, coef, z):
    """二次模型对角二阶导（对 z）。"""
    out = _np.zeros(len(z))
    for (kind, i, _j), c in zip(terms, coef):
        if kind == "quad":
            out[i] += 2.0 * c
    return out


def _quad_grad(terms, coef, z):
    """二次模型梯度（对 z）。"""
    g = _np.zeros(len(z))
    for (kind, i, j), c in zip(terms, coef):
        if kind == "linear":
            g[i] += c
        elif kind == "quad":
            g[i] += 2.0 * c * z[i]
        elif kind == "cross":
            g[i] += c * z[j]
            g[j] += c * z[i]
    return g


def _fit_model(X, y, full_quadratic=False):
    """拟合 X(输入，原始值) -> y，转为编码 z∈[-1,1] 的二次模型。返回模型 dict。"""
    if not HAS_NUMPY:
        raise RuntimeError("需要 numpy")
    X = _np.asarray(X, float)
    y = _np.asarray(y, float)
    n, k = X.shape
    lo = X.min(axis=0)
    hi = X.max(axis=0)
    span = (hi - lo) / 2.0
    span[span == 0] = 1.0
    center = (lo + hi) / 2.0
    Z = (X - center) / span
    # 两水平数据（±1）中 x² 与常数共线，仅当因子有≥3个不同值才保留平方项
    distinct = [_np.unique(X[:, j]).size for j in range(k)]
    terms = [("const", None, None)]
    names = ["常数"]
    for i in range(k):
        terms.append(("linear", i, None))
        names.append(f"x{i + 1}")
        if full_quadratic or distinct[i] >= 3:
            terms.append(("quad", i, i))
            names.append(f"x{i + 1}²")
    for i in range(k):
        for j in range(i + 1, k):
            terms.append(("cross", i, j))
            names.append(f"x{i + 1}·x{j + 1}")
    A = _np.column_stack([_design_row(z, terms) for z in Z]).T
    nterms = len(terms)
    if n < nterms and not full_quadratic:
        # 点数不足时降为线性模型
        keep = [i for i, (kind, *_r) in enumerate(terms) if kind in ("const", "linear")]
        terms = [terms[i] for i in keep]
        names = [names[i] for i in keep]
        A = A[:, keep]
        nterms = len(keep)
    rank = int(_np.linalg.matrix_rank(A))
    if rank < nterms:
        raise ValueError(f"模型矩阵秩不足（{rank}/{nterms}）；无法独立估计全部系数，请补充有效设计点。")
    coef, *_ = _np.linalg.lstsq(A, y, rcond=None)
    y_hat = A @ coef
    ss_tot = float(_np.sum((y - y.mean()) ** 2)) or 1e-12
    ss_res = float(_np.sum((y - y_hat) ** 2))
    df_model = nterms - 1
    df_resid = n - nterms
    r2 = max(0.0, 1.0 - ss_res / ss_tot)
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / max(n - nterms, 1)
    rmse = math.sqrt(ss_res / max(n, 1))
    residual = y - y_hat
    resid_std = math.sqrt(ss_res / max(df_resid, 1)) if df_resid > 0 else rmse
    return {
        "terms": terms, "names": names, "coef": coef,
        "full_quadratic": full_quadratic,
        "center": center, "half": span, "lo": lo, "hi": hi,
        "r2": round(r2, 6), "adj_r2": round(adj_r2, 6), "rmse": round(rmse, 6),
        "df_model": df_model, "df_residual": df_resid,
        "residual_std": resid_std, "residual": list(float(v) for v in residual),
        "predicted": list(float(v) for v in y_hat), "n": n, "k": k,
    }


def model_predict(model, x_raw):
    if not HAS_NUMPY:
        return None
    if "predict_fn" in model:
        return float(model["predict_fn"](_np.asarray(x_raw, float)))
    z = (_np.asarray(x_raw, float) - model["center"]) / model["half"]
    row = _design_row(z, model["terms"])
    return float(row @ model["coef"])


def model_grad_x(model, x_raw):
    """梯度 wrt 原始单位 x。"""
    if "grad_fn" in model:
        return _np.asarray(model["grad_fn"](_np.asarray(x_raw, float)), float)
    if "predict_fn" in model:
        x = _np.asarray(x_raw, float)
        step = float(model.get("finite_difference_step", 1e-4))
        grad = _np.zeros(len(x))
        for i in range(len(x)):
            delta = _np.zeros(len(x)); delta[i] = step
            grad[i] = (model["predict_fn"](x + delta)
                       - model["predict_fn"](x - delta)) / (2.0 * step)
        return grad
    z = (_np.asarray(x_raw, float) - model["center"]) / model["half"]
    gz = _quad_grad(model["terms"], model["coef"], z)
    return gz / model["half"]


def model_hess_diag_x(model, x_raw):
    if "hess_diag_fn" in model:
        return _np.asarray(model["hess_diag_fn"](_np.asarray(x_raw, float)), float)
    if "predict_fn" in model:
        x = _np.asarray(x_raw, float)
        step = float(model.get("finite_difference_step", 1e-4))
        center = model["predict_fn"](x)
        hess = _np.zeros(len(x))
        for i in range(len(x)):
            delta = _np.zeros(len(x)); delta[i] = step
            hess[i] = (model["predict_fn"](x + delta)
                       - 2.0 * center + model["predict_fn"](x - delta)) / step ** 2
        return hess
    z = (_np.asarray(x_raw, float) - model["center"]) / model["half"]
    hz = _quad_hess_diag(model["terms"], model["coef"], z)
    # 对 z 的二阶导转换：∂²f/∂x² = (1/h²)·∂²f/∂z²
    return hz / (model["half"] ** 2)


def model_equation(model):
    terms = model["terms"]
    labels = model["names"]
    coef = model["coef"]
    parts = []
    for t, label, c in zip(terms, labels, coef):
        parts.append((float(c), label))
    s = []
    for i, (c, label) in enumerate(parts):
        sign = "+" if c >= 0 else "-"
        mag = abs(c)
        body = f"{mag:.5g}·{label}" if label != "常数" else f"{mag:.5g}"
        s.append(f" {sign} {body}" if i else (f"{body}" if c >= 0 else f"-{body}"))
    return "y = " + "".join(s).strip()


def build_models(project):
    """训练每个响应的二次模型（输入为所有非固定因子）。返回 (context, errors)。"""
    matrix = project.doe_matrix or []
    if not matrix:
        return None, ["尚无 DOE 试验数据，请先在【方案配置】生成方案。"]
    is_rsm = "响应曲面" in project.design_method
    inputs = de.model_factors(project) if is_rsm else [f for f in project.factors if f.name and not f.is_fixed]
    names = [f.name for f in inputs]
    if not names:
        return None, ["没有可建模的输入因子。"]
    # 只使用矩阵中实际存在的输入列
    keys = set(matrix[0].keys())
    if is_rsm and any(n not in keys for n in names):
        return None, ["DOE 缺少设计因子列，不能删去因子后继续拟合。"]
    names = [n for n in names if n in keys]
    inputs = [f for f in inputs if f.name in names]
    if not names:
        return None, ["DOE 矩阵中未找到输入因子列。"]

    context = {"inputs": inputs, "names": names, "models": {},
               "errors": [], "_responses": project.responses,
               "_project": project}
    for resp in project.responses:
        if not resp.name:
            continue
        X, y = [], []
        for row in matrix:
            try:
                _ = [float(row[n]) for n in names]
            except (KeyError, TypeError, ValueError):
                continue
            try:
                yv = float(row.get(resp.name))
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in _ + [yv]):
                continue
            X.append([float(row[n]) for n in names])
            y.append(yv)
        if len(y) < 3:
            context["errors"].append(f"响应 {resp.name} 有效样本 {len(y)} < 3，跳过建模。")
            continue
        if is_rsm and len(y) != len(matrix):
            context["errors"].append(f"响应 {resp.name} 存在缺失/非有限数据，请补齐后拟合完整二次响应面。")
            continue
        try:
            context["models"][resp.name] = _fit_model(X, y, full_quadratic=is_rsm)
        except ValueError as exc:
            context["errors"].append(f"响应 {resp.name}：{exc}")
    if not context["models"]:
        return context, context["errors"] or ["没有足够的响应数据可建模。"]
    return context, context["errors"]
