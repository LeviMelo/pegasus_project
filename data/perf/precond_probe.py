"""Newton-CG at the stored fit's tau's from a cold start, one configuration per process.

python data/perf/precond_probe.py DATASET EVENT BLOCK FIRST LAST --precond diag|block --forcing 0.5 [--steps N] [--grain month]
Prints every Newton step (objective, gradient norm, CG iterations, step length, decrease) and the total CG iterations."""
import argparse
import time

import numpy as np

from pegasus_core import graphs, monolith

ap = argparse.ArgumentParser()
ap.add_argument("dataset")
ap.add_argument("event")
ap.add_argument("block")
ap.add_argument("first", type=int)
ap.add_argument("last", type=int)
ap.add_argument("--grain", default="year")
ap.add_argument("--steps", type=int, default=30)
ap.add_argument("--precond", default="diag")
ap.add_argument("--forcing", type=float, default=0.5)
a = ap.parse_args()
data = monolith.assemble(a.dataset, a.event, a.block, range(a.first, a.last + 1), grain=a.grain)
ref = monolith.Monolith.load(a.dataset, a.event, a.block, range(a.first, a.last + 1), grain=a.grain)
m = monolith.Monolith(data, graphs.graph(data.places, "contiguity"), "contiguity")
for k, c in m.components.items():
    c.tau = ref.components[k].tau
m.precond, m.forcing = a.precond, a.forcing
m._initialise()
t0 = time.process_time()
steps = m._fit_mean(a.steps)
cpu = time.process_time() - t0
for i, (f0, gn, its, step, dec) in enumerate(m.newton_log):
    print(f"  step {i:2d}: f {f0 * m.scale:14.3f} |g| {gn:9.2e} cg {its:3d} step {step:5.3f} decrease {dec * m.scale:10.3f}")
print(f"{a.precond} forcing {a.forcing}: {steps} Newton steps, {m.cg_iterations} CG iterations, cpu {cpu:.0f}s, "
      f"objective {float(m.objective()) * m.scale:.4f}, converged {m.refit_converged}", flush=True)
mu, _ = m.expected(np.arange(len(data.leaves)))
np.save(f"data/perf/out/precond_{a.precond}_{a.forcing}.npy", mu)
