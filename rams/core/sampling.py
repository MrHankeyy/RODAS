"""Extracted sampling algorithms; preserve v0.1 calculations."""
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
from .factors import _round_row


def _latin_hypercube(n_points, dimensions, rng):
    strata = [[(i + rng.random()) / n_points for i in range(n_points)]
              for _ in range(dimensions)]
    for values in strata:
        rng.shuffle(values)
    return [[strata[col][row] for col in range(dimensions)]
            for row in range(n_points)]


def _maximin_lhs(n_points, dimensions, rng, candidates=12):
    """用小规模候选搜索提高 LHS 的空间分散性，避免依赖 scipy。"""
    best = None
    best_score = -1.0
    for _ in range(candidates):
        points = _latin_hypercube(n_points, dimensions, rng)
        score = min(
            sum((a - b) ** 2 for a, b in zip(left, right))
            for i, left in enumerate(points)
            for right in points[i + 1:]
        ) if n_points > 1 else 1.0
        if score > best_score:
            best_score, best = score, points
    return best


def _van_der_corput(index, base):
    value, factor = 0.0, 1.0 / base
    while index:
        index, remainder = divmod(index, base)
        value += remainder * factor
        factor /= base
    return value


def _sobol_like(n_points, dimensions):
    """优先使用 scipy 的 Sobol；无 scipy 时回退到确定性的低差异序列。"""
    try:
        from scipy.stats import qmc  # type: ignore
        return qmc.Sobol(d=dimensions, scramble=False).random(n_points).tolist()
    except Exception:
        pass
    bases = [2, 3, 5, 7, 11, 13, 17, 19]
    return [[_van_der_corput(index + 1, bases[col % len(bases)])
             for col in range(dimensions)] for index in range(n_points)]


def build_samples(factors, n_points: int, method: str, seed: int):
    """代理模型试验样本（LHS、最优 LHS、Sobol、网格、稀疏网格或随机）。"""
    rng = random.Random(seed)
    k = len(factors)
    rows = []
    if method in ("均匀网格抽样", "均匀网格") and k <= 4 and n_points >= 2 ** k:
        side = max(2, int(round(n_points ** (1.0 / k))))
        points = [lo + (hi - lo) * (t / max(side - 1, 1))
                  for (_, lo, hi, _) in factors for t in range(side)]
        chunks = [points[i * side:(i + 1) * side] for i in range(k)]
        combos = list(itertools.product(*chunks))
        if len(combos) > n_points:
            combos = rng.sample(combos, n_points)
        for combo in combos:
            rows.append({factors[i][0]: combo[i] for i in range(k)})
    elif method in ("Latin Hypercube (LHS)", "最优 LHS"):
        points = (_maximin_lhs(n_points, k, rng)
                  if method == "最优 LHS" else _latin_hypercube(n_points, k, rng))
        for point in points:
            rows.append({name: lo + point[i] * (hi - lo)
                         for i, (name, lo, hi, _) in enumerate(factors)})
    elif method in ("低差异序列 SOBOL", "SOBOL（低差异序列）"):
        for point in _sobol_like(n_points, k):
            rows.append({name: lo + point[i] * (hi - lo)
                         for i, (name, lo, hi, _) in enumerate(factors)})
    elif method == "稀疏配点法":
        # 每次只激活少量维度，覆盖中心、轴向及低阶组合点。
        center = [0.5] * k
        unit_points = [center]
        for i in range(k):
            for value in (0.0, 1.0):
                point = list(center)
                point[i] = value
                unit_points.append(point)
        for i, j in itertools.combinations(range(k), 2):
            point = list(center)
            point[i], point[j] = 0.0, 1.0
            unit_points.append(point)
        while len(unit_points) < n_points:
            point = list(center)
            for i in rng.sample(range(k), min(2, k)):
                point[i] = rng.choice((0.0, 1.0))
            unit_points.append(point)
        for point in unit_points[:n_points]:
            rows.append({name: lo + point[i] * (hi - lo)
                         for i, (name, lo, hi, _) in enumerate(factors)})
    else:  # 随机抽样
        for _ in range(n_points):
            rows.append({name: lo + rng.random() * (hi - lo) for name, lo, hi, _ in factors})
    rng.shuffle(rows)
    return [_round_row(r) for r in rows]
