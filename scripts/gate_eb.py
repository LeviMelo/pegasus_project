"""The E_b gate (ARCHITECTURE §10.5): negative controls and δ_E, planted-latent power, the known positives.

Inputs are local: data/agent_context/prep.npz (counts, populations and census context per municipality, built
once by data/agent_context/prep.py from the gateway). Nothing is read from the national tables here.

    python scripts/heavy.py --label gate_eb -- python scripts/gate_eb.py [draws] [reps]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from pegasus_core import config, control, harness, surprise  # noqa: I001
from pegasus_core.scans import pairs

PREP = Path(__file__).resolve().parents[1] / "data" / "agent_context" / "prep.npz"
CONTEXT_SD = 0.05      # the census shares are complete counts: a constant, small sd (it cannot change ρ)


def inputs():
    z = np.load(PREP)
    c = lambda k: z["ctx_" + k]  # noqa: E731
    share = lambda n, d: np.where(c(d) > 0, c(n) / np.maximum(c(d), 1e-9), np.nan)  # noqa: E731
    ctx = {"sewer": share("households_sewer_network", "households"), "water": share("households_water_network", "households"),
           "no_bathroom": share("households_without_bathroom", "households"),
           "waste": share("households_waste_collected", "households"),
           "literacy": share("persons_15_plus_literate", "persons_15_plus"),
           "log_gdp_pc": np.log(c("gdp") * 1000 / np.where(c("pop2021") > 0, c("pop2021"), np.nan))}
    for k, v in ctx.items():          # z-scored; a missing value takes the mean
        ctx[k] = np.where(np.isfinite(v), (v - np.nanmean(v)) / np.nanstd(v), 0.0)
    d0, births = z["d0"], z["births"]
    mu_i = births * d0.sum() / births.sum()
    PA, YA = z["PA"], z["YA"]
    band = np.minimum(np.arange(81) // 5, 16)
    ag = lambda A: np.stack([A[..., band == b].sum(-1) for b in range(17)], -1)  # noqa: E731
    Pb, Yb = ag(PA), ag(YA)
    mu_d = (Pb * (Yb.sum(0) / np.maximum(Pb.sum(0), 1e-9))[None]).sum((2, 3)).sum(1)
    out = {"infant_mortality": (d0, mu_i), "diarrhoea": (Yb.sum((2, 3)).sum(1), mu_d)}
    return z["places"], ctx, out


def effect(y: np.ndarray, mu: np.ndarray):
    _, b, sd, tau = surprise.refit_place(y[:, None], mu[:, None], np.full((len(y), 1), np.inf), np.ones((1, 1)))
    return b[:, 0], sd[:, 0], float(tau[0])


def main(draws: int = 200, reps: int = 50) -> dict:
    t0 = time.time()
    places, ctx, outcomes = inputs()
    test_basis = pairs.MoranBasis(places)                  # the graph that tests
    gen_basis = pairs.MoranBasis(places, "knn8")           # another graph generates the negatives
    print(f"bases {time.time() - t0:.0f}s", flush=True)
    eff = {k: effect(*v) for k, v in outcomes.items()}
    result: dict = {"draws": draws, "reps": reps, "test_graph": pairs.BASIS_GRAPH, "negative_graph": "knn8"}

    families, families_adj = {}, {}
    zc = ctx["log_gdp_pc"][:, None]
    adjustable = {k: v for k, v in ctx.items() if k != "log_gdp_pc"}
    for name, (b, s, _) in eff.items():
        others = {f"outcome:{o}": (eff[o][0], eff[o][1]) for o in eff if o != name}     # another outcome's noisy effects
        for tag, cx, cxa in (("census", ctx, adjustable), ("outcome", others, others)):
            families[f"{name}|{tag}"] = list(harness.pair_negatives((b, s), cx, test_basis, gen_basis, draws,
                                                                    CONTEXT_SD).values())
            families_adj[f"{name}|{tag}"] = list(harness.pair_negatives((b, s), cxa, test_basis, gen_basis, draws,
                                                                        CONTEXT_SD, Z=zc).values())
    for j in ctx:       # the hardest class: two unweighted smooth fields (a census field against the others)
        rest = {k: v for k, v in ctx.items() if k != j}
        families.setdefault("census|census", []).extend(harness.pair_negatives((ctx[j], np.full(len(ctx[j]), CONTEXT_SD)), rest,
                                                                     test_basis, gen_basis, draws, CONTEXT_SD).values())
        if j != "log_gdp_pc":
            families_adj.setdefault("census|census", []).extend(harness.pair_negatives(
                (ctx[j], np.full(len(ctx[j]), CONTEXT_SD)), {k: v for k, v in rest.items() if k != "log_gdp_pc"},
                test_basis, gen_basis, draws, CONTEXT_SD, Z=zc).values())
    result["delta_E"] = harness.calibrate_delta(families)
    result["delta_E|Z"] = harness.calibrate_delta(families_adj)
    print("delta_E", result["delta_E"], "\ndelta_E|Z", result["delta_E|Z"], f"{time.time() - t0:.0f}s", flush=True)

    b, s, tau = eff["infant_mortality"]
    mu = outcomes["infant_mortality"][1]
    result["power"] = {name: harness.pair_power(mu, 1 / np.sqrt(tau), b, ctx["literacy"], latent, gen_basis, test_basis,
                                                rhos=(0.15, 0.3, 0.45, 0.6), reps=reps)
                       for name, latent in (("latent_smooth(literacy)", ctx["literacy"]), ("latent_local(infant_mortality)", b))}
    print("power", json.dumps(result["power"]), f"{time.time() - t0:.0f}s", flush=True)

    ledger = control.Ledger(config.home() / "harness" / "ledger")
    rows = []
    for name, (b, s, _) in eff.items():
        for adjust in (False, True):
            effects = {name: (b, s)} | {k: (v, np.full(len(v), CONTEXT_SD)) for k, v in ctx.items()
                                        if not (adjust and k == "log_gdp_pc")}
            for p in pairs.between(effects, test_basis, ledger, f"harness:known_positive:{name}:E_b{'|logGDP' if adjust else ''}",
                                   Z=zc if adjust else None):
                if name in (p.x, p.y):
                    rows.append({"outcome": name, "context": p.y if p.x == name else p.x, "adjusted": adjust,
                                 "rho": p.rho, "n_eff": p.n_eff, "p": p.p, "p_at_0": float(pairs.minimum_effect_p(p.rho, p.n_eff, 0.0)),
                                 "p_at_0.1": float(pairs.minimum_effect_p(p.rho, p.n_eff, 0.1))})
    result["positives"] = rows
    for r in rows:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
    harness.record("gate_eb", {"draws": draws, "reps": reps, "min_effect": pairs.MIN_EFFECT}, result)
    return result


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
