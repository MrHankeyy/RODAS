"""Analysis workflows shared by the Qt pages and headless callers."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib

from backend.core.design_evaluation import DEFAULT_K_DESIGN, DEFAULT_K_CONSTRAINT
from backend.engines import optimizer as optimizer
from backend.engines import workbench as statistics
from backend.services.project_service import ProjectService
from backend.reporting.math_format import polynomial


def build_snapshot(context, k_design=DEFAULT_K_DESIGN, k_constraint=DEFAULT_K_CONSTRAINT):
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


def analyze(project, context, robust, k_design=DEFAULT_K_DESIGN, k_constraint=DEFAULT_K_CONSTRAINT):
    validation = optimizer.validation_results(context)
    validation_text = optimizer.cross_validation(context, validation)
    residual_text, residual_data = optimizer.residual_analysis(context)
    _, tolerance = (optimizer.tolerance_contribution(context, k_design, robust['best']['x'])
                    if robust.get('best') else ('', {}))
    model_text = optimizer.model_extraction(context)
    snapshot = build_snapshot(context, k_design, k_constraint)
    snapshot.update(
        optimization=robust,
        tolerance=tolerance,
        anova_text=optimizer.anova_and_lof(context, project),
        validation_text=validation_text + "\n\n" + residual_text,
        model_text=model_text,
        validation=validation,
    )
    return {
        "anova_text": snapshot["anova_text"],
        "validation_text": snapshot["validation_text"],
        "residual_data": residual_data,
        "tolerance": tolerance,
        "model_text": model_text,
        "snapshot": snapshot,
    }


def evaluate_point(context, values, k_design=DEFAULT_K_DESIGN, k_constraint=DEFAULT_K_CONSTRAINT):
    return statistics.point_analysis(
        context, values, k_design, k_constraint)


def optimization_schemes(context, result):
    """Inspect actual optimized designs without fitting or generating new candidates."""
    best = result.get('best')
    if not best:
        return [], -1
    candidates = result.get('front', []) if result['mode'] == 'multi' else []
    candidates = candidates or [best]
    scoped = dict(context, sigma_limits=result.get('sigma_limits', {}))
    records = [dict(id=f'P{i+1:03}', x=dict(item['x']),
                    verification=evaluate_point(scoped, item['x'], result['k_design'], result['k_constraint']))
               for i, item in enumerate(candidates)]
    default = next(i for i, record in enumerate(records) if record['x'] == best['x'])
    return records, default


def scheme_variance(context, result, point):
    """Local variance decomposition at the viewed design, using the run's settings."""
    return optimizer.tolerance_contribution(context, result['k_design'], point)[1]
