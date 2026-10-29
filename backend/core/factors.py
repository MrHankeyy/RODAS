"""Extracted factors algorithms; preserve v0.1 calculations."""
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


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def factor_limits(factor):
    """返回 (下限, 上限)，保证 low<=high。"""
    if factor.nominal_lower != "" and factor.nominal_upper != "":
        return float(factor.nominal_lower), float(factor.nominal_upper)
    lo = _num(getattr(factor, "param1", None))
    hi = _num(getattr(factor, "param2", None))
    if getattr(factor, "uncertainty", "区间") == "概率":
        mean = lo
        variance = max(0.0, hi)
        if getattr(factor, "distribution", "") == "均匀分布":
            half_width = math.sqrt(3.0 * variance)
        else:
            half_width = 3.0 * math.sqrt(variance)
        lo, hi = mean - half_width, mean + half_width
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        hi = lo + 1.0
    return lo, hi


def factor_center(factor, point=None, include_deviation=True):
    """Keep nominal search values distinct from the center of additive deviations."""
    if factor.source == "环境" and not factor.nominal_lower:
        return (_num(factor.param1) if factor.uncertainty == "概率" else
                (_num(factor.param1) + _num(factor.param2)) / 2)
    lo, hi = factor_limits(factor)
    nominal = (point or {}).get(factor.name, (lo + hi) / 2)
    if factor.nominal_lower != "":
        offset = (_num(factor.param1) if factor.uncertainty == "概率" else
                  (_num(factor.param1) + _num(factor.param2)) / 2)
        return nominal + offset if include_deviation else nominal
    return nominal


def model_factors(project):
    """Both design variables and actual environmental inputs join the model."""
    return [f for f in project.factors if f.name and not f.is_fixed]


def simple_factors(factors, exclude_fixed=True):
    """转成 [(名称, 下限, 上限, 固定值|None), ...] 便于构造器统一处理。"""
    out = []
    for f in factors:
        if not (getattr(f, "name", "") or "").strip():
            continue
        fixed = None
        if exclude_fixed and getattr(f, "is_fixed", False):
            fixed = _num(getattr(f, "fixed_value", None), None)
        lo, hi = factor_limits(f)
        out.append((f.name, lo, hi, fixed))
    return out


def to_actual(code, low, high):
    """把编码值 -1/0/+1/α 映射到实际取值（0=中值）。"""
    return round((low + high) / 2.0 + code * (high - low) / 2.0, 8)


def _round_row(row):
    return {name: (round(v, 8) if isinstance(v, float) else v) for name, v in row.items()}


def _isfinite(x):
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
