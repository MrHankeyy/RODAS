"""Compatibility imports for existing scripts; implementation lives in core/."""
from backend.core.factors import HAS_NUMPY, _np
from backend.core.doe import (
    _gf_oa_columns,
    _oa_levels,
    _pb_matrix,
    ccd_runs,
    bbd_runs,
    rotatable_alpha,
    build_response_surface,
    taguchi_arrays,
    _levels_of_factor,
    build_taguchi,
)
from backend.core.factors import (
    _num,
    factor_limits,
    simple_factors,
    to_actual,
    _round_row,
)
from backend.core.response_models import (
    _design_matrix,
    fit_response_surface,
    quadratic_optimum,
)
from backend.core.sampling import (
    _latin_hypercube,
    _maximin_lhs,
    _sobol,
    build_samples,
)
from backend.core.surrogate import (
    _ann_forward,
    train_kriging,
    train_svr,
    train_ann,
    train_surrogate,
)
