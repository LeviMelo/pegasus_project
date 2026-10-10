"""Capture fields (ARCHITECTURE §5.2, §6.4; BACKLOG 2.7, 6.4): how many events no system recorded, from the overlap of
the systems that recorded some, by log-linear multiple-systems estimation.

k systems each record some of the events (a congenital toxoplasmosis case notified in SINAN, admitted in SIH, dead in
SIM); linked, every recorded event has an inclusion pattern (1, 0, 1). The 2^k − 1 observed pattern counts are fitted by
Poisson log-linear models (Fienberg 1972; Bishop, Fienberg & Holland 1975, ch. 6): main effects for each system plus a
subset of the pairwise interactions, which carry the dependence between systems (a death certificate is likelier for
an admitted child). The unobserved cell (0, …, 0) is the model's prediction there, and the total N̂ = n + n̂₀.

Which dependences hold is not known, so no single model is chosen: every hierarchical model with main effects and any
set of pairwise terms is fitted, and N̂ is averaged over them by Akaike weight, its variance the unconditional one of
Buckland, Burnham & Augustin (1997). Each model's n̂₀ has the log-scale interval of its intercept-based prediction
(the usual log-normal interval for a missing cell). Models whose fitted n̂₀ is unbounded (a pairwise term that leaves
the missing cell unidentified) are left out.

Checked on the three-source spina bifida data of upstate New York, 1969–1974 (Hook, Albright & Cross 1980; the R
package conting's `spina`, 621 cases on three lists): every model's N̂, deviance and AIC equal R's `glm`; the averaged
N̂ is 734.8 [660.5, 809.1] and the lists' completeness 69 %, 28 % and 25 %, the authors' 68 %, 27 % and 25 %.
"""

from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass

import numpy as np


@dataclass
class Estimate:
    observed: float                     # n: events recorded by at least one system
    total: float                        # N̂, model-averaged
    low: float                          # its 95 % interval
    high: float
    completeness: dict[str, float]      # each system's recorded share of N̂
    models: list[dict]                  # every model fitted: terms, N̂, n̂₀, deviance, df, AIC, weight


def _design(patterns: np.ndarray, pairs: tuple[tuple[int, int], ...]) -> np.ndarray:
    cols = [np.ones(len(patterns))] + [patterns[:, j] for j in range(patterns.shape[1])]
    cols += [patterns[:, a] * patterns[:, b] for a, b in pairs]
    return np.column_stack(cols).astype(float)


def multiple_systems(counts: dict[tuple[int, ...], float], systems: list[str], max_pairs: int | None = None,
                     z: float = 1.959963984540054) -> Estimate:
    """N̂ from the counts of each observed inclusion pattern (a tuple of 0/1 per system, the all-zero one absent),
    averaged over the log-linear models with main effects and any set of pairwise interactions (at most ``max_pairs``;
    all by default). Needs at least three systems for any dependence to be estimable; with two, only independence."""
    import statsmodels.api as sm

    k = len(systems)
    if k < 2:
        raise ValueError("capture needs at least two systems")
    pats = [p for p in itertools.product((0, 1), repeat=k) if any(p)]
    y = np.array([float(counts.get(p, 0.0)) for p in pats])
    X_pat = np.array(pats, dtype=float)
    n = float(y.sum())
    pairs_all = list(itertools.combinations(range(k), 2))
    limit = len(pairs_all) if max_pairs is None else max_pairs
    models = []
    for r in range(0, min(limit, len(pairs_all)) + 1):
        for pairs in itertools.combinations(pairs_all, r):
            X = _design(X_pat, pairs)
            if X.shape[1] > len(y):
                continue
            try:
                with warnings.catch_warnings():     # the saturated model has no residual df: statsmodels warns, harmlessly
                    warnings.simplefilter("ignore")
                    fit = sm.GLM(y, X, family=sm.families.Poisson()).fit()
            except Exception:  # noqa: BLE001 - a model that does not converge is not averaged
                continue
            x0 = _design(np.zeros((1, k)), pairs)[0]
            eta = float(x0 @ fit.params)
            se = float(np.sqrt(x0 @ fit.cov_params() @ x0))
            if not np.isfinite(eta) or not np.isfinite(se) or eta > np.log(1e3 * max(n, 1.0)):
                continue                  # the missing cell unidentified (n̂₀ unbounded)
            n0 = float(np.exp(eta))
            models.append({"terms": [f"{systems[a]}:{systems[b]}" for a, b in pairs], "total": n + n0, "missing": n0,
                           "missing_low": float(np.exp(eta - z * se)), "missing_high": float(np.exp(eta + z * se)),
                           "se_total": n0 * se, "deviance": float(fit.deviance), "df": int(fit.df_resid),
                           "aic": float(fit.aic)})
    if not models:
        raise ValueError("no log-linear model identifies the unrecorded events")
    aic = np.array([m["aic"] for m in models])
    w = np.exp(-(aic - aic.min()) / 2)
    w /= w.sum()
    for m, wi in zip(models, w, strict=True):
        m["weight"] = float(wi)
    N = np.array([m["total"] for m in models])
    se = np.array([m["se_total"] for m in models])
    total = float((w * N).sum())
    # Buckland, Burnham & Augustin (1997): the unconditional sd carries the spread between models
    sd = float((w * np.sqrt(se ** 2 + (N - total) ** 2)).sum())
    low, high = max(n, total - z * sd), total + z * sd
    completeness = {s: float(sum(c for p, c in counts.items() if p[j])) / total for j, s in enumerate(systems)}
    return Estimate(n, total, low, high, completeness, sorted(models, key=lambda m: m["aic"]))
