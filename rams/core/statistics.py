"""Extracted statistics algorithms; preserve v0.1 calculations."""
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
from .design_evaluation import _sigma_of_factor, design_inputs, evaluate_design
from .factors import _isfinite
from .response_models import _fit_model, model_grad_x, model_hess_diag_x, model_predict


def _gammaln(x):
    return math.lgamma(x)


def _betacf(a, b, x):
    MAXIT = 200
    EPS = 3.0e-12
    FPMIN = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(_gammaln(a + b) - _gammaln(a) - _gammaln(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _f_pvalue(F, df1, df2):
    x = df2 / (df2 + df1 * F)
    return _betai(df2 / 2.0, df1 / 2.0, x)


def describe_data(project):
    matrix = project.doe_matrix or []
    if not matrix:
        return "尚无试验数据。"
    lines = ["【整体数据分析】"]
    n = len(matrix)
    for resp in project.responses:
        if not resp.name:
            continue
        vals = []
        for row in matrix:
            try:
                if _isfinite(row.get(resp.name)):
                    vals.append(float(row[resp.name]))
            except (TypeError, ValueError):
                continue
        if not vals:
            lines.append(f"  {resp.name}: 无有效数据")
            continue
        vals.sort()
        mean = statistics.mean(vals)
        std = statistics.stdev(vals) if len(vals)>1 else float("nan")
        lines.append(f"  响应 {resp.name}: n={len(vals)}/{n} 均值={mean:.4g} "
                     f"样本标准差={std:.4g} 最小={vals[0]:.4g} 最大={vals[-1]:.4g} "
                     f"极差={vals[-1] - vals[0]:.4g}")
    return "\n".join(lines)


def level_stats(project):
    matrix = project.doe_matrix or []
    factors = [f for f in project.factors if f.name and not (f.is_fixed and f.fixed_value not in (None, ""))]
    headers = ["因子", "水平", "响应", "均值", "方差", "极差", "样本数", "F比", "p值"]
    rows = []
    if not matrix:
        return {"headers": headers, "rows": rows}
    for f in factors:
        if f.name not in matrix[0]:
            continue
        level_values = sorted({float(row[f.name]) for row in matrix if _isfinite(row.get(f.name))})
        for resp in project.responses:
            if not resp.name:
                continue
            groups = []
            for lv in level_values:
                vals = []
                for row in matrix:
                    try:
                        if abs(float(row[f.name]) - lv) < 1e-9:
                            vals.append(float(row.get(resp.name)))
                    except (TypeError, ValueError):
                        continue
                groups.append((lv, [v for v in vals if _isfinite(v)]))
            groups = [(lv, v) for lv, v in groups if v]
            if not groups:
                continue
            grand = [x for _lv, v in groups for x in v]
            g = len(groups)
            n = len(grand)
            grand_mean = statistics.mean(grand)
            ss_between = sum(len(v) * (statistics.mean(v) - grand_mean) ** 2 for _lv, v in groups)
            ss_within = sum(sum((x - statistics.mean(v)) ** 2 for x in v) for _lv, v in groups)
            df_b = g - 1
            df_w = n - g
            fstat = (ss_between / df_b) / (ss_within / df_w) if ss_within > 0 and df_w > 0 and df_b > 0 else float("nan")
            p = _f_pvalue(fstat, df_b, df_w) if math.isfinite(fstat) else float("nan")
            for lv, v in groups:
                mean = statistics.mean(v)
                var = statistics.variance(v) if len(v) > 1 else float("nan")
                rng = max(v) - min(v)
                rows.append({
                    "factor": f.name, "level": lv, "response": resp.name,
                    "mean": mean, "var": var, "range": rng, "n": len(v),
                    "F": fstat, "p": p,
                })
    return {"headers": headers, "rows": rows}


def anova_and_lof(context, project):
    if not context or not context["models"]:
        return "无模型可分析，请先填入响应数据。"
    matrix = project.doe_matrix or []
    names = context["names"]
    lines = ["【回归方差分析 / 显著性 / 失拟(LOF)】"]
    for resp_name, m in context["models"].items():
        if "predict_fn" in m:
            lines.append(f"◆ 响应 {resp_name}：代理模型不适用多项式回归 ANOVA/LOF；请查看留出集验证与残差。")
            continue
        n = m["n"]
        # 从残差计算
        y = [float(row[resp_name]) for row in matrix if row.get(resp_name) not in (None, "") and all(_isfinite(row[c]) for c in names)]
        if len(y) != n:
            continue
        y_mean = statistics.mean(y)
        ss_tot = sum((v - y_mean) ** 2 for v in y)
        ss_res = sum((v - p) ** 2 for v, p in zip(y, m["predicted"]))
        ss_reg = ss_tot - ss_res
        df_reg = m["df_model"]
        df_res = m["df_residual"]
        ms_reg = ss_reg / max(df_reg, 1)
        ms_res = ss_res / max(df_res, 1)
        fstat = ms_reg / ms_res if ms_res > 0 else 0.0
        p = _f_pvalue(fstat, df_reg, df_res)
        lines.append(f"◆ 响应 {resp_name}")
        lines.append(f"  回归：F={fstat:.4g}，df=({df_reg},{df_res})，p={p:.4g}，"
                     f"R²={m['r2']}，调整R²={m['adj_r2']}，RMSE={m['rmse']}")
        if df_res <= 0 or ms_res <= 1e-24:
            lines[-1] = f"  回归：R²={m['r2']}，RMSE={m['rmse']}；残差自由度不足或误差为零，F/p 不可估计。"
        # 失拟：从重复设计点估计纯误差
        pure_ss, pure_df = 0, 0
        point_groups = {}
        for row in matrix:
            try:
                pt = tuple(row.get(c) for c in names)
                yv = float(row.get(resp_name))
            except (TypeError, ValueError):
                continue
            if not all(_isfinite(v) for v in pt):
                continue
            point_groups.setdefault(pt, []).append(yv)
        for pt, vals in point_groups.items():
            if len(vals) > 1:
                gm = statistics.mean(vals)
                pure_ss += sum((v - gm) ** 2 for v in vals)
                pure_df += len(vals) - 1
        if pure_df > 0 and df_res > pure_df:
            lof_df = df_res - pure_df
            lof_ss = max(ss_res - pure_ss, 0.0)
            ms_pe = pure_ss / pure_df
            ms_lof = lof_ss / lof_df
            if ms_pe <= 1e-24:
                lines.append("  失拟(LOF)：重复点纯误差为零，F/p 不可估计；不能据此判定模型充分。")
                continue
            lof_f = ms_lof / ms_pe
            lof_p = _f_pvalue(lof_f, lof_df, pure_df)
            lines.append(f"  失拟(LOF)：SS_Lof={lof_ss:.4g}，SS_PE={pure_ss:.4g}，"
                         f"F_Lof={lof_f:.4g}，p={lof_p:.4g}，df=({lof_df},{pure_df})")
            lines.append("  判定：" + ("未检出显著失拟，不等于证明模型充分。" if lof_p > 0.05
                                      else "模型存在失拟，建议改进模型结构或补点。"))
        else:
            lines.append("  失拟(LOF)：无重复点/中心点，无法估计纯误差，跳过 LOF。")
        lines.append("")
    return "\n".join(lines)


def cross_validation(context):
    if not context or not context["models"] or not HAS_NUMPY:
        return "无模型可交叉验证。"
    lines = ["【交互验证（交叉验证）】"]
    for resp_name, m in context["models"].items():
        if "predict_fn" in m:
            validation = m.get("validation", {})
            lines.append(f"  响应 {resp_name}（{m.get('model_type', '代理模型')}）："
                         f"留出集验证，测试样本 {validation.get('test_samples', '未知')}，"
                         f"R²={validation.get('r2_test', '未知')}，RMSE={m['rmse']:.4g}；未执行 K 折验证。")
            continue
        X, y = _matrix_xy(context, resp_name)
        if len(y) < 4:
            lines.append(f"  {resp_name}: 样本不足")
            continue
        kfold = min(5, len(y))
        rng = _np.random.default_rng(123)
        idx = rng.permutation(len(y))
        splits = _np.array_split(idx, kfold)
        preds = _np.full(len(y), _np.nan)
        for test_idx in splits:
            train_idx = _np.setdiff1d(_np.arange(len(y)), test_idx)
            if len(train_idx) < 3:
                continue
            try:
                m_fold = _fit_model(X[train_idx], y[train_idx], full_quadratic=m.get("full_quadratic", False))
                for i in test_idx:
                    preds[i] = model_predict(m_fold, X[i])
            except Exception:
                continue
        if not _np.all(_np.isfinite(preds)):
            lines.append(f"  {resp_name}: 分折后样本不足或设计矩阵秩不足，无法验证同一模型；未降阶替代。")
            continue
        actual = y
        ss_tot = float(_np.sum((actual - actual.mean()) ** 2)) + 1e-12
        ss_res = float(_np.sum((actual - preds) ** 2))
        cv_r2 = 1 - ss_res / ss_tot
        cv_rmse = math.sqrt(ss_res / len(y))
        lines.append(f"  响应 {resp_name}: {kfold} 折 CV-RMSE={cv_rmse:.4g}, CV-R²={cv_r2:.4g}")
    return "\n".join(lines)


def _matrix_xy(context, resp_name):
    project = context["_project"]
    names = context["names"]
    X, y = [], []
    for row in (project.doe_matrix or []):
        try:
            xv = [float(row[c]) for c in names]
            yv = float(row[resp_name])
        except (KeyError, TypeError, ValueError):
            continue
        X.append(xv)
        y.append(yv)
    return _np.array(X, float), _np.array(y, float)


def residual_analysis(context):
    if not context or not context["models"]:
        return "无模型可做残差分析。", None
    lines = ["【拟合度与残差分析】"]
    data = {}
    for resp_name, m in context["models"].items():
        if "predict_fn" in m:
            validation = m.get("validation", {})
            predicted = validation.get("predicted", [])
            residuals = [a - p for a, p in zip(validation.get("actual", []), predicted)]
            lines.append(f"  {resp_name}：留出集残差，R²={validation.get('r2_test', '未知')}，RMSE={m['rmse']:.4g}")
            data[resp_name] = {"predicted": predicted, "residual": residuals}
            continue
        residuals = m["residual"]
        n = len(residuals)
        mean_r = statistics.mean(residuals) if n else 0.0
        std_r = statistics.pstdev(residuals) if n else 0.0
        std_res = [0.0 if std_r == 0 else (r - mean_r) / std_r for r in residuals]
        lines.append(f"  {resp_name}: R²={m['r2']}, 调整R²={m['adj_r2']}, "
                     f"RMSE={m['rmse']}, 残差均值={mean_r:.4g}, 残差标准差={std_r:.4g}")
        lines.append(f"    标准化残差区间 [{min(std_res):.3g}, {max(std_res):.3g}]，"
                     f"|z|>2 的占比 {sum(1 for z in std_res if abs(z) > 2) / max(n, 1) * 100:.1f}%")
        data[resp_name] = {"predicted": m["predicted"], "residual": residuals,
                           "std_residual": std_res, "r2": m["r2"]}
    return "\n".join(lines), data


def tolerance_contribution(context, k_design, point=None):
    if not context or not context["models"]:
        return "无模型可做容差贡献分析。", {}
    inputs = context["inputs"]
    names = context["names"]
    lines = ["【局部输入方差贡献（独立输入，对角二阶近似）】", f"参考点：{point or '设计区间中心'}", "包含一阶及对角曲率项，与当前优化器近似一致；不含混合二阶项，不代表全局重要性。"]
    detail = {}
    # 参考点：各设计因子取中心
    x_nom = {}
    x_raw = []
    for f in inputs:
        lo, hi = de.factor_limits(f)
        if f.source == "环境":
            val = float(f.param1) if (f.uncertainty == "概率" and f.param1) else (lo + hi) / 2.0
        else:
            val = (point or {}).get(f.name, (lo + hi) / 2.0)
            x_nom[f.name] = val
        x_raw.append(val)
    x = _np.array(x_raw, float)
    for resp_name, m in context["models"].items():
        grad = model_grad_x(m, x)
        sigmas = _np.array([_sigma_of_factor(f, k_design) for f in inputs])
        hess = model_hess_diag_x(m, x)
        contrib = (grad * sigmas) ** 2 + 0.5 * (hess * sigmas**2)**2
        residual_var = float(m.get("residual_std", 0))**2
        total = float(contrib.sum()) + residual_var
        rows = sorted(list(zip(names, contrib.tolist())) + [("模型残差", residual_var)], key=lambda kv: -kv[1])
        lines.append(f"  ◆ 响应 {resp_name}（总方差 {total:.5g}）")
        for name, c in rows:
            lines.append(f"      {name}: 贡献 {c:.5g}（{(c / total * 100 if total > 0 else 0):.2f}%）")
        detail[resp_name] = [{"name": name, "variance": c, "share": (c / total * 100 if total > 0 else 0)} for name, c in rows]
    return "\n".join(lines), detail


def _metric_at(context, xd, k_design, k_constraint=6.0):
    r = evaluate_design(context, xd, k_design, weight_r=0.5, use_constraints=True,
                        k_constraint=k_constraint)
    return r["mean_perf"], r["std_norm"]


def parameter_design(context, robust_result, k_design, k_constraint=6.0):
    if not context or not context["models"]:
        return {"text": "无模型可做参数设计。"}
    d_inputs = design_inputs(context)
    dnames = [f.name for f in d_inputs]
    if not dnames:
        return {"text": "没有设计因子。"}
    lo = {f.name: de.factor_limits(f)[0] for f in d_inputs}
    hi = {f.name: de.factor_limits(f)[1] for f in d_inputs}
    # 推荐点（来自鲁棒优化）
    recommended = dict(robust_result.get("best", {}).get("x", {}))
    if not recommended:
        recommended = {n: (lo[n] + hi[n]) / 2.0 for n in dnames}
    # 稳定点：随机搜索最小化归一化 σ
    rng = _np.random.default_rng(7)
    initial = evaluate_design(context, recommended, k_design, .5, True, k_constraint)
    best_x = dict(recommended) if initial["infeas"] <= 1e-12 else None
    best_std = initial["std_norm"] if best_x is not None else float("inf")
    for _ in range(400):
        trial = {n: rng.uniform(lo[n], hi[n]) for n in dnames}
        evaluation = evaluate_design(context, trial, k_design, .5, True, k_constraint)
        std = evaluation["std_norm"]
        if evaluation["infeas"] <= 1e-12 and std < best_std:
            best_std, best_x = std, dict(trial)
    # 因子扫描图数据
    plots = []
    for f in d_inputs:
        xs, mean_curve, std_curve, feasibility = [], [], [], []
        n_pts = 9
        for t in range(n_pts):
            val = lo[f.name] + (hi[f.name] - lo[f.name]) * t / (n_pts - 1)
            xd = dict(recommended)
            xd[f.name] = val
            evaluated = evaluate_design(context, xd, k_design, .5, True, k_constraint)
            m, s = evaluated["mean_perf"], evaluated["std_norm"]
            feasibility.append(evaluated["infeas"] <= 1e-12)
            xs.append(round(val, 5))
            mean_curve.append(round(m, 4))
            std_curve.append(round(s, 4))
        plots.append({"factor": f.name, "x": xs, "mean": mean_curve, "std": std_curve, "feasible": feasibility})
    lines = ["【参数设计与取值器】"]
    lines.append(f"  优化返回参考点（约束违反={initial['infeas']:.5g}）：{ {k: round(v, 5) for k, v in recommended.items()} }")
    lines.append(f"  有限抽样内的可行稳定候选：{best_x or '未找到；不输出违反约束的稳定点'}")
    _m, _s = _metric_at(context, recommended, k_design, k_constraint)
    _m2, _s2 = _metric_at(context, best_x, k_design, k_constraint) if best_x is not None else (float("nan"), float("nan"))
    lines.append(f"  推荐点：望性均值 {_m:.4f}，σ 归一 {_s:.4f}")
    if best_x is not None:
        lines.append(f"  稳定候选：望性均值 {_m2:.4f}，σ 归一 {_s2:.4f}")
    lines.append("  提示：因子图见“参数设计”页，横轴为取值，纵轴为均值/稳定性。")
    return {"text": "\n".join(lines), "recommended": recommended,
            "stable": best_x, "factor_plots": plots}


def model_extraction(context):
    if not context or not context["models"]:
        return "无模型可提取。"
    lines = ["【模型提取（拟合方程）】"]
    for resp_name, m in context["models"].items():
        if "predict_fn" in m:
            lines.append(f"  {resp_name}：{m.get('model_type', '代理模型')} 已训练预测器；"
                         f"输入变量：{context['names']}。鲁棒优化直接调用该预测器，"
                         "采用数值梯度和 Hessian 传播输入不确定性，无二次多项式方程。")
            continue
        inputs = context["inputs"]
        names = context["names"]
        # 用实际的因子名替换 x_i 命名
        term_names = []
        for label in m["names"]:
            if label == "常数":
                term_names.append("常数")
            elif label.startswith("x") and "·" not in label and "²" not in label:
                idx = int(label[1:]) - 1
                term_names.append(names[idx] if idx < len(names) else label)
            elif "·" in label:
                a, b = label.split("·")
                ia, ib = int(a[1:]) - 1, int(b[1:]) - 1
                term_names.append(f"{names[ia]}·{names[ib]}")
            elif "²" in label:
                idx = int(label[1:-1]) - 1
                term_names.append(f"{names[idx]}²")
            else:
                term_names.append(label)
        s = []
        for i, (c, term) in enumerate(zip(m["coef"], term_names)):
            sign = " + " if c >= 0 else " - "
            mag = abs(float(c))
            body = f"{mag:.5g}" if term == "常数" else f"{mag:.5g}·{term}"
            s.append((body if i == 0 and c >= 0 else sign + body))
        lines.append("    以下符号均为编码变量：" + str(dict(zip(names, zip(m["center"].tolist(), m["half"].tolist())))) + "；编码值=(实际值−中心)/半跨度。")
        lines.append(f"  {resp_name}: y = " + "".join(s).strip())
        lines.append(f"    输入变量：{names}；R²={m['r2']}，调整R²={m['adj_r2']}")
    return "\n".join(lines)
