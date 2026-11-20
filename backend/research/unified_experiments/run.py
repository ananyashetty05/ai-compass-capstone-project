"""Offline evidence for the unified algorithm. Run:  python -m research.unified_experiments.run

PROTOCOL (fixed before the test run): the missing-metric prior and the penalty were chosen on DEV seeds 0-199 only (sweep recorded in the report).
All numbers below use TEST seeds 1000-2999 and no parameter is tuned on them. The seeds 1000-2999 were also used by the earlier V2 study for V1-vs-V2
comparisons; nothing here was selected using them.

WHAT THIS CAN AND CANNOT SHOW. The generator is ours: a latent true utility per (product, objective) is observed through noisy "evidence" of several
quality levels. Lower regret here means the formula recovers the generator's best product more often. It does NOT show the real product ranking is
"correct": no independent labels of which product is best for a real query exist. The formulas below are replicas of the production formulas;
the production code's structural properties (exact order, removal invariance, determinism) are tested in tests/ against the real scorer.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

OBJ = ("quality", "cost", "latency", "reliability", "risk", "preference_alignment")
T0, TU, T1, T2, T3 = "unknown", "editorial", "rubric", "documented", "measured"
TIERS, TP = [T0, TU, T1, T2, T3], [0.20, 0.30, 0.20, 0.20, 0.10]
SIG = {TU: 0.15, T1: 0.10, T2: 0.04, T3: 0.02}
CONF = {TU: 0.5, T1: 0.5, T2: 0.85, T3: 1.0}
RHO, EPS_V1 = 0.25, 0.005
PRIOR_V1, PRIOR_UNIFIED = 0.0, 0.5            # value an unknown metric is scored as, at zero confidence (then minus RHO)
OUT = Path(__file__).resolve().parents[1] / "results" / "unified_experiments.json"


def clip(x: float) -> float:
    return max(0.0, min(1.0, x))


class Cand:
    __slots__ = ("id", "order", "v", "tier")

    def __init__(self, id, order, v, tier):
        self.id, self.order, self.v, self.tier = id, order, v, tier


class Inst:
    def __init__(self, seed, truth, cands, w, ok):
        self.seed, self.truth, self.cands, self.w, self.ok = seed, truth, cands, w, ok

    def true_u(self, i):
        return math.fsum(self.w[d] * self.truth[i][d] for d in OBJ)


def gen(seed: int, *, n: int = 25, inflated: bool = False, extra_editorial_noise: float = 0.0, mnar_shift: float = 0.0) -> Inst:
    rnd = random.Random(seed)
    ids = [f"m{i:02d}" for i in range(n)]
    truth = {i: {d: rnd.betavariate(2, 2) for d in OBJ} for i in ids}
    g = [rnd.gammavariate(1.0, 1.0) for _ in OBJ]; s = sum(g)  # noqa: E702
    w = {d: x / s for d, x in zip(OBJ, g)}
    prov = {i: rnd.randrange(5) for i in ids}
    lenient = {p for p in range(5) if rnd.random() < 0.30} if inflated else set()
    cands = []
    for k, i in enumerate(ids):
        v, t = {}, {}
        for d in OBJ:
            tier = rnd.choices(TIERS, TP)[0]
            t[d] = tier
            if tier == T0:
                v[d] = None
                if mnar_shift:
                    truth[i][d] = clip(truth[i][d] - mnar_shift)       # products with unknown data are truly worse (missing-not-at-random)
            else:
                x = truth[i][d] + rnd.gauss(0, SIG[tier])
                if tier == TU and prov[i] in lenient:
                    x += 0.20
                if tier == TU and extra_editorial_noise:
                    x += rnd.gauss(0, extra_editorial_noise)
                v[d] = clip(x)
        cands.append(Cand(i, k, v, t))
    ok = {i: (rnd.random() < 0.6) if rnd.random() < 0.5 else True for i in ids}
    return Inst(seed, truth, cands, w, ok)


# ── algorithms (formula replicas) ──────────────────────────────────────────────────────────────────────────────────
def robust_scores(cands: Sequence[Cand], w: Dict[str, float], prior: float) -> Dict[str, float]:
    out = {}
    for c in cands:
        s = 0.0
        for d in OBJ:
            x, t = c.v.get(d), c.tier[d]
            known = x is not None and t != T0
            eff, conf = (x, CONF[t]) if known else (prior, 0.0)
            s += w[d] * max(0.0, eff - (1 - conf) * RHO)
        out[c.id] = s
    return out


def order_exact(cands, sc):
    return [c.id for c in sorted(cands, key=lambda c: (-round(sc[c.id], 12), c.order, c.id))]


def order_window(cands, sc, eps):
    """V1 as it was: everything within eps of the LEADER is re-ordered by list order."""
    ordered = sorted(cands, key=lambda c: (-round(sc[c.id], 12), c.order, c.id))
    top = sc[ordered[0].id]
    tied = sorted([c for c in ordered if top - sc[c.id] < eps], key=lambda c: (c.order, c.id))
    return [c.id for c in tied + [c for c in ordered if c not in tied]]


ALGS: Dict[str, Callable] = {
    "R1_strongest_only": lambda cs, w: [c.id for c in sorted(cs, key=lambda c: (-(c.v.get("quality") or 0.0), c.order, c.id))],
    "R2_cheapest_only": lambda cs, w: [c.id for c in sorted(cs, key=lambda c: (-(c.v.get("cost") or 0.0), c.order, c.id))],
    "R3_list_order": lambda cs, w: [c.id for c in sorted(cs, key=lambda c: (c.order, c.id))],
    "V1_original (tie window, unknown=0)": lambda cs, w: order_window(cs, robust_scores(cs, w, PRIOR_V1), EPS_V1),
    "ablation: exact order only": lambda cs, w: order_exact(cs, robust_scores(cs, w, PRIOR_V1)),
    "ablation: prior only": lambda cs, w: order_window(cs, robust_scores(cs, w, PRIOR_UNIFIED), EPS_V1),
    "UNIFIED (exact order + neutral prior)": lambda cs, w: order_exact(cs, robust_scores(cs, w, PRIOR_UNIFIED)),
}
BASE, NEW = "V1_original (tie window, unknown=0)", "UNIFIED (exact order + neutral prior)"
SETTINGS = {
    "editorial unbiased": {},
    "editorial inflated (+0.20 for 30% of providers)": {"inflated": True},
    "editorial noisy (extra sd 0.25)": {"extra_editorial_noise": 0.25},
    "unknown data truly worse (MNAR, -0.20)": {"mnar_shift": 0.20},
}


def regret(inst: Inst, pick: str, eligible: Sequence[str]) -> float:
    vals = {i: inst.true_u(i) for i in eligible}
    hi, lo = max(vals.values()), min(vals.values())
    return (hi - vals[pick]) / (hi - lo) if hi > lo else 0.0


def boot_ci(diffs: List[float], n: int = 2000, seed: int = 1) -> List[float]:
    rnd = random.Random(seed)
    m = len(diffs)
    means = sorted(statistics.fmean(rnd.choice(diffs) for _ in range(m)) for _ in range(n))
    return [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)]


def run_setting(seeds, **kw) -> Dict:
    reg = {k: [] for k in ALGS}
    top1 = {k: 0 for k in ALGS}
    used = 0
    for sd in seeds:
        inst = gen(sd, **kw)
        el = [c for c in inst.cands if inst.ok[c.id]]
        if len(el) < 2:
            continue
        used += 1
        best = max(el, key=lambda c: inst.true_u(c.id)).id
        for k, f in ALGS.items():
            pick = f(el, inst.w)[0]
            reg[k].append(regret(inst, pick, [c.id for c in el]))
            top1[k] += pick == best
    diffs = [a - b for a, b in zip(reg[BASE], reg[NEW])]
    return {"instances": used,
            "algorithms": {k: {"mean_regret": round(statistics.fmean(v), 4), "top1_rate": round(top1[k] / used, 4)} for k, v in reg.items()},
            "paired_regret_reduction_V1_minus_UNIFIED": {"mean": round(statistics.fmean(diffs), 4), "ci95": boot_ci(diffs),
                                                         "share_of_instances_improved": round(sum(d > 1e-12 for d in diffs) / used, 4), "share_worse": round(sum(d < -1e-12 for d in diffs) / used, 4)}}


def removal_invariance(seeds) -> Dict:
    """Remove each NON-winning candidate in turn (including the one with the top raw score, which is what breaks a leader-anchored tolerance window). A sound ranking keeps the same winner."""
    res = {}
    for name in (BASE, NEW):
        trials = viol = 0
        for sd in seeds:
            inst = gen(sd)
            el = [c for c in inst.cands if inst.ok[c.id]]
            if len(el) < 3:
                continue
            f = ALGS[name]
            win = f(el, inst.w)[0]
            for victim in [c for c in el if c.id != win]:
                trials += 1
                viol += f([c for c in el if c.id != victim.id], inst.w)[0] != win
        res[name] = {"trials": trials, "winner_changed": viol, "rate": round(viol / trials, 5)}
    return res


def main() -> None:
    t0 = time.time()
    quick = "--quick" in sys.argv
    test = range(1000, 1000 + (300 if quick else 2000))
    out = {"protocol": __doc__.split("WHAT THIS")[0].strip(), "claim_scope": "Synthetic evidence about formula behaviour only; no claim about real-world product correctness.",
           "test_seeds": [test.start, test.stop - 1], "settings": {k: run_setting(test, **kw) for k, kw in SETTINGS.items()},
           "removal_invariance": removal_invariance(test), "runtime_seconds": None}
    out["runtime_seconds"] = round(time.time() - t0, 1)
    if not quick:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, indent=1))
    for k, v in out["settings"].items():
        p = v["paired_regret_reduction_V1_minus_UNIFIED"]
        print(f"{k}: V1 {v['algorithms'][BASE]['mean_regret']} -> UNIFIED {v['algorithms'][NEW]['mean_regret']}  paired reduction {p['mean']} CI95 {p['ci95']}  improved {p['share_of_instances_improved']} worse {p['share_worse']}")
    print(json.dumps(out["removal_invariance"], indent=1))


if __name__ == "__main__":
    main()
