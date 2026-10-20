"""Model preparation and surrogate training without Qt dependencies."""
from copy import deepcopy
from dataclasses import asdict
import json
import math
import statistics

from backend.engines import design_analysis as design
from backend.engines import doe as engine
from backend.engines import optimizer as optimizer


def active_factors(project):
    return design.active_controls(project)


def active_responses(project):
    return [item for item in project.responses if item.name]


def surrogate_signature(project):
    return json.dumps({
        "config": project.surrogate_config,
        "factors": [asdict(item) for item in active_factors(project)],
        "responses": [asdict(item) for item in active_responses(project)],
        "matrix": project.doe_matrix,
    }, sort_keys=True, ensure_ascii=False)


def train_surrogates(project):
    config = project.surrogate_config or {}
    if not config:
        raise ValueError(
            "尚未配置代理模型，请先在【方案配置】填写模型参数并生成方案。")
    factors = [item for item in active_factors(project) if item.name]
    names = [item.name for item in factors]
    bounds = config.get("bounds") or {}
    lows, highs = {}, {}
    for name, factor in zip(names, factors):
        default_low, default_high = engine.factor_limits(factor)
        low, high = bounds.get(name) or [default_low, default_high]
        lows[name], highs[name] = low, high

    results = {}
    for response in active_responses(project):
        samples, values = [], []
        for row in project.doe_matrix:
            try:
                response_value = float(row.get(response.name))
                sample = [
                    (float(row[name]) - lows[name])
                    / max(highs[name] - lows[name], 1e-12)
                    for name in names
                ]
            except (KeyError, TypeError, ValueError):
                continue
            samples.append(sample)
            values.append(response_value)
        if len(values) < 6:
            results[response.name] = {
                "error":
                    f"响应 {response.name} 有效样本 {len(values)} < 6，无法训练。"}
            continue
        results[response.name] = engine.train_surrogate(
            samples, values, model=config.get("model") or "Kriging",
            model_params=config.get("model_params") or {})
    return {"responses": results, "signature": surrogate_signature(project)}


def build_surrogate_context(project, surrogate_result=None):
    config = project.surrogate_config or {}
    result_map = (surrogate_result or project.surrogate_result).get(
        "responses", {})
    factors = active_factors(project)
    names = [item.name for item in factors]
    bounds = config.get("bounds") or {}
    lows = {
        name: (bounds.get(name) or engine.factor_limits(factor))[0]
        for name, factor in zip(names, factors)
    }
    highs = {
        name: (bounds.get(name) or engine.factor_limits(factor))[1]
        for name, factor in zip(names, factors)
    }
    models, errors = {}, []
    for response in active_responses(project):
        result = result_map.get(response.name) or {}
        predictor = result.get("predict_fn")
        if not callable(predictor):
            errors.append(
                f"响应 {response.name}："
                f"{result.get('error', '没有可用的代理预测器')}")
            continue
        raw_values = []
        for row in project.doe_matrix:
            try:
                raw_values.append(float(row[response.name]))
            except (KeyError, TypeError, ValueError):
                pass

        def predict_raw(values, predictor=predictor):
            normalized = [
                (float(value) - lows[name])
                / max(highs[name] - lows[name], 1e-12)
                for name, value in zip(names, values)
            ]
            return predictor(normalized)

        actual = result.get("actual") or []
        predicted = result.get("predicted") or []
        rmse = (
            math.sqrt(statistics.mean(
                (actual_value - predicted_value) ** 2
                for actual_value, predicted_value in zip(actual, predicted)))
            if actual and predicted else 0.0)
        models[response.name] = {
            "model_type": config.get("model", "Kriging"),
            "validation": result,
            "predict_fn": predict_raw,
            "predicted": raw_values or [0.0, 1.0],
            "rmse": rmse,
            "residual_std": 0.0,
            "finite_difference_step": 1e-3,
        }
    if errors or not models:
        return None, errors or [
            "代理模型尚未训练成功，请先检查响应数据和模型设置。"]
    return {
        "inputs": factors,
        "names": names,
        "models": models,
        "errors": [],
        "_responses": project.responses,
        "_project": project,
    }, []


def build_rsm_context(project):
    context, errors = optimizer.build_models(project)
    if errors or not context or not context["models"]:
        raise ValueError("\n".join(errors or ["响应曲面拟合失败"]))
    return context


def rsm_result(project, context):
    fitted = {}
    for name, model in context["models"].items():
        fitted[name] = {
            key: model[key]
            for key in (
                "r2", "adj_r2", "rmse", "df_model", "df_residual",
                "predicted")
        }
        fitted[name]["coefficients"] = list(zip(
            model["names"], [float(value) for value in model["coef"]]))
        fitted[name]["coding"] = dict(zip(
            context["names"],
            zip(model["center"].tolist(), model["half"].tolist())))
    result = deepcopy(project.rsm_result)
    result["fit"] = fitted
    result["message"] = (
        "汇总与优化使用同一完整二次模型；输入编码 z=(x−中心)/半跨度。")
    return result
