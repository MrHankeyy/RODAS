"""Compatibility imports for existing scripts; implementation lives in core/."""
from rams.core.factors import HAS_NUMPY, _np
from rams.core import factors as de
from rams.core.design_evaluation import (
    _sigma_of_factor,
    robust_moments,
    _response_ref,
    _desirability,
    _constraint_limits,
    _response_scale,
    evaluate_design,
    project_responses,
    self_is_constraint,
    design_inputs,
)
from rams.core.factors import (
    _isfinite,
)
from rams.core.optimization import (
    _dominates,
    _fast_non_dominated_sort,
    _crowding_distance,
    _sbx_crossover,
    _polynomial_mutation,
    nsga2,
    _pareto,
    _knee_point,
    robust_optimize,
    _robust_result_text,
    _design_bounds,
    local_search,
    steepest_ascent,
    evop_cycle,
    aofat_search,
)
from rams.core.response_models import (
    _design_terms,
    _design_row,
    _quad_hess_diag,
    _quad_grad,
    _fit_model,
    model_predict,
    model_grad_x,
    model_hess_diag_x,
    model_equation,
    build_models,
)
from rams.core.statistics import (
    _gammaln,
    _betacf,
    _betai,
    _f_pvalue,
    describe_data,
    level_stats,
    anova_and_lof,
    cross_validation,
    _matrix_xy,
    residual_analysis,
    tolerance_contribution,
    _metric_at,
    parameter_design,
    model_extraction,
)
