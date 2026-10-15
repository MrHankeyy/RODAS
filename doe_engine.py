"""Compatibility imports for existing scripts; implementation lives in core/."""
from core.factors import HAS_NUMPY, _np
from core.doe import SCREENING_KINDS
from core.doe import (
    _gf_oa_columns,
    _oa_levels,
    _pb_matrix,
    screening_coded_runs,
    build_screening,
    ccd_runs,
    bbd_runs,
    rotatable_alpha,
    build_response_surface,
    taguchi_arrays,
    _levels_of_factor,
    build_taguchi,
)
from core.factors import (
    _num,
    factor_limits,
    simple_factors,
    to_actual,
    _round_row,
)
from core.response_models import (
    _design_matrix,
    fit_response_surface,
    quadratic_optimum,
    screening_from_responses,
)
from core.sampling import (
    _latin_hypercube,
    _maximin_lhs,
    _van_der_corput,
    _sobol_like,
    build_samples,
)
from core.surrogate import (
    _kernel_rbf,
    _ann_forward,
    train_kriging,
    train_svr,
    train_ann,
    train_surrogate,
)
