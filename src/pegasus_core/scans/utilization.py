"""Hospital use: the factor common to the SIH chapters' place effects, and what it correlates with (evaluation
2026-10-05, utilization).

The extraction that the dependency map needs (``maps.factors``) lives in maps.py. Here are the checks around it: the
number of factors against Moran-randomised surrogates (parallel analysis under ADR-0005's null: each field keeps its
own spatial spectrum, the fields are made independent), and the correlation of a factor with the context fields
under the same E_b null.
"""

from __future__ import annotations

import numpy as np

from . import maps, pairs


def parallel_analysis(inp: maps.MapInputs, gen_basis: pairs.MoranBasis, worlds: int = 200, seed: tuple = ("utilization",)
                      ) -> np.ndarray:
    """Eigenvalues [worlds, F_SIH] of the weighted correlation matrix of the SIH fields when each is replaced by its own
    Moran-randomised surrogate (own signs, spectrum, sd and missingness kept): the spread of the eigenvalues of a
    set of spatially structured fields that share nothing."""
    from .. import config
    rng = np.random.default_rng(config.seed(*seed, "parallel"))
    idx = [i for i, g in enumerate(inp.groups) if g in maps.care(inp)]
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
