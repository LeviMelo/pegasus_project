"""Fellner-Schall with the full Hessian against the block-diagonal Poisson Fisher diagonal.

Usage: python scripts/measure_laplace_fs.py ix|dengue [DRAWS] [DEVICE]

At the fitted MAP, one update of every tau by (a) the code's FS (Poisson Fisher diagonal per effect),
(b) the full Poisson Hessian (draws), (c) the full negative-binomial information (draws). The MAP is not
refitted: the proposals show the direction and size of the correction the full Hessian would make.
Output: data/logs/laplace_fs_<mode>.json.
"""
import json
import sys
import time

import numpy as np
import torch

from pegasus_core import laplace, monolith

mode = sys.argv[1]
S = int(sys.argv[2]) if len(sys.argv) > 2 else 24
device = sys.argv[3] if len(sys.argv) > 3 else "cpu"
if mode == "ix":
    m = monolith.Monolith.load("SIM.DO", "death", "IX", range(2010, 2024), "knn6", device=device)
else:
    m = monolith.Monolith.load("SINAN-DENG", "probable_case", "*", range(2010, 2024), "contiguity",
                               device=device, grain="month")
print("loaded; phi", m.phi, flush=True)
out = {"phi": m.phi}

taus0 = {k: c.tau for k, c in m.components.items()}
m._update_taus()
diag = {k: c.tau for k, c in m.components.items()}
diag_trace = {row[0]: row[4] * row[3] for row in m.trace_log[-len(m.components):]}   # tau * tr(H^-1 Q)
for k, c in m.components.items():
    c.tau = taus0[k]

res = {}
for label, poisson in (("poisson_full", True), ("nb_full", False)):
    t = time.time()
    post = laplace.Posterior(m, poisson=poisson)
    post.sample(S)
    res[label] = post.fellner_schall()
    its = [s.iterations for s in post.solves]
    print(f"{label}: {S} draws in {time.time() - t:.0f}s, CG iterations mean {np.mean(its):.0f} max {max(its)}", flush=True)
    out[label + "_seconds"] = time.time() - t

print(f"{'component':8} {'tau':>10} {'FS diag':>10} {'Poisson full':>13} {'NB full':>10}   rank  tr(diag)  tr(P full)  tr(NB full)")
for k, c in m.components.items():
    if c.rank <= 0:
        continue
    p, n = res["poisson_full"][k], res["nb_full"][k]
    print(f"{k:8} {taus0[k]:10.3g} {diag[k]:10.3g} {p['proposal']:13.3g} {n['proposal']:10.3g}   {c.rank:6.0f} "
          f"{diag_trace.get(k, float('nan')):9.1f} {p['trace']:9.1f} {n['trace']:9.1f}")
    out[k] = {"tau": taus0[k], "fs_diag": diag[k], "poisson_full": p, "nb_full": n}
with open(f"data/logs/laplace_fs_{mode}.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, default=float)
