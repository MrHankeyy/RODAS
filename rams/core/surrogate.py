"""Extracted surrogate algorithms; preserve v0.1 calculations."""
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


def _kernel_rbf(x, z, gamma):
    diff = x[:, None, :] - z[None, :, :]
    return _np.exp(-gamma * _np.sum(diff ** 2, axis=2))


def _ann_forward(x, w1, b1, w2, b2, activation):
    z1 = x @ w1 + b1
    if activation == "relu":
        a1 = _np.maximum(z1, 0.0)
    elif activation == "tanh":
        a1 = _np.tanh(z1)
    else:
        a1 = 1.0 / (1.0 + _np.exp(-z1))
    out = a1 @ w2 + b2
    return a1, out


def train_kriging(Xtr, ytr, Xte, correlation="Gaussian", trend="常数"):
    if not HAS_NUMPY:
        raise RuntimeError("numpy 不可用")
    Xtr = _np.asarray(Xtr, float)
    ytr = _np.asarray(ytr, float)
    Xte = _np.asarray(Xte, float)
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

    def corr(a, b, theta):
        d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        if corr_label == "指数":
            return _np.exp(-_np.sqrt(d2) * theta)
        if corr_label == "Matern 3/2":
            s = _np.sqrt(d2) * theta
            return (1 + s) * _np.exp(-s)
        return _np.exp(-d2 * theta)  # Gaussian / Power(p=2)

    def trend_matrix(values):
        columns = [_np.ones(len(values))]
        if "一次" in trend or "二次" in trend:
            columns.extend(values[:, j] for j in range(values.shape[1]))
        if "二次" in trend:
            columns.extend(values[:, j] ** 2 for j in range(values.shape[1]))
        return _np.column_stack(columns)

    Ftr = trend_matrix(xz)
    Fte = trend_matrix(tz)
    best = None
    for theta in (0.05, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0):
        R = corr(xz, xz, theta) + _np.eye(n) * 1e-8
        try:
            L = _np.linalg.cholesky(R)
        except Exception:
            continue
        r_inv_y = _np.linalg.solve(R, ytr)
        r_inv_f = _np.linalg.solve(R, Ftr)
        beta = _np.linalg.solve(Ftr.T @ r_inv_f, Ftr.T @ r_inv_y)
        res = ytr - Ftr @ beta
        # 集中似然同时估计过程方差，避免响应量纲左右相关长度选择。
        variance = max(float(res @ _np.linalg.solve(R, res)) / n, 1e-30)
        log_like = -_np.sum(_np.log(_np.diag(L))) - 0.5 * n * math.log(variance)
        if best is None or log_like > best[0]:
            best = (log_like, theta, R)
    _loglike, theta, R = best
    r_inv_y = _np.linalg.solve(R, ytr)
    r_inv_f = _np.linalg.solve(R, Ftr)
    beta = _np.linalg.solve(Ftr.T @ r_inv_f, Ftr.T @ r_inv_y)
    w = _np.linalg.solve(R, ytr - Ftr @ beta)
    rte = corr(xz, tz, theta)
    pred = Fte @ beta + rte.T @ w
    # 保留模型的光滑预测；裁剪到样本响应范围会产生虚假的零梯度/零方差平台。
    def predict_fn(values):
        values = _np.asarray(values, float).reshape(1, -1)
        scaled = values / span
        trend_value = trend_matrix(scaled)
        kernel_value = corr(xz, scaled, theta)
        return float((trend_value @ beta + kernel_value.T @ w)[0])
    return {"params": {"theta": theta, "correlation": corr_label, "trend": trend},
            "predicted": [float(v) for v in pred], "predict_fn": predict_fn}


def train_svr(Xtr, ytr, Xte, kernel="RBF", poly_degree=3,
              c_min=0.1, c_max=10.0, c_step=1.0,
              g_min=0.01, g_max=10.0, g_step=1.0):
    """SVR 训练。

    若环境装有 scikit-learn 则调用其 SVR；否则退回 RBF 核岭回归（KRR），
    并按 C/g 网格寻优，输出中会注明所用求解器。
    """
    if not HAS_NUMPY:
        raise RuntimeError("numpy 不可用")
    Xtr = _np.asarray(Xtr, float)
    Xte = _np.asarray(Xte, float)
    ytr = _np.asarray(ytr, float)

    def grid_range(lo, hi, step):
        vals = []
        v = float(lo)
        while v <= float(hi) + 1e-9:
            vals.append(round(v, 6))
            v += float(step)
        return vals or [1.0]

    try:
        from sklearn.svm import SVR  # type: ignore
        kernel_arg = ("rbf" if "RBF" in kernel or kernel == "RBF"
                      else ("poly" if "多项式" in kernel else "sigmoid"))
        best, best_err = None, float("inf")
        for c in grid_range(c_min, c_max, c_step):
            for gamma in grid_range(g_min, g_max, g_step):
                model = SVR(kernel=kernel_arg, degree=int(poly_degree), C=c,
                            gamma=gamma, epsilon=0.05)
                model.fit(Xtr, ytr)
                pred = model.predict(Xtr)
                err = float(_np.mean((pred - ytr) ** 2))
                if err < best_err:
                    best_err, best = err, (c, gamma)
        c, gamma = best
        model = SVR(kernel=kernel_arg, degree=int(poly_degree), C=c,
                gamma=gamma, epsilon=0.05)
        model.fit(Xtr, ytr)
        def predict_fn(values):
            value = _np.asarray(values, float).reshape(1, -1)
            return float(model.predict(value)[0])
        return {"params": {"kernel": kernel, "C": c, "gamma": gamma,
                   "poly_degree": int(poly_degree),
                           "solver": "scikit-learn SVR"},
                "predicted": [float(v) for v in model.predict(Xte)],
                "predict_fn": predict_fn}
    except Exception:
        # KRR 近似：核矩阵 + 岭回归，C 视为 1/λ 的缩放
        best_pred, best_err, best_params = None, float("inf"), (1.0, 1.0)
        for c in grid_range(c_min, c_max, c_step):
            for gamma in grid_range(g_min, g_max, g_step):
                K = _kernel_rbf(Xtr, Xtr, gamma)
                lam = 1.0 / max(c, 1e-6)
                alpha = _np.linalg.solve(K + lam * _np.eye(len(ytr)), ytr)
                pred_tr = K @ alpha
                err = float(_np.mean((pred_tr - ytr) ** 2))
                if err < best_err:
                    best_err = err
                    best_params = (c, gamma)
                    best_alpha = alpha.copy()
                    best_pred = _kernel_rbf(Xtr, Xte, gamma).T @ alpha
        def predict_fn(values):
            value = _np.asarray(values, float).reshape(1, -1)
            return float((_kernel_rbf(Xtr, value, best_params[1]).T @ best_alpha).item())
        return {"params": {"kernel": kernel, "C": best_params[0],
                           "gamma": best_params[1],
                   "poly_degree": int(poly_degree),
                           "solver": "核岭回归 KRR（未安装 scikit-learn 的 SVR 近似）"},
                "predicted": [float(v) for v in best_pred],
                "predict_fn": predict_fn}


def train_ann(Xtr, ytr, Xte, hidden_layers=1, hidden_nodes=8, activation="sigmoid",
              learning_rate=0.05, epochs=300, node_search=None):
    """BP 神经网络训练（numpy 实现；有 scikit-learn 则优先使用 MLPRegressor）。"""
    if not HAS_NUMPY:
        raise RuntimeError("numpy 不可用")
    Xtr = _np.asarray(Xtr, float)
    Xte = _np.asarray(Xte, float)
    ytr = _np.asarray(ytr, float)
    Xmean, Xstd = Xtr.mean(axis=0), Xtr.std(axis=0) + 1e-9
    ymean, ystd = ytr.mean(), ytr.std() + 1e-9
    Xs, ys = (Xtr - Xmean) / Xstd, (ytr - ymean) / ystd
    try:
        from sklearn.neural_network import MLPRegressor  # type: ignore
        if node_search:
            lo, hi, step = node_search
            layer_sizes = [int(max(2, lo + i * step)) for i in range(int((hi - lo) / max(step, 1)) + 1)]
            hidden = tuple(layer_sizes[:int(hidden_layers)]) if int(hidden_layers) > 1 else layer_sizes[0]
        else:
            hidden = tuple([int(hidden_nodes)] * int(hidden_layers)) if int(hidden_layers) > 1 else int(hidden_nodes)
        act = "logistic" if activation == "sigmoid" else activation
        model = MLPRegressor(hidden_layer_sizes=hidden, activation=act,
                             learning_rate_init=float(learning_rate),
                             max_iter=int(epochs), random_state=7)
        model.fit(Xs, ys.ravel())
        def predict_fn(values):
            value = (_np.asarray(values, float).reshape(1, -1) - Xmean) / Xstd
            return float(model.predict(value)[0] * ystd + ymean)
        pred = model.predict((Xte - Xmean) / Xstd) * ystd + ymean
        return {"params": {"layers": hidden, "solver": "scikit-learn MLP"},
            "predicted": [float(v) for v in pred], "predict_fn": predict_fn}
    except Exception:
        rng = _np.random.default_rng(7)
        if node_search:
            nodes = int(max(2, (node_search[0] + node_search[1]) / 2.0))
        else:
            nodes = int(hidden_nodes)
        layers = [nodes] * int(max(hidden_layers, 1))
        nh = layers[0]
        w1 = rng.normal(0, 0.5, (Xs.shape[1], nh))
        b1 = _np.zeros(nh)
        w2 = rng.normal(0, 0.5, (nh, 1))
        b2 = _np.zeros(1)
        for _ in range(int(epochs)):
            a1, out = _ann_forward(Xs, w1, b1, w2, b2, activation)
            err = ys[:, None] - out
            if activation == "relu":
                da1 = (a1 > 0).astype(float)
            elif activation == "tanh":
                da1 = 1 - a1 ** 2
            else:
                da1 = a1 * (1 - a1)
            dw2 = a1.T @ err
            db2 = err.sum(axis=0)
            dz1 = (err @ w2.T) * da1
            dw1 = Xs.T @ dz1
            db1 = dz1.sum(axis=0)
            w1 += learning_rate * dw1 / len(Xs)
            b1 += learning_rate * db1 / len(Xs)
            w2 += learning_rate * dw2 / len(Xs)
            b2 += learning_rate * db2 / len(Xs)
        _, out = _ann_forward((Xte - Xmean) / Xstd, w1, b1, w2, b2, activation)
        pred = out[:, 0] * ystd + ymean
        def predict_fn(values):
            value = (_np.asarray(values, float).reshape(1, -1) - Xmean) / Xstd
            _, result = _ann_forward(value, w1, b1, w2, b2, activation)
            return float(result[0, 0] * ystd + ymean)
        return {"params": {"layers": tuple(layers), "solver": "numpy BP"},
            "predicted": [float(v) for v in pred], "predict_fn": predict_fn}


def train_surrogate(x_rows, response_values, test_ratio=0.2, seed=2026,
                    model="Kriging", model_params=None):
    """训练单个响应的代理模型，返回评估指标（训练/测试误差、耗时等）。"""
    if not HAS_NUMPY:
        return {"error": "当前环境未安装 numpy，无法训练代理模型。"}
    model_params = model_params or {}
    # 设置对话框产生扁平参数；同时兼容早期脚本使用的按模型分组格式。
    model_key = {"Kriging": "kriging", "SVR": "svr"}.get(model, "ann")
    params = dict(model_params.get(model_key, model_params))
    params.pop("net_mode", None)  # 对话框选项，不是训练器参数。
    X = _np.array(x_rows, float)
    y = _np.array(response_values, float)
    if len(y) < 6:
        return {"error": f"有效样本仅 {len(y)} 个，至少需要 6 个才能训练与评估。"}
    rng = _np.random.default_rng(seed)
    idx = rng.permutation(len(y))
    n_test = max(1, int(round(len(y) * 0.2)))
    test_idx, train_idx = idx[:n_test], idx[n_test:]
    Xtr, ytr = X[train_idx], y[train_idx]
    Xte, yte = X[test_idx], y[test_idx]
    t0 = time.time()
    try:
        if model == "Kriging":
            result = train_kriging(Xtr, ytr, Xte, **params)
        elif model == "SVR":
            result = train_svr(Xtr, ytr, Xte, **params)
        else:
            result = train_ann(Xtr, ytr, Xte, **params)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"训练失败：{exc}"}
    elapsed = time.time() - t0
    pred = _np.array(result["predicted"])
    denom = float(_np.abs(yte).mean()) + 1e-9
    mape_test = float(_np.mean(_np.abs(yte - pred) / denom) * 100)
    ss_tot = float(_np.sum((yte - yte.mean()) ** 2)) + 1e-12
    r2_test = float(1 - _np.sum((yte - pred) ** 2) / ss_tot)
    return {
        "params": result["params"],
        "predict_fn": result.get("predict_fn"),
        "train_samples": int(len(train_idx)),
        "test_samples": int(len(test_idx)),
        "train_time_s": round(elapsed, 4),
        "mape_test_%": round(mape_test, 4),
        "r2_test": round(r2_test, 4),
        "actual": [float(v) for v in yte],
        "predicted": [float(v) for v in pred],
    }
