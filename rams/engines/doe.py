"""Compatibility imports for existing scripts; implementation lives in core/."""
from rams.core.factors import HAS_NUMPY, _np
from rams.core.doe import SCREENING_KINDS
from rams.core.doe import (
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
from rams.core.factors import (
    _num,
    factor_limits,
    simple_factors,
    to_actual,
    _round_row,
)
from rams.core.response_models import (
    _design_matrix,
    fit_response_surface,
    quadratic_optimum,
    screening_from_responses,
)
from rams.core.sampling import (
    _latin_hypercube,
    _maximin_lhs,
    _van_der_corput,
    _sobol_like,
    build_samples,
)
from rams.core.surrogate import (
    _kernel_rbf,
    _ann_forward,
    train_kriging,
    train_svr,
    train_ann,
    train_surrogate,
)
