"""Measured runtime of ER-PCR ranking on this machine (no network, no database, no provider calls).
Run from backend/:  python research/er_pcr_benchmark.py
Reports wall-clock only; numbers are for this machine and are not a latency guarantee."""
import os, random, statistics, sys, time
os.environ.setdefault("JWT_SECRET", "benchmark-only")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.engine_helpers import MEASURED_PROV, mk, prefs, profile
from app.services.routing_engine import filtering, pipeline, scoring

Q = "Write a Python function that sorts a list of records."
P = profile(Q)
OV = {"quality": 5, "cost": 5, "latency": 0.5, "reliability": 0.5, "risk": 0.5}


def models(n):
    r = random.Random(7)
    return [mk(f"m{i:03d}", q=r.random(), inp=r.random() * 20, out=r.random() * 60, avg_latency=r.random() * 30, rel=r.random(), prov=MEASURED_PROV) for i in range(n)]


def time_ms(fn, reps):
    xs = []
    for _ in range(reps):
        t = time.perf_counter(); fn(); xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return statistics.median(xs), xs[int(0.95 * (len(xs) - 1))]


for n in (10, 50, 200):
    ms = models(n)
    pr = prefs(P, weight_overrides=OV)
    def rank_only():
        passing, _ = filtering.filter_candidates(ms, P, pr)
        rows, _ = scoring.score_candidates(passing, P, pr)
        scoring.select(rows, pr, P)
    def full():
        pipeline.run(pipeline.PipelineRequest(query=Q, weight_overrides=OV), saved_weights=None, user_id=None, catalog_loader=lambda t, m: (list(ms), []),
                     learning_loader=lambda u, i: {}, observed_loader=lambda i: {})
    a = time_ms(rank_only, 200); b = time_ms(full, 50)
    print(f"candidates={n:4d}  filter+score+select  median {a[0]:7.2f} ms  p95 {a[1]:7.2f} ms | full pipeline (understanding..explanation)  median {b[0]:7.2f} ms  p95 {b[1]:7.2f} ms")
