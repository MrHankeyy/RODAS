
from __future__ import annotations

import itertools
import random

from .factors import _round_row


def _latin_hypercube(n_points, dimensions, rng):
    strata = [[(i + rng.random()) / n_points for i in range(n_points)] for _ in range(dimensions)]
    for values in strata:
        rng.shuffle(values)
    return [[strata[col][row] for col in range(dimensions)] for row in range(n_points)]


def _maximin_lhs(n_points, dimensions, rng, candidates=12):
    best = None
    best_score = -1.0
    for _ in range(candidates):
        points = _latin_hypercube(n_points, dimensions, rng)
        score = (
            min(
                sum((a - b) ** 2 for a, b in zip(left, right))
                for i, left in enumerate(points)
                for right in points[i + 1 :]
            )
            if n_points > 1
            else 1.0
        )
        if score > best_score:
            best_score, best = score, points
    return best


def _sobol(n_points, dimensions):
    stage = "依赖加载"
    try:
        from scipy.stats import qmc

        stage = "生成"
        return qmc.Sobol(d=dimensions, scramble=False).random(n_points).tolist()
    except Exception as exc:
        raise ValueError(f"索博尔序列{stage}失败（{type(exc).__name__}）：{exc}") from exc


def build_samples(factors, n_points: int, method: str, seed: int):
    rng = random.Random(seed)
    k = len(factors)
    rows = []
    if method in ("均匀网格抽样", "均匀网格") and k <= 4 and n_points >= 2**k:
        side = max(2, int(round(n_points ** (1.0 / k))))
        points = [
            lo + (hi - lo) * (t / max(side - 1, 1))
            for (_, lo, hi, _) in factors
            for t in range(side)
        ]
        chunks = [points[i * side : (i + 1) * side] for i in range(k)]
        combos = list(itertools.product(*chunks))
        if len(combos) > n_points:
            combos = rng.sample(combos, n_points)
        for combo in combos:
            rows.append({factors[i][0]: combo[i] for i in range(k)})
    elif method in ("Latin Hypercube (LHS)", "最优 LHS"):
        points = (
            _maximin_lhs(n_points, k, rng)
            if method == "最优 LHS"
            else _latin_hypercube(n_points, k, rng)
        )
        for point in points:
            rows.append(
                {name: lo + point[i] * (hi - lo) for i, (name, lo, hi, _) in enumerate(factors)}
            )
    elif method in ("低差异序列 SOBOL", "SOBOL（低差异序列）"):
        for point in _sobol(n_points, k):
            rows.append(
                {name: lo + point[i] * (hi - lo) for i, (name, lo, hi, _) in enumerate(factors)}
            )
    elif method == "稀疏配点法":
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
            rows.append(
                {name: lo + point[i] * (hi - lo) for i, (name, lo, hi, _) in enumerate(factors)}
            )
    else:
        for _ in range(n_points):
            rows.append({name: lo + rng.random() * (hi - lo) for name, lo, hi, _ in factors})
    rng.shuffle(rows)
    return [_round_row(r) for r in rows]
