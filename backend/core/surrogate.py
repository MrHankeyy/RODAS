"""克里金、支持向量回归与神经网络模型训练。"""

from __future__ import annotations

import math
import time
from functools import partial

import numpy as np

from .predictors import Predictor, trend_matrix
from .predictors import correlation as correlation_values


def train_kriging(Xtr, ytr, Xte, correlation="Gaussian", trend="常数"):
    Xtr = np.asarray(Xtr, float)
    ytr = np.asarray(ytr, float)
    Xte = np.asarray(Xte, float)
    n = Xtr.shape[0]
    span = Xtr.max(axis=0) - Xtr.min(axis=0)
    span[span == 0] = 1.0
    xz = Xtr / span
    tz = Xte / span

    corr_label = correlation
    if "Gaussian" in correlation or "高斯" in correlation:
        corr_label = "Gaussian"
    elif "指数" in correlation or "Exponential" in correlation:
        corr_label = "指数"
    elif "Matern" in correlation:
        corr_label = "Matern 3/2"

    corr = partial(correlation_values, label=corr_label)
    trend_matrix_for_model = partial(trend_matrix, kind=trend)

    Ftr = trend_matrix_for_model(xz)
    Fte = trend_matrix_for_model(tz)
    if np.linalg.matrix_rank(Ftr) < Ftr.shape[1]:
        raise ValueError("克里金趋势矩阵秩不足，请增加独立样本或降低趋势阶数。")
    best = None
    for theta in (0.05, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0):
        R = corr(xz, xz, theta) + np.eye(n) * 1e-8
        try:
            L = np.linalg.cholesky(R)
        except np.linalg.LinAlgError:
            continue
        r_inv_y = np.linalg.solve(R, ytr)
        r_inv_f = np.linalg.solve(R, Ftr)
        beta = np.linalg.solve(Ftr.T @ r_inv_f, Ftr.T @ r_inv_y)
        res = ytr - Ftr @ beta
        # 集中似然同时估计过程方差，避免响应量纲左右相关长度选择。
        variance = max(float(res @ np.linalg.solve(R, res)) / n, 1e-30)
        log_like = -np.sum(np.log(np.diag(L))) - 0.5 * n * math.log(variance)
        if best is None or log_like > best[0]:
            best = (log_like, theta, R)
    if best is None:
        raise ValueError("克里金相关矩阵无法分解，请检查重复样本和模型设置。")
    _loglike, theta, R = best
    r_inv_y = np.linalg.solve(R, ytr)
    r_inv_f = np.linalg.solve(R, Ftr)
    beta = np.linalg.solve(Ftr.T @ r_inv_f, Ftr.T @ r_inv_y)
    w = np.linalg.solve(R, ytr - Ftr @ beta)
    rte = corr(xz, tz, theta)
    pred = Fte @ beta + rte.T @ w
    predict_fn = Predictor(
        "kriging",
        dict(
            span=span, x=xz, theta=theta, correlation=corr_label, trend=trend, beta=beta, weights=w
        ),
    )
    return {
        "params": {"theta": theta, "correlation": corr_label, "trend": trend},
        "predicted": [float(v) for v in pred],
        "predict_fn": predict_fn,
    }


def train_svr(
    Xtr,
    ytr,
    Xte,
    kernel="RBF",
    poly_degree=3,
    c_min=0.1,
    c_max=10.0,
    c_step=1.0,
    g_min=0.01,
    g_max=10.0,
    g_step=1.0,
):
    """Train real SVR only; report dependency, fitting and prediction errors."""
    Xtr = np.asarray(Xtr, float)
    Xte = np.asarray(Xte, float)
    ytr = np.asarray(ytr, float)

    def grid_range(lo, hi, step):
        lo, hi, step = float(lo), float(hi), float(step)
        if not all(map(math.isfinite, (lo, hi, step))) or lo <= 0 or hi < lo or step <= 0:
            raise ValueError("C、γ 搜索范围须为正的有限数，上限不得小于下限，步长须大于零。")
        vals = []
        v = lo
        while v <= hi + 1e-9:
            vals.append(round(v, 6))
            v += step
        return vals

    stage = "依赖加载"
    try:
        from sklearn.svm import SVR

        stage = "参数搜索"
        kernel_arg = (
            "rbf"
            if "RBF" in kernel or kernel == "RBF"
            else ("poly" if "多项式" in kernel else "sigmoid")
        )
        best, best_err = None, float("inf")
        for c in grid_range(c_min, c_max, c_step):
            for gamma in grid_range(g_min, g_max, g_step):
                model = SVR(
                    kernel=kernel_arg, degree=int(poly_degree), C=c, gamma=gamma, epsilon=0.05
                )
                model.fit(Xtr, ytr)
                pred = model.predict(Xtr)
                if not np.isfinite(pred).all():
                    raise ValueError("训练集预测包含非有限数。")
                err = float(np.mean((pred - ytr) ** 2))
                if err < best_err:
                    best_err, best = err, (c, gamma)
        c, gamma = best
        stage = "最终训练"
        model = SVR(kernel=kernel_arg, degree=int(poly_degree), C=c, gamma=gamma, epsilon=0.05)
        model.fit(Xtr, ytr)
        stage = "预测器构造"
        predict_fn = Predictor(
            "svr",
            dict(
                support=model.support_vectors_,
                dual=model.dual_coef_.ravel(),
                intercept=float(model.intercept_[0]),
                kernel=model.kernel,
                gamma=float(model._gamma),
                degree=model.degree,
                coef0=model.coef0,
            ),
        )
        stage = "测试集预测"
        predicted = model.predict(Xte)
        if not np.isfinite(predicted).all():
            raise ValueError("测试集预测包含非有限数。")
        return {
            "params": {
                "kernel": kernel,
                "C": c,
                "gamma": gamma,
                "poly_degree": int(poly_degree),
                "solver": "scikit-learn SVR",
            },
            "predicted": [float(v) for v in predicted],
            "predict_fn": predict_fn,
        }
    except Exception as exc:
        raise RuntimeError(f"支持向量回归{stage}失败（{type(exc).__name__}）：{exc}") from exc


def train_ann(
    Xtr,
    ytr,
    Xte,
    hidden_layers=1,
    hidden_nodes=8,
    activation="sigmoid",
    learning_rate=0.05,
    epochs=300,
    node_search=None,
):
    """训练指定层数的 MLP；节点寻优仅使用训练集内部的验证样本。"""
    stage = "依赖加载"
    try:
        from sklearn.neural_network import MLPRegressor
        from sklearn.preprocessing import StandardScaler

        stage = "参数校验"
        Xtr = np.asarray(Xtr, float)
        Xte = np.asarray(Xte, float)
        ytr = np.asarray(ytr, float)
        depth = int(hidden_layers)
        if (
            depth < 1
            or int(epochs) < 1
            or not math.isfinite(float(learning_rate))
            or learning_rate <= 0
        ):
            raise ValueError("网络层数、训练代数和学习率必须为正数。")
        if node_search is None:
            widths = [int(hidden_nodes)]
        else:
            low, high, step = map(int, node_search)
            if low < 1 or high < low or step < 1:
                raise ValueError("节点搜索下限至少为 1，上限不得小于下限，步长必须为正数。")
            widths = list(range(low, high + 1, step))
        if min(widths) < 1:
            raise ValueError("每个隐含层至少需要一个节点。")
        act = "logistic" if activation == "sigmoid" else activation

        def make_model(width):
            return MLPRegressor(
                hidden_layer_sizes=(width,) * depth,
                activation=act,
                learning_rate_init=float(learning_rate),
                max_iter=int(epochs),
                random_state=7,
            )

        stage = "节点搜索"
        selected = widths[0]
        if len(widths) > 1:
            order = np.random.default_rng(7).permutation(len(ytr))
            count = max(1, int(round(len(ytr) * 0.2)))
            validation, training = order[:count], order[count:]
            x_scale = StandardScaler().fit(Xtr[training])
            y_scale = StandardScaler().fit(ytr[training, None])
            train_x = x_scale.transform(Xtr[training])
            train_y = y_scale.transform(ytr[training, None]).ravel()
            validation_x = x_scale.transform(Xtr[validation])
            validation_y = y_scale.transform(ytr[validation, None]).ravel()
            best_error = float("inf")
            for width in widths:
                candidate = make_model(width)
                candidate.fit(train_x, train_y)
                error = float(np.mean((candidate.predict(validation_x) - validation_y) ** 2))
                if not math.isfinite(error):
                    raise ValueError("节点搜索预测包含非有限数。")
                if error < best_error:
                    selected, best_error = width, error

        stage = "最终训练"
        x_mean, x_std = Xtr.mean(axis=0), Xtr.std(axis=0) + 1e-9
        y_mean, y_std = ytr.mean(), ytr.std() + 1e-9
        model = make_model(selected)
        model.fit((Xtr - x_mean) / x_std, (ytr - y_mean) / y_std)
        stage = "预测器构造"
        predict_fn = Predictor(
            "ann",
            dict(
                weights=model.coefs_,
                biases=model.intercepts_,
                activation=model.activation,
                out_activation=model.out_activation_,
                x_mean=x_mean,
                x_std=x_std,
                y_mean=y_mean,
                y_std=y_std,
            ),
        )
        stage = "测试集预测"
        predicted = predict_fn.predict(Xte)
        if not np.isfinite(predicted).all():
            raise ValueError("测试集预测包含非有限数。")
        return {
            "params": {"layers": (selected,) * depth, "solver": "scikit-learn MLP"},
            "predicted": predicted.tolist(),
            "predict_fn": predict_fn,
        }
    except Exception as exc:
        raise RuntimeError(f"神经网络{stage}失败（{type(exc).__name__}）：{exc}") from exc


def train_surrogate(
    x_rows, response_values, test_ratio=0.2, seed=2026, model="Kriging", model_params=None
):
    """训练单个响应的代理模型，返回评估指标（训练/测试误差、耗时等）。"""
    model_params = model_params or {}
    # 参数可直接提供，也可按模型名称分组。
    model_key = {"Kriging": "kriging", "SVR": "svr"}.get(model, "ann")
    params = dict(model_params.get(model_key, model_params))
    params.pop("net_mode", None)  # 对话框选项，不是训练器参数。
    if model not in ("Kriging", "SVR", "ANN"):
        return {"error": f"不支持的代理模型：{model}"}
    try:
        X = np.asarray(x_rows, float)
        y = np.asarray(response_values, float)
        ratio = float(test_ratio)
        if X.ndim != 2 or X.shape[1] == 0 or y.ndim != 1 or len(X) != len(y):
            raise ValueError("输入须为二维样本矩阵，响应须为等长的一维数组。")
        if not np.isfinite(X).all() or not np.isfinite(y).all():
            raise ValueError("训练数据包含非有限数，请检查缺失值和无效响应。")
        if not 0 < ratio < 1:
            raise ValueError("测试集比例必须介于 0 与 1 之间。")
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}
    if len(y) < 6:
        return {"error": f"有效样本仅 {len(y)} 个，至少需要 6 个才能训练与评估。"}
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(y))
    n_test = min(len(y) - 2, max(1, int(round(len(y) * ratio))))
    test_idx, train_idx = idx[:n_test], idx[n_test:]
    Xtr, ytr = X[train_idx], y[train_idx]
    Xte, yte = X[test_idx], y[test_idx]
    t0 = time.perf_counter()
    try:
        if model == "Kriging":
            result = train_kriging(Xtr, ytr, Xte, **params)
        elif model == "SVR":
            result = train_svr(Xtr, ytr, Xte, **params)
        else:
            result = train_ann(Xtr, ytr, Xte, **params)
    except Exception as exc:
        return {"error": f"训练失败：{exc}"}
    elapsed = time.perf_counter() - t0
    pred = np.array(result["predicted"])
    denom = float(np.abs(yte).mean()) + 1e-9
    nmae_test = float(np.mean(np.abs(yte - pred) / denom) * 100)
    ss_tot = float(np.sum((yte - yte.mean()) ** 2)) + 1e-12
    r2_test = float(1 - np.sum((yte - pred) ** 2) / ss_tot)
    return {
        "params": result["params"],
        "predict_fn": result.get("predict_fn"),
        "train_samples": int(len(train_idx)),
        "test_samples": int(len(test_idx)),
        "train_time_s": round(elapsed, 4),
        "nmae_test_%": round(nmae_test, 4),
        "r2_test": round(r2_test, 4),
        "actual": [float(v) for v in yte],
        "validation_inputs": Xte.tolist(),
        "predicted": [float(v) for v in pred],
    }
