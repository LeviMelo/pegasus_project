"""Simulation-based calibration of the mean fit and its Laplace posterior (ARCHITECTURE §10.6.1; Talts et al. 2018,
the posterior variant of Modrák et al. 2023): truths drawn from a fitted block's exact Laplace posterior, counts
simulated from them, the mean refitted at the same strengths, and each tracked quantity's rank among the refit's
posterior draws recorded. Uniform ranks mean the solver and the Laplace approximation are calibrated at fixed τ.

    python scripts/sbc.py SIM.DO death XIII 2010 2021 --replicates 100 --draws 99

Writes data/probes/sbc/<dataset>_<block>_<first>_<last>.json (ranks per quantity, the χ² of their histograms).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import torch
from scipy import stats

from pegasus_core import graphs, laplace, monolith, solver

parser = argparse.ArgumentParser()
parser.add_argument("dataset")
parser.add_argument("event")
parser.add_argument("block")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("--replicates", type=int, default=100)
parser.add_argument("--draws", type=int, default=99)
parser.add_argument("--seed", type=int, default=20261006)
args = parser.parse_args()


def tracked(m: monolith.Monolith, x: dict[str, torch.Tensor]) -> dict[str, float]:
    """The scalars whose ranks are read: the intercept, every group level, the first and last years' overall course,
    three ages of the overall profile, the overall place effect at the five largest places, and each group's expected
    total (a nonlinear functional the effects' marginals do not show)."""
    out = {"b0": float(x["b0"][0])}
    for k, g in enumerate(m.data.groups):
        out[f"th_grp[{g}]"] = float(x["th_grp"][0][k])
    T = x["h_all"].shape[1]
    out["h_all[first]"], out["h_all[last]"] = float(x["h_all"][0][0]), float(x["h_all"][0][T - 1])
    for g in (0, m.nB // 2, m.nB - 1):
        out[f"f_all[{g}]"] = float(x["f_all"][0][g])
    big = np.argsort(-m.data.N.sum(axis=(1, 2)))[:5]
    for u in big:
        out[f"place[{int(m.data.places[u])}]"] = float(x["s_all"][0][u] + x["v_all"][0][u])
    with torch.no_grad():
        for k, g in enumerate(m.data.groups):
            leaves = np.nonzero(m.data.leaf_group == k)[0]
            out[f"total[{g}]"] = float(np.log(m.expected(leaves, x=x)[0].sum()))
    return out


def simulate(m: monolith.Monolith, x: dict[str, torch.Tensor], rng: np.random.Generator) -> monolith.BlockData:
    """Poisson counts from the effects ``x`` over every admissible cell, streamed one leaf at a time."""
    d = m.data
    parts = []
    with torch.no_grad():
        lp = m._leaf_place(x).cpu().numpy()                                   # [E, U]
        lin = (m._time(x)[:, None, :] + (x["s_all"][0] + x["v_all"][0])[None, :, None]
               + m._grp_place(x)[:, :, None])
        base = torch.exp(lin).cpu().numpy()                                   # [K, U, T]
        prof = m._prof(x).cpu().numpy()                                       # [K, G]
    N = d.N
    for e in range(len(d.leaves)):
        k = int(d.leaf_group[e])
        mu = lp[e][:, None, None] * base[k][:, :, None] * N * prof[k][None, None, :]
        y = rng.poisson(mu)
        u, t, g = np.nonzero(y)
        parts.append((np.full(len(u), e), u, t, g, y[u, t, g].astype(float)))
    e, u, t, g, y = (np.concatenate(z) for z in zip(*parts, strict=True))
    return dataclasses.replace(d, e=e, u=u, t=t, g=g, y=y, key={**d.key, "sbc": True})


def main() -> None:
    rng = np.random.default_rng(args.seed)
    data = monolith.assemble(args.dataset, args.event, args.block, range(args.first, args.last + 1))
    graph = graphs.graph(data.places, "contiguity")
    m = monolith.Monolith(data, graph, "contiguity")
    t0 = time.time()
    m.fit(outer=40, mean_tol=1.0, log=lambda s: None)
    print(f"fitted {args.block}: {time.time() - t0:.0f}s, {len(m.history)} outers", flush=True)
    taus = {n: c.tau for n, c in m.components.items()}
    truths = laplace.Posterior(m, poisson=True).sample(args.replicates, seed=args.seed)
    ranks: dict[str, list[int]] = {}
    for r, x_true in enumerate(truths):
        t1 = time.time()
        sim = simulate(m, x_true, rng)
        m2 = monolith.Monolith(sim, graph, "contiguity")
        for n, c in m2.components.items():
            c.tau = taus[n]
        with torch.no_grad():
            for n, v in m.params.items():
                m2.params[n].copy_(v)                                         # start at the fit's MAP
        solver.fit_mean(m2, iterations=30, loglik_tol=1e-3)
        draws = laplace.Posterior(m2, poisson=True).sample(args.draws, seed=args.seed + r + 1)
        truth = tracked(m2, x_true)
        drawn = [tracked(m2, x) for x in draws]
        for q, val in truth.items():
            ranks.setdefault(q, []).append(int(sum(dq[q] < val for dq in drawn)))
        print(f"replicate {r}: {time.time() - t1:.0f}s, {int(sim.y.sum())} events", flush=True)
    bins = 10
    out = {"dataset": args.dataset, "block": args.block, "years": [args.first, args.last],
           "replicates": args.replicates, "draws": args.draws, "taus": taus, "quantities": {}}
    for q, rk in ranks.items():
        hist = np.histogram(rk, bins=bins, range=(0, args.draws + 1))[0]
        chi2 = stats.chisquare(hist)
        out["quantities"][q] = {"ranks": rk, "histogram": hist.tolist(), "chi2_p": float(chi2.pvalue)}
    path = Path("data/probes/sbc") / f"{args.dataset}_{args.block}_{args.first}_{args.last}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    ps = sorted((v["chi2_p"], q) for q, v in out["quantities"].items())
    print("lowest χ² p:", ps[:5], flush=True)


if __name__ == "__main__":
    main()
