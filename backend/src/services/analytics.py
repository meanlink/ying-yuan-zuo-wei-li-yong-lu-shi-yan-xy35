from collections import defaultdict
import random
from statistics import mean

def _rate(rows):
    return sum(1 for r in rows if r["sold"]) / len(rows) if rows else 0.0

def bootstrap_difference(control, treatment, iterations=1200, seed=20261121):
    rng = random.Random(seed)
    if not control or not treatment:
        raise ValueError("两个实验组都需要至少一条票务观测")
    observed = _rate(treatment) - _rate(control)
    diffs = []
    for _ in range(iterations):
        c = [control[rng.randrange(len(control))] for _ in control]
        t = [treatment[rng.randrange(len(treatment))] for _ in treatment]
        diffs.append(_rate(t) - _rate(c))
    diffs.sort()
    low = diffs[int(iterations * 0.025)]
    high = diffs[int(iterations * 0.975) - 1]
    return {"difference": observed, "ci_low": low, "ci_high": high, "iterations": iterations, "seed": seed}

def stratified_effect(rows):
    strata = defaultdict(lambda: {"control": [], "treatment": []})
    for row in rows:
        strata[row["stratum"]][row["group"]].append(row)
    effects = []
    weights = []
    detail = []
    for stratum, groups in sorted(strata.items()):
        c = groups["control"]
        t = groups["treatment"]
        if not c or not t:
            continue
        effect = _rate(t) - _rate(c)
        weight = len(c) + len(t)
        effects.append(effect * weight)
        weights.append(weight)
        detail.append({"stratum": stratum, "control_n": len(c), "treatment_n": len(t), "effect": effect})
    if not weights:
        raise ValueError("没有同时包含两个实验组的厅次分层")
    return {"effect": sum(effects) / sum(weights), "strata": detail}

def balance_ratio(rows):
    grouped = defaultdict(lambda: {"control": 0, "treatment": 0})
    for row in rows:
        grouped[row["stratum"]][row["group"]] += 1
    ratios = []
    for g in grouped.values():
        if g["control"] and g["treatment"]:
            ratios.append(min(g.values()) / max(g.values()))
        else:
            ratios.append(0)
    return min(ratios) if ratios else 0.0
