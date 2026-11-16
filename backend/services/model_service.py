
import json
import math
import statistics
from copy import deepcopy
from dataclasses import asdict

from backend.core.factors import model_factors
from backend.domain.models import factor_definition
from backend.engines import doe as engine
from backend.engines import optimizer as optimizer


def active_factors(project):
    return model_factors(project)


def active_responses(project):
    return [item for item in project.responses if item.name]


def surrogate_signature(project):
    return json.dumps(
        {
            "config": project.surrogate_config,
            "factors": [factor_definition(item) for item in active_factors(project)],
            "responses": [asdict(item) for item in active_responses(project)],
            "matrix": project.doe_matrix,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _training_bounds(project, factors):
    configured = (project.surrogate_config or {}).get("bounds") or {}
    lows, highs = {}, {}
    for factor in factors:
        low, high = map(float, configured.get(factor.name) or engine.factor_limits(factor))
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ValueError(f"{factor.name} 的模型训练范围无效，上限须大于下限且均为有限数。")
        lows[factor.name], highs[factor.name] = low, high
    return lows, highs


def train_surrogates(project):
    config = project.surrogate_config or {}
    if not config:
        raise ValueError("尚未配置代理模型，请先在【方案配置】填写模型参数并生成方案。")
    factors = [item for item in active_factors(project) if item.name]
    names = [item.name for item in factors]
    lows, highs = _training_bounds(project, factors)

    results = {}
    for response in active_responses(project):
        samples, values = [], []
        for row in project.doe_matrix:
            try:
                response_value = float(row.get(response.name))
                sample = [
                    (float(row[name]) - lows[name]) / (highs[name] - lows[name]) for name in names
                ]
            except (KeyError, TypeError, ValueError):
                continue
            samples.append(sample)
            values.append(response_value)
        if len(values) < 6:
            results[response.name] = {
                "error": f"响应 {response.name} 有效样本 {len(values)} < 6，无法训练。"
            }
            continue
        results[response.name] = engine.train_surrogate(
            samples,
            values,
            model=config.get("model") or "Kriging",
            model_params=config.get("model_params") or {},
        )
    return {"responses": results, "signature": surrogate_signature(project)}


def build_surrogate_context(project, surrogate_result=None):
    config = project.surrogate_config or {}
    result_map = (surrogate_result or project.surrogate_result).get("responses", {})
    factors = active_factors(project)
    names = [item.name for item in factors]
    lows, highs = _training_bounds(project, factors)
    models, errors = {}, []
    for response in active_responses(project):
        result = result_map.get(response.name) or {}
        predictor = result.get("predict_fn")
        if not callable(predictor):
            errors.append(f"响应 {response.name}：{result.get('error', '没有可用的代理预测器')}")
            continue
        raw_values = []
        for row in project.doe_matrix:
            try:
                raw_values.append(float(row[response.name]))
            except (KeyError, TypeError, ValueError):
                pass

        def predict_raw(values, predictor=predictor):
            normalized = [
                (float(value) - lows[name]) / (highs[name] - lows[name])
                for name, value in zip(names, values)
            ]
            return predictor(normalized)

        actual = result.get("actual") or []
        predicted = result.get("predicted") or []
        rmse = (
            math.sqrt(
                statistics.mean(
                    (actual_value - predicted_value) ** 2
                    for actual_value, predicted_value in zip(actual, predicted)
                )
            )
            if actual and predicted
            else 0.0
        )
        models[response.name] = {
            "model_type": config.get("model", "Kriging"),
            "validation": result,
            "predict_fn": predict_raw,
            "predicted": raw_values or [0.0, 1.0],
            "rmse": rmse,
            "residual_std": 0.0,
            "finite_difference_step": [
                1e-3 * (highs[name] - lows[name]) for name in names
            ],
        }
    if errors or not models:
        return None, errors or ["代理模型尚未训练成功，请先检查响应数据和模型设置。"]
    return {
        "inputs": factors,
        "names": names,
        "models": models,
        "errors": [],
        "_responses": project.responses,
        "_project": project,
    }, []


def build_rsm_context(project):
    from backend.services.project_service import ProjectService

    service = ProjectService.for_project(project)
    service.ensure_current()
    if service.model_cache.get("rsm"):
        factors = [f for f in model_factors(project) if f.name in project.doe_matrix[0]]
        return dict(
            inputs=factors,
            names=[f.name for f in factors],
            models=service.model_cache["rsm"],
            errors=[],
            _responses=project.responses,
            _project=project,
        )
    context, errors = optimizer.build_models(project)
    if errors or not context or not context["models"]:
        raise ValueError("\n".join(errors or ["二次响应面模型拟合失败"]))
    service.model_cache["rsm"] = context["models"]
    return context


def rsm_result(project, context):
    fitted = {}
    for name, model in context["models"].items():
        fitted[name] = {
            key: model[key]
            for key in ("r2", "adj_r2", "rmse", "df_model", "df_residual", "predicted")
        }
        fitted[name]["coefficients"] = list(
            zip(model["names"], [float(value) for value in model["coef"]])
        )
        fitted[name]["coding"] = dict(
            zip(context["names"], zip(model["center"].tolist(), model["half"].tolist()))
        )
    result = deepcopy(project.rsm_result)
    result["fit"] = fitted
    result["message"] = "汇总与优化使用同一完整二次模型；输入编码 z=(x−中心)/半跨度。"
    return result
