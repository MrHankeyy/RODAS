"""Analysis workflows shared by the Qt pages and headless callers."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib

from backend.engines import optimizer as optimizer
from backend.engines import workbench as statistics
from backend.services.project_service import ProjectService
from backend.reporting.math_format import polynomial


def build_snapshot(context, k_design=6, k_constraint=6):
    project = context["_project"]
    formulas = {}
    for name, model in context["models"].items():
        if "predict_fn" not in model:
            _, equation, coding = polynomial(name, model, context["names"])
            formulas[name] = {"equation": equation, "coding": [item.latex for item in coding]}
    return {
        "model_formulas": formulas,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": hashlib.sha256(
            ProjectService.for_project(project).input_signature().encode("utf-8")).hexdigest(),
        "inputs": [asdict(item) for item in context["inputs"]],
        "response_definitions": [
            asdict(item) for item in context["_responses"]],
        "model_types": {
            name: model.get("model_type", "二次回归")
            for name, model in context["models"].items()
        },
        "method": project.design_method,
        "k_design": k_design,
        "k_constraint": k_constraint,
        "data": statistics.descriptive(project),
        "responses": {
            name: statistics.diagnostics(context, name)
            for name in context["models"]
        },
    }


def analyze(project, context, robust, k_design=6, k_constraint=6):
    validation = optimizer.validation_results(context)
    validation_text = optimizer.cross_validation(context, validation)
    residual_text, residual_data = optimizer.residual_analysis(context)
    parameter_result = (
        optimizer.parameter_design(
            context, robust, k_design, k_constraint)
        if robust else {
            "text": (
                "尚未执行鲁棒优化，无推荐点；"
                "可在统计诊断页手动核验设计点。"),
            "factor_plots": [],
        })
    tolerance_text, tolerance = optimizer.tolerance_contribution(
        context, k_design, (robust.get("best") or {}).get("x"))
    model_text = optimizer.model_extraction(context)
    snapshot = build_snapshot(context, k_design, k_constraint)
    snapshot.update(
        optimization=robust,
        tolerance=tolerance,
        parameter_design=parameter_result,
        anova_text=optimizer.anova_and_lof(context, project),
        validation_text=validation_text + "\n\n" + residual_text,
        model_text=model_text,
        validation=validation,
    )
    return {
        "anova_text": snapshot["anova_text"],
        "validation_text": snapshot["validation_text"],
        "residual_data": residual_data,
        "parameter_design": parameter_result,
        "tolerance_text": tolerance_text,
        "tolerance": tolerance,
        "model_text": model_text,
        "snapshot": snapshot,
    }


def evaluate_point(context, values, k_design=6, k_constraint=6):
    return statistics.point_analysis(
        context, values, k_design, k_constraint)


def run_local_search(context, start, k_design, k_constraint, weight,
                     method, steps, step_size):
    return optimizer.local_search(
        context, start, k_design, k_constraint, weight, method, steps,
        step_size)
