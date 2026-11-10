"""Extracted optimization algorithms; preserve v0.1 calculations."""
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
from .design_evaluation import DEFAULT_K_DESIGN, DEFAULT_K_CONSTRAINT, _response_ref, _response_scale, _sigma_of_factor, design_inputs, evaluate_design, project_responses, self_is_constraint, response_uses_limits, validate_response_limits


def _dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _fast_non_dominated_sort(fitness):
    n = len(fitness)
    dominates_count = [0] * n
    dominated = [[] for _ in range(n)]
    ranks = [[]]
    for i in range(n):
        for j in range(i + 1, n):
            if _dominates(fitness[i], fitness[j]):
                dominated[i].append(j)
                dominates_count[j] += 1
            elif _dominates(fitness[j], fitness[i]):
                dominated[j].append(i)
                dominates_count[i] += 1
        if dominates_count[i] == 0:
            ranks[0].append(i)
    front = [ranks[0]]
    k = 0
    while True:
        nxt = []
        for i in front[k]:
            for j in dominated[i]:
                dominates_count[j] -= 1
                if dominates_count[j] == 0:
                    nxt.append(j)
        if not nxt:
            break
        front.append(nxt)
        k = k + 1
    return front


def _crowding_distance(fitness, front):
    n_obj = len(fitness[0])
    dist = {i: 0.0 for i in front}
    if len(front) <= 2:
        for i in front:
            dist[i] = float("inf")
        return dist
    for m in range(n_obj):
        front_sorted = sorted(front, key=lambda i: fitness[i][m])
        lo = fitness[front_sorted[0]][m]
        hi = fitness[front_sorted[-1]][m]
        span = (hi - lo) or 1.0
        dist[front_sorted[0]] = dist.get(front_sorted[0], 0) + 1e9
        dist[front_sorted[-1]] = dist.get(front_sorted[-1], 0) + 1e9
        for a, b in zip(front_sorted, front_sorted[1:]):
            dist[a] = dist.get(a, 0) + (fitness[b][m] - fitness[a][m]) / span
    return dist


def _sbx_crossover(p1, p2, eta, lo, hi, rng, pc=0.5):
    c1, c2 = list(p1), list(p2)
    for i in range(len(p1)):
        if rng.random() >= pc:
            continue
        if abs(p1[i] - p2[i]) < 1e-12:
            continue
        u = rng.random()
        if u <= 0.5:
            beta = (2.0 * u) ** (1.0 / (eta + 1))
        else:
            beta = (1.0 / (2.0 * (1.0 - u))) ** (1.0 / (eta + 1))
        c1[i] = 0.5 * ((1 + beta) * p1[i] + (1 - beta) * p2[i])
        c2[i] = 0.5 * ((1 - beta) * p1[i] + (1 + beta) * p2[i])
    c1 = [min(hi[i], max(lo[i], v)) for i, v in enumerate(c1)]
    c2 = [min(hi[i], max(lo[i], v)) for i, v in enumerate(c2)]
    return c1, c2


def _polynomial_mutation(x, eta, pm, lo, hi, rng):
    out = list(x)
    for i in range(len(x)):
        if rng.random() >= pm:
            continue
        u = rng.random()
        delta = (2.0 * u) ** (1.0 / (eta + 1)) - 1.0 if u < 0.5 else \
            1.0 - (2.0 * (1.0 - u)) ** (1.0 / (eta + 1))
        out[i] = min(hi[i], max(lo[i], x[i] + delta * (hi[i] - lo[i])))
    return out


def _generation_record(generation, population, assess, evaluated_count):
    """Summarise one generation: per-objective best/mean over feasible members."""
    values = [assess(v) for v in population]
    feasible = [obj for obj, info in values if info.get("r", {}).get("infeas", 0) <= 1e-8]
    usable = feasible or [obj for obj, _info in values]
    if not usable:
        return {"gen": generation, "best": [], "mean": [], "feasible": 0,
                "evaluated": evaluated_count}, []
    columns = list(zip(*usable))
    record = {
        "gen": generation,
        "best": [round(min(column), 6) for column in columns],
        "mean": [round(sum(column) / len(column), 6) for column in columns],
        "feasible": len(feasible),
        "evaluated": evaluated_count,
    }
    return record, usable


def _reference_point(usable):
    """固定参考点：首代目标值域外扩一成，用于逐代超体积比较。"""
    columns = list(zip(*usable))
    return tuple(max(column) + max(0.1 * (max(column) - min(column)), 0.05)
                 for column in columns[:2])


def _hypervolume(front, reference):
    """二维最小化超体积：前沿点相对参考点支配的面积。"""
    points = sorted((float(f1), float(f2)) for f1, f2 in front
                    if f1 < reference[0] and f2 < reference[1])
    volume, previous = 0.0, reference[1]
    for f1, f2 in points:
        if f2 < previous:
            volume += (reference[0] - f1) * (previous - f2)
            previous = f2
    return volume


def _stall_rule(mode, window, tolerance):
    """连续 window 代改进不足 tolerance 时返回 True；多目标看超体积。"""
    def reached(history):
        if len(history) <= window:
            return False
        start, recent = history[-window - 1], history[-window:]
        if mode == "multi":
            past = start.get("hv") or 0.0
            if past <= 0:
                return False
            best = max((record.get("hv") or 0.0) for record in recent)
            return (best - past) / past < tolerance
        past_values = start.get("best") or []
        if not past_values:
            return False
        past = past_values[0]
        best = min(((record.get("best") or [past])[0]) for record in recent)
        return (past - best) / max(abs(past), 1e-12) < tolerance
    return reached


def nsga2(evaluate, lo, hi, pop=60, gen=100, seed=1, eta_c=15.0, eta_m=20.0, progress=None, pc=0.5, pm=None,
          should_stop=None, track_hypervolume=False):
    """Elitist NSGA-II with feasibility-first survival and tournament selection."""
    if pop < 2 or gen < 1:
        raise ValueError("种群至少为 2，迭代代数至少为 1。")
    if len(lo) == 0 or len(lo) != len(hi):
        raise ValueError("设计变量边界不能为空，且上下界数量必须一致。")
    mutation_probability = 1.0 / len(lo) if pm is None else pm
    for label, value in (("逐变量交叉概率", pc), ("逐变量变异概率", mutation_probability)):
        if value is None or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(label + "必须在 0 到 1 之间。")
    if any(not math.isfinite(v) or v <= 0 for v in (eta_c, eta_m)):
        raise ValueError("交叉和变异分布指数必须为有限正数。")
    rng = _np.random.default_rng(seed)
    n = len(lo)
    evaluated = {}
    def assess(v):
        key = tuple(float(x) for x in v)
        if key not in evaluated:
            evaluated[key] = evaluate(v)
        return evaluated[key]
    def order(population):
        values = [assess(v) for v in population]
        feasible = [i for i, (_, info) in enumerate(values) if info.get("r", {}).get("infeas", 0) <= 1e-8]
        invalid = [i for i in range(len(values)) if i not in feasible]
        rank = {}
        distance = {}
        fronts = _fast_non_dominated_sort([values[i][0] for i in feasible])
        for r, front in enumerate(fronts):
            if not front:
                continue
            crowd = _crowding_distance([values[i][0] for i in feasible], front)
            for j in front:
                rank[feasible[j]] = r
                distance[feasible[j]] = crowd[j]
        keys = {i:(0, rank[i], -distance[i]) for i in feasible}
        keys.update({i:(1, values[i][1].get("r", {}).get("infeas", 0), sum(values[i][0])) for i in invalid})
        return sorted(range(len(population)), key=keys.get), keys
    population = [[rng.uniform(lo[i], hi[i]) for i in range(n)] for _ in range(pop)]
    history = []
    reference = None
    for generation in range(gen):
        _, keys = order(population)
        def parent():
            a, b = rng.choice(len(population), 2, replace=False)
            return population[a if keys[a] <= keys[b] else b]
        children = []
        while len(children) < pop:
            c1, c2 = _sbx_crossover(parent(), parent(), eta_c, lo, hi, rng, pc)
            children.extend([_polynomial_mutation(c, eta_m, mutation_probability, lo, hi, rng) for c in (c1,c2)])
        combined = population + children[:pop]
        indices, _ = order(combined)
        population = [combined[i] for i in indices[:pop]]
        record, usable = _generation_record(generation + 1, population, assess, len(evaluated))
        if track_hypervolume and usable and len(usable[0]) >= 2:
            if reference is None:
                reference = _reference_point(usable)
            front = _fast_non_dominated_sort(usable)[0]
            record["hv"] = round(_hypervolume([usable[i] for i in front], reference), 8)
        history.append(record)
        if progress and (generation == 0 or (generation + 1) % max(1, gen//20) == 0 or generation + 1 == gen):
            progress(generation + 1, gen)
        if should_stop is not None and should_stop(history):
            break
    return population, [(key, tuple(value[0])) for key, value in evaluated.items()], history


def _pareto(sorted_pairs):
    """从 [(vec, objs, info)] 中筛出非支配解并排序。"""
    filtered = []
    seen = set()
    for item in sorted_pairs:
        key = tuple(item[1])
        if key in seen or any(_dominates(other[1], item[1]) for other in filtered):
            continue
        filtered = [other for other in filtered if not _dominates(item[1], other[1])]
        filtered.append(item)
        seen.add(key)
    filtered.sort(key=lambda t: t[1][0])
    return filtered


def _knee_point(front):
    if not front:
        return None
    f1 = [obj[0] for _, obj, _ in front]
    f2 = [obj[1] for _, obj, _ in front]
    m1, M1 = min(f1), max(f1)
    m2, M2 = min(f2), max(f2)
    span1 = (M1 - m1) or 1e-9
    span2 = (M2 - m2) or 1e-9
    best, score = None, float("inf")
    for item, o1, o2 in zip(front, f1, f2):
        s = (o1 - m1) / span1 + (o2 - m2) / span2
        # 两个极端点的归一化和均为 1；平分时优先稳定性，不能由前沿排序决定。
        if s < score - 1e-12 or (abs(s - score) <= 1e-12 and
                                (best is None or o2 < best[1][1])):
            score, best = s, item
    return best


def robust_optimize(context, mode="multi", pop=60, gen=100, weight=0.5,
                    k_design=DEFAULT_K_DESIGN, k_constraint=DEFAULT_K_CONSTRAINT, seed=1, sigma_limits=None, progress=None,
                    pc=0.5, pm=None, eta_c=15.0, eta_m=20.0,
                    auto_stop=False, stall_generations=20, tolerance=0.001, enforce_objective_limits=False):
    """执行鲁棒优化，返回结果 dict。"""
    if mode not in ("multi", "weighted", "constraint"):
        raise ValueError("未知鲁棒优化策略")
    if auto_stop:
        if stall_generations < 1 or stall_generations >= gen:
            raise ValueError(f"停滞代数必须小于总代数（当前设定 {gen} 代），否则无法提前停止。")
        if not _np.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("收敛容差必须是有限正数。")
    context = dict(context)
    context.pop("sigma_limits", None)
    context['enforce_objective_limits'] = bool(enforce_objective_limits)
    objective_limit_names = [r.name for r in project_responses(context)
                             if not self_is_constraint(r) and response_uses_limits(context, r)]
    if enforce_objective_limits and not objective_limit_names:
        raise ValueError('尚未设置目标鲁棒性阈值，请先在【业务建模】定义目标响应的性能要求。')
    for response in project_responses(context):
        if response_uses_limits(context, response):
            validate_response_limits(response)
    if mode == "constraint":
        objective_names = {r.name for r in project_responses(context) if not self_is_constraint(r) or "目标" in r.kind}
        if not objective_names:
            raise ValueError("波动约束法需要至少一个目标响应。")
        limits = sigma_limits or {}
        if set(limits) != objective_names:
            raise ValueError("请为每个目标响应设置独立标准差上限：" + "、".join(sorted(objective_names)))
        limits = {name: float(value) for name, value in limits.items()}
        if any(not _np.isfinite(value) or value <= 0 for value in limits.values()):
            raise ValueError("标准差上限必须是有限正数，单位与响应一致。")
        context["sigma_limits"] = limits
    dinputs = design_inputs(context)
    if not dinputs:
        return {"error": "没有可优化的设计变量，请先在【业务建模】添加设计变量。"}
    dnames = [f.name for f in dinputs]
    lo = [de.factor_limits(f)[0] for f in dinputs]
    hi = [de.factor_limits(f)[1] for f in dinputs]
    # 响应角色来自业务建模，不能因选择 NSGA-II / 加权模式而把约束变成目标。
    use_cons = any(response_uses_limits(context, resp) for resp in project_responses(context))

    def evaluate(vec):
        xd = dict(zip(dnames, vec))
        r = evaluate_design(context, xd, k_design, weight, use_constraints=use_cons,
                            k_constraint=k_constraint)
        if mode == "weighted":
            obj = [weight * r["obj"][0] + (1.0 - weight) * r["obj"][1]]
        elif mode == "constraint":
            # Keep improving the mean even beyond the sampled response range;
            # clipped desirability would create false equal-optimum plateaus.
            means = {item["name"]: item["mu"] for item in r["objectives"]}
            losses = []
            for response in project_responses(context):
                if response.name not in means:
                    continue
                mu = means[response.name]
                scale = max(_response_scale(context["models"][response.name]), 1e-12)
                if response.feature == "望目":
                    ref = _response_ref(response)
                    if not isinstance(ref, tuple) or None in ref:
                        raise ValueError(f"{response.name} 缺少望目上下界。")
                    loss = abs(mu - (ref[0] + ref[1])/2)/scale
                else:
                    loss = (-mu if response.feature == "望大" else mu)/scale
                losses.append(loss)
            obj = [sum(losses)/len(losses)]
        else:
            obj = list(r["obj"])
        return obj, {"x": xd, "r": r}

    population, evaluated, history = nsga2(
        evaluate, lo, hi, pop=pop, gen=gen, seed=seed, progress=progress,
        pc=pc, pm=pm, eta_c=eta_c, eta_m=eta_m,
        should_stop=_stall_rule(mode, stall_generations, tolerance) if auto_stop else None,
        track_hypervolume=bool(auto_stop and mode == "multi"))
    pairs = []
    for vec_tuple, _obj in evaluated:
        vec = list(vec_tuple)
        obj, info = evaluate(vec)
        pairs.append((vec, obj, info))
    feasible = [t for t in pairs if t[2]["r"]["infeas"] <= 1e-8]
    # 最终推荐与前沿优先使用可行解，不能让低目标值抵消约束违反。
    candidates = feasible or pairs
    front_full = _pareto(feasible)

    # 选择推荐最优解
    if mode == "weighted":
        best = min(candidates, key=lambda t: t[1][0])
    elif mode == "constraint":
        best = min(candidates, key=lambda t: sum(t[1]))
    else:
        best = _knee_point(front_full) or min(candidates, key=lambda t: sum(t[1]))
    if not feasible:
        best = min(pairs, key=lambda t: (t[2]["r"]["infeas"], sum(t[1])))

    knee = _knee_point(front_full) if mode == "multi" else None
    recommended = best
    x_rec = recommended[2]["x"]
    r_rec = recommended[2]["r"]
    resp_detail = []
    objective_names = {item["name"] for item in r_rec["objectives"]}
    constraint_names = {item["name"] for item in r_rec["constraints"]}
    seen_responses = set()
    for item in r_rec["objectives"] + r_rec["constraints"]:
        if item["name"] in seen_responses:
            continue
        seen_responses.add(item["name"])
        role = ("目标+约束" if item["name"] in objective_names and item["name"] in constraint_names
                else "约束" if item["name"] in constraint_names else "目标")
        resp_detail.append({"name": item["name"], "mu": item["mu"],
                            "sigma": item["sigma"], "d": round(item["d"], 4), "role": role})

    result = {
        "enforce_objective_limits": bool(enforce_objective_limits),
        "objective_limit_names": objective_limit_names,
        "sigma_limits": context.get("sigma_limits", {}),
        "population_size": pop, "generations": gen, "seed": seed,
        "pc": pc, "pm": pm, "effective_pm": 1.0 / len(dnames) if pm is None else pm,
        "eta_c": eta_c, "eta_m": eta_m,
        "mode": mode, "weight": weight, "k_design": k_design,
        "k_constraint": k_constraint, "design_names": dnames,
        "input_sigmas": {f.name: _sigma_of_factor(f, k_design) for f in context["inputs"]},
        "objective_names": sorted(objective_names), "constraint_names": sorted(constraint_names),
        "feasible_count": len(feasible),
        "front": [{"x": _info["x"], "obj": [round(float(o), 6) for o in _obj],
                   "infeas": _info["r"]["infeas"]}
                  for _vec, _obj, _info in front_full],
        "front_scatter": [[float(t[1][0]), float(t[1][1] if len(t[1]) > 1 else 0.0)]
                          for t in feasible if len(t[1]) > 1],
        "knee": ({"x": knee[2]["x"], "obj": [round(float(o), 6) for o in knee[1]],
                  "infeas": knee[2]["r"]["infeas"]} if knee else None),
        "best": {"x": x_rec, "obj": [round(float(o), 6) for o in recommended[1]],
                 "mean_perf": round(r_rec["mean_perf"], 4),
                 "std_norm": round(r_rec["std_norm"], 4),
                 "infeas": r_rec["infeas"],
                 "sigma_constraints": r_rec["details"],
                 "responses": resp_detail},
        "evaluated_count": len(pairs),
        "history": history,
        "history_objectives": _history_labels(mode),
        "auto_stop": bool(auto_stop), "stall_generations": stall_generations,
        "tolerance": tolerance, "generations_run": len(history),
        "stop_reason": "stall" if len(history) < gen else "max_generations",
    }
    result["text"] = _robust_result_text(result)
    if objective_limit_names:
        result['text'] += '\n已启用目标鲁棒性独立约束（μ±kσ性能要求）：' + '、'.join(objective_limit_names)
    if mode == "constraint":
        result["text"] += "\n独立标准差约束（响应原单位）：" + "；".join(f"{n}: σ ≤ {v:g}" for n,v in context["sigma_limits"].items())
    return result


def _history_labels(mode):
    """目标名称按策略排列，供优化历程图表与报告使用。"""
    return {"multi": ["望性损失", "归一化标准差"],
            "weighted": ["加权目标和"],
            "constraint": ["望性损失"]}[mode]


def _robust_result_text(res):
    mode_names = {"multi": "帕累托前沿法",
                  "weighted": "加权和法",
                  "constraint": "波动约束法"}
    lines = [f"【{mode_names.get(res['mode'], res['mode'])}】",
             f"约束裕量系数 k={res['k_constraint']}，区间标准差换算系数 k={res['k_design']}",
             "输入标准差：" + "，".join(f"{n}={s:.6g}" for n, s in res.get("input_sigmas", {}).items()),
             "目标响应：" + "、".join(res.get("objective_names", [])),
             "约束响应：" + ("、".join(res.get("constraint_names", [])) or "无"),
             "标准差按响应数据极差归一化；均值和方差采用局部二阶近似。"]
    if res["mode"] == "weighted":
        lines.append(f"望性损失权重 λ={res['weight']}，波动权重={round(1 - res['weight'], 2)}")
    lines.append(f"评估解数量：{res['evaluated_count']}")
    if res.get("auto_stop"):
        reason = "达到停滞判据" if res.get("stop_reason") == "stall" else "达到最大代数"
        lines.append(f"停止方式：自动停止（{reason}），执行 {res.get('generations_run', res['generations'])}/"
                     f"{res['generations']} 代；判据为连续 {res['stall_generations']} 代改进 "
                     f"< {res['tolerance'] * 100:g}%")
    else:
        lines.append(f"停止方式：固定代数，执行 {res['generations']} 代")
    if res.get("history"):
        first, last = res["history"][0], res["history"][-1]
        trend = "；".join(
            f"{label} {start:.4g} → {end:.4g}"
            for label, start, end in zip(res.get("history_objectives") or [],
                                         first.get("best", []), last.get("best", [])))
        if trend:
            lines.append("收敛历程（每代最优值）：" + trend)
    lines.append(f"可行解数量：{res.get('feasible_count', 0)}；图中只显示可行解，不把约束罚项作为响应波动。")
    lines.append("")
    if res["mode"] == "multi" and res["front"]:
        lines.append(f"帕累托前沿解数量：{len(res['front'])}")
        knee = res.get("knee")
        if knee:
            lines.append(f"折中解：{knee['x']} ｜ 目标值 {knee['obj']}")
    best = res["best"]
    lines.append("")
    lines.append("★ 推荐优化设计（稳健设计点）" if res.get("feasible_count", 0)
                 else "尚未找到满足约束的设计；以下仅列出违例最小的候选点。")
    lines.append(f"  因子设置：{ {k: round(v, 5) for k, v in best['x'].items()} }")
    lines.append(f"  平均望性 {best['mean_perf']} ｜ 归一化标准差 {best['std_norm']} ｜ "
                 f"约束违例 {best['infeas']}")
    lines.append("  各响应（扰动后近似均值 μ、标准差 σ、望性 d）：")
    for item in best["responses"]:
        lines.append(f"    {item['name']}（{item.get('role', '目标')}）: μ={item['mu']:.4g}, σ={item['sigma']:.4g}, d={item['d']}")
    return "\n".join(lines)
