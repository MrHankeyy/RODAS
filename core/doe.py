"""Extracted doe algorithms; preserve v0.1 calculations."""
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
from .factors import factor_limits

_PB_CORES = {
    12: "+ + - + + + - - - + -".replace(" ", ""),
    20: "+ + - - + + + + - + - + - - - - + + -".replace(" ", ""),
}

SCREENING_KINDS = {
    "full": "全因子 2^k",
    "half": "部分析因 1/2 分数",
    "quarter": "部分析因 1/4 分数",
    "pb": "Plackett-Burman",
}
from .factors import _round_row, to_actual
from .response_models import _design_matrix


def _gf_oa_columns(prime: int, dim: int):
    """GF(prime)^dim 的全部非零线性型列，返回 (列数, 每列级别列表 0..p-1)。"""
    rows = list(itertools.product(range(prime), repeat=dim))
    coeffs = [c for c in itertools.product(range(prime), repeat=dim) if any(c)]
    # 首非零元素规范为 1，消除成比例的重复列
    norm = []
    for c in coeffs:
        i = next(i for i, v in enumerate(c) if v)
        if c[i] == 1:
            norm.append(c)
    columns = []
    for coeff in norm:
        col = [sum(a * b for a, b in zip(coeff, r)) % prime for r in rows]
        columns.append(col)
    return len(columns), columns


def _oa_levels(label: str):
    """返回标准 L 表的 (标签, 水平数, 行数, 列级别矩阵)。"""
    mapping = {
        "L4": (2, 2), "L8": (2, 3), "L16": (2, 4),
        "L9": (3, 2), "L27": (3, 3),
    }
    if label not in mapping:
        raise ValueError(f"不支持的正交表：{label}")
    prime, dim = mapping[label]
    col_count, columns = _gf_oa_columns(prime, dim)
    runs = prime ** dim
    matrix = [[columns[c][r] for c in range(col_count)] for r in range(runs)]
    return label, prime, runs, matrix


def _pb_matrix(n: int):
    """Plackett-Burman n×（n-1）正交矩阵（±1）。"""
    core = [1 if ch == "+" else -1 for ch in _PB_CORES[n]]
    rows = []
    for shift in range(n - 1):
        rows.append([core[(i - shift) % (n - 1)] for i in range(n - 1)])
    rows.append([-1] * (n - 1))  # 最后一行全低
    return rows


def screening_coded_runs(k: int, kind: str):
    """返回筛选设计的编码行 [[+1/-1/0(中心), ...], ...] 与元信息。"""
    limits = {"full": (1, 7), "half": (3, 10), "quarter": (5, 10), "pb": (1, 19)}
    if kind not in limits or not limits[kind][0] <= k <= limits[kind][1]:
        raise ValueError(f"{SCREENING_KINDS.get(kind, kind)}支持因子数：{limits.get(kind, '未知')}；当前 {k}。")
    if kind == "full":
        n = 2 ** k
        rows = [[1 if (i >> j) & 1 else -1 for j in range(k)] for i in range(n)]
        info_extra = f"全因子设计，2^{k} = {n} 次试验"
    elif kind == "half":
        n = 2 ** (k - 1)
        rows = []
        for i in range(n):
            row = [1 if (i >> j) & 1 else -1 for j in range(k - 1)]
            prod = 1
            for v in row:
                prod *= v
            rows.append(row + [prod])  # 第 k 个因子 = 前 k-1 个乘积
        info_extra = f"分辨率为 {k}（第 {k} 个因子作为生成元）"
    elif kind == "quarter":
        n = 2 ** (k - 2)
        masks = [m for m in range(1, n) if m.bit_count() >= 2]
        a, b = max(itertools.combinations(masks, 2), key=lambda pair: (
            min(pair[0].bit_count() + 1, pair[1].bit_count() + 1,
                (pair[0] ^ pair[1]).bit_count() + 2),
            pair[0].bit_count() + pair[1].bit_count() + (pair[0] ^ pair[1]).bit_count()))
        rows = []
        for i in range(n):
            row = [1 if (i >> j) & 1 else -1 for j in range(k - 2)]
            g1 = math.prod(v for j, v in enumerate(row) if a & (1 << j))
            g2 = math.prod(v for j, v in enumerate(row) if b & (1 << j))
            rows.append(row + [g1, g2])
        resolution = min(a.bit_count() + 1, b.bit_count() + 1, (a ^ b).bit_count() + 2)
        generator = lambda mask: "×".join(f"x{j+1}" for j in range(k-2) if mask & (1 << j))
        info_extra = f"分辨率 {resolution}；生成元 x{k-1}={generator(a)}，x{k}={generator(b)}；主效应正交，仍需检查交互混杂"
    elif kind == "pb":
        n = 12 if k <= 11 else 20
        matrix = _pb_matrix(n)
        rows = [row[:k] for row in matrix]
        info_extra = f"Plackett-Burman {n} 次试验（主效应正交）"
    else:
        raise ValueError(kind)
    return rows, n, info_extra


def build_screening(factors, kind: str, seed: int, centers: int = 0,
                    replicates: int = 1, randomize: bool = True):
    """构造两水平筛选设计表。factors: [(名称,低,高,固定值),...]"""
    if centers < 0 or replicates < 1:
        raise ValueError("中心点数不能为负，重复次数至少为 1")
    fixed_factors = [f for f in factors if f[3] is not None]
    factors = [f for f in factors if f[3] is None]
    k = len(factors)
    if kind == "full" and k > 7:
        raise ValueError("全因子设计仅支持不超过 7 个因子（试验次数 2^k 过大）")
    if kind == "half" and k > 10:
        raise ValueError("1/2 部分析因仅支持不超过 10 个因子")
    if kind == "quarter" and k < 5:
        raise ValueError("1/4 部分析因至少需要 5 个因子")
    if kind == "pb" and k > 19:
        raise ValueError("Plackett-Burman 最多支持 19 个因子")

    coded, base_runs, info = screening_coded_runs(k, kind)
    all_coded = list(coded)
    all_coded.extend([[0] * k] * centers)
    rows = []
    for _ in range(max(1, replicates)):
        for coded_row in all_coded:
            row = {}
            for (name, lo, hi, fixed), code in zip(factors, coded_row):
                row[name] = fixed if fixed is not None else to_actual(code, lo, hi)
            rows.append(_round_row(row))
            rows[-1].update({f[0]: f[3] for f in fixed_factors})
    if randomize:
        rng = random.Random(seed)
        rng.shuffle(rows)
    meta = {
        "kind": SCREENING_KINDS[kind],
        "base_runs": base_runs,
        "centers": centers,
        "replicates": replicates,
        "total_runs": len(rows),
        "diagnostic": info,
        "active_factors": [f[0] for f in factors],
    }
    return rows, meta


def ccd_runs(k: int, alpha: float, centers: int):
    rows = []
    cube = int(2 ** k)
    for i in range(cube):  # 立方点 ±1
        row = [1 if (i >> j) & 1 else -1 for j in range(k)]
        rows.append(row)
    for j in range(k):  # 轴点
        for sign in (1, -1):
            row = [0.0] * k
            row[j] = sign * alpha
            rows.append(row)
    for _ in range(centers):
        rows.append([0.0] * k)
    return rows


def bbd_runs(k: int, centers: int):
    rows = []
    for i, j in itertools.combinations(range(k), 2):  # 每对因子 4 个点
        for xi in (-1, 1):
            for xj in (-1, 1):
                row = [0.0] * k
                row[i] = xi
                row[j] = xj
                rows.append(row)
    for _ in range(centers):
        rows.append([0.0] * k)
    return rows


def rotatable_alpha(k: int):
    return round((2 ** k) ** 0.25, 6)


def build_response_surface(factors, rsm_type: str, alpha_mode: str,
                           custom_alpha: float, centers: int,
                           replicates: int = 1, seed: int = 0,
                           randomize: bool = True):
    """构造 CCD 或 BBD。rsm_type: 'CCD'/'BBD'。"""
    if centers < 0 or replicates < 1:
        raise ValueError("中心点数不能为负，重复次数至少为 1")
    fixed_factors = [f for f in factors if f[3] is not None]
    factors = [f for f in factors if f[3] is None]
    k = len(factors)
    if rsm_type not in ("CCD", "BBD"):
        raise ValueError("响应曲面类型必须为 CCD 或 BBD")
    if rsm_type == "BBD":
        if k < 3:
            raise ValueError("Box-Behnken 设计至少需要 3 个因子")
        if k > 7:
            raise ValueError("Box-Behnken 设计最多支持 7 个因子（试验次数过多）")
        coded = bbd_runs(k, centers)
        alpha = 0.0
        design_label = f"Box-Behnken 设计（k={k}）"
    else:
        if k < 2:
            raise ValueError("中心复合设计至少需要 2 个因子")
        if k > 6:
            raise ValueError("中心复合设计最多支持 6 个因子")
        rot_alpha = rotatable_alpha(k)
        if alpha_mode == "rotatable":
            alpha = rot_alpha
        elif alpha_mode == "face":
            alpha = 1.0
        else:
            alpha = float(custom_alpha)
        if not math.isfinite(alpha) or alpha <= 0:
            raise ValueError("CCD 轴值必须为正数")
        coded = ccd_runs(k, alpha, centers)
        design_label = f"中心复合设计 CCD（k={k}, α={alpha}）"

    if _np.linalg.matrix_rank(_design_matrix(_np.asarray(coded, float))[0]) < (k + 1) * (k + 2) // 2:
        raise ValueError("当前点型无法识别完整二次模型；请增加中心点或调整 CCD 轴值。")
    rows = []
    for _ in range(max(1, replicates)):
        for coded_row in coded:
            row = {}
            for (name, lo, hi, fixed), code in zip(factors, coded_row):
                row[name] = fixed if fixed is not None else to_actual(code, lo, hi)
            rows.append(_round_row(row))
            rows[-1].update({f[0]: f[3] for f in fixed_factors})
    if randomize:
        rng = random.Random(seed)
        rng.shuffle(rows)

    cube_count = (2 ** k) if rsm_type == "CCD" else (2 * k * (k - 1))
    meta = {
        "design": design_label,
        "alpha": alpha if rsm_type == "CCD" else None,
        "cube_points": cube_count,
        "axial_points": 2 * k if rsm_type == "CCD" else 0,
        "centers": centers,
        "replicates": replicates,
        "total_runs": len(rows),
        "active_factors": [f[0] for f in factors],
        "bounds_note": "CCD 的 α>1 轴点超出所填低/高水平；这些水平对应编码 ±1，不是硬边界。" if rsm_type == "CCD" and alpha > 1 else "所有设计点位于所填低/高水平内。",
    }
    return rows, meta


def taguchi_arrays(label: str, k_needed: int):
    """按标签返回级别矩阵（行×k 个因子）并校验容量。"""
    label = label.replace(" ", "")
    if label.startswith("L12"):
        n, levels, columns = 12, 2, _pb_matrix(12)
        if k_needed > 11:
            raise ValueError(f"{label} 最多容纳 11 个因子")
        matrix = [cols[:k_needed] for cols in columns]
        matrix = [[0 if v == -1 else 1 for v in row] for row in matrix]
        return label, levels, n, matrix
    short = next((s for s in ("L4", "L8", "L9", "L16", "L27") if label.startswith(s)), None)
    if not short:
        raise ValueError(f"不支持的正交表：{label}")
    _, levels, n, all_cols = _oa_levels(short)
    capacity = len(all_cols[0]) if all_cols else 0
    if k_needed > capacity:
        raise ValueError(f"{short} 最多容纳 {capacity} 个 {levels} 水平因子")
    matrix = [row[:k_needed] for row in all_cols]
    return short, levels, n, matrix


def _levels_of_factor(lo, hi, n_levels):
    if n_levels == 2:
        return [lo, hi]
    return [lo, (lo + hi) / 2.0, hi]


def build_taguchi(control_factors, noise_factors, inner_label, outer_label,
                  levels: int, seed: int = 0, replicates: int = 1, randomize: bool = True):
    """田口设计：内表(控制因子) × 外表(噪声因子) 叉积。返回行与分组信息。"""
    fixed = {f[0]: f[3] for f in control_factors + noise_factors if f[3] is not None}
    control_factors = [f for f in control_factors if f[3] is None]
    noise_factors = [f for f in noise_factors if f[3] is None]
    if not control_factors:
        raise ValueError("田口设计至少需要一个未固定的控制因子")
    if replicates < 1:
        raise ValueError("重复次数必须至少为 1")
    c_label, c_levels, n_inner, c_matrix = taguchi_arrays(inner_label, len(control_factors))
    if levels != c_levels:
        raise ValueError(f"内表 {c_label} 是 {c_levels} 水平表，与所选 {levels} 水平不一致")
    factor_level_maps = {}
    for (name, lo, hi, _fixed), idx in zip(control_factors, range(len(control_factors))):
        factor_level_maps[name] = _levels_of_factor(lo, hi, levels)

    if noise_factors:
        n_label, n_levels, n_outer, n_matrix = taguchi_arrays(outer_label, len(noise_factors))
        noise_level_maps = {}
        for (name, lo, hi, _fixed), idx in zip(noise_factors, range(len(noise_factors))):
            noise_level_maps[name] = _levels_of_factor(lo, hi, n_levels)
        has_outer = True
    else:
        n_label, n_outer, n_matrix, noise_level_maps, n_levels = "无", 1, [[0]], {}, levels
        has_outer = False

    rows = []
    groups = []
    for ci in range(n_inner):
        for oi in range(n_outer):
            row = {}
            for (name, *_rest), idx in zip(control_factors, range(len(control_factors))):
                row[name] = factor_level_maps[name][c_matrix[ci][idx]]
            if has_outer:
                for (name, *_rest), idx in zip(noise_factors, range(len(noise_factors))):
                    row[name] = noise_level_maps[name][n_matrix[oi][idx]]
            rows.append(_round_row(row))
            rows[-1].update(fixed)
            groups.append({"inner": ci, "outer": oi if has_outer else 0})
    base_rows, base_groups = rows, groups
    rows, groups = [], []
    for rep in range(replicates):
        rows.extend(dict(row) for row in base_rows)
        groups.extend({**g, "replicate": rep} for g in base_groups)
    rng = random.Random(seed)
    order = list(range(len(rows)))
    if randomize:
        rng.shuffle(order)
    rows = [rows[i] for i in order]
    groups = [groups[i] for i in order]
    meta = {
        "inner_label": c_label,
        "outer_label": n_label if has_outer else "无",
        "levels": levels,
        "inner_runs": n_inner,
        "outer_runs": n_outer if has_outer else 1,
        "has_outer": has_outer,
        "replicates": replicates,
        "noise_level_count": n_levels if has_outer else 0,
        "total_runs": len(rows),
        "factor_levels": factor_level_maps,
        "noise_levels": noise_level_maps if has_outer else {},
        "groups": groups,
    }
    return rows, meta
