"""Hospital use: the factor common to the SIH chapters' place effects, and what it correlates with (evaluation
2026-10-05, utilization).

The extraction that the dependency map needs (``maps.factors``) lives in maps.py. Here are the checks around it: the
SIH chapters as a place × year × chapter tensor with its expectation (the input of CP-APR, ``patterns.fit``), the
number of factors against Moran-randomised surrogates (parallel analysis under ADR-0005's null: each field keeps its
own spatial spectrum, the fields are made independent), and the correlation of a factor with the context fields
under the same E_b null.
"""

from __future__ import annotations

import numpy as np

from .. import store
from . import map_inputs, maps, pairs


def tensor(inp: maps.MapInputs) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Observed and expected SIH admissions (survivors) by place × year × chapter [U, T, F] for the SIH fields of
    ``inp``, the expectation indirectly standardised on the national rates by year × sex × band (the map's own,
    ``map_inputs``), cached in the store."""
    years = inp.meta["years"]
    key = {"what": "sih_tensor", "years": years, "first": int(inp.places[0]), "n": len(inp.places), "v": 1}
    names = [n for n, g in zip(inp.names, inp.groups, strict=True) if g == "SIH"]
    hit = store.get_arrays("maps", key)
    if hit is not None and hit["names"].tolist() == names:
        return hit["y"], hit["mu"], names
    PA = map_inputs._population(inp.places, years)
    counts = map_inputs._chapter_counts(("SIH-RD", "hospitalisation"), inp.places, years, True)
    y = np.zeros((len(inp.places), len(years), len(names)))
    mu = np.zeros_like(y)
    for f, n in enumerate(names):
        Y = counts[n.split(":")[1]]
        rate = Y.sum(0) / np.maximum(PA.sum(0), 1e-9)
        y[:, :, f] = Y.sum((2, 3))
        mu[:, :, f] = (PA * rate[None]).sum((2, 3))
    store.put_arrays("maps", key, {"y": y, "mu": mu, "names": np.array(names)})
    return y, mu, names


def parallel_analysis(inp: maps.MapInputs, gen_basis: pairs.MoranBasis, worlds: int = 200, seed: tuple = ("utilization",)
                      ) -> np.ndarray:
    """Eigenvalues [worlds, F_SIH] of the weighted correlation matrix of the SIH fields when each is replaced by its own
    Moran-randomised surrogate (own signs, spectrum, sd and missingness kept): the spread of the eigenvalues of a
    set of spatially structured fields that share nothing."""
    from .. import config
    rng = np.random.default_rng(config.seed(*seed, "parallel"))
    idx = [i for i, g in enumerate(inp.groups) if g == maps.UTILIZATION_GROUP]
    out = []
    for _ in range(worlds):
        B = inp.B.copy()
        sub = B[:, idx]
        miss = ~np.isfinite(sub)
        B[:, idx] = np.where(miss, np.nan, gen_basis.randomise(np.where(miss, 0.0, sub), rng))
        world = maps.MapInputs(inp.places, inp.names, inp.groups, inp.labels, B, inp.SD, inp.overlap, inp.meta)
        out.append(maps.factors(world, 1)[2]["eigenvalues"])
    return np.array(out)


def rank1_share(R: np.ndarray, vals: np.ndarray, vecs_load: np.ndarray, k: int) -> float:
    """Share of the squared off-diagonal of R that k factors reproduce."""
    F = len(R)
    L = vecs_load[:, :k] * np.sqrt(vals[:k])
    off = ~np.eye(F, dtype=bool)
    return float(1 - ((R - L @ L.T)[off] ** 2).sum() / (R[off] ** 2).sum())
