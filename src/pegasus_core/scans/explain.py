"""On demand: explaining away and decomposition (ARCHITECTURE §7.7).

Explaining away: refit the lead's field over the lead's cells and their
surroundings with a candidate driver x added to log μ; report the coefficient
with its interval and the share of the lead's deviance the driver absorbs,

    A = 1 − D'_S / D_S,    D_S = 2 Σ_{c∈S} [ y log(y/μ) − (y − μ) ].

Decomposition: the change in expected events between two periods split into
population size, age–sex composition, place mix and risk, each by substitution
of one component at a time, averaged over all 24 orders (exact Shapley values
for four components).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy import special


def deviance(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.maximum(mu, 1e-300)
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(2 * np.sum(np.where(y > 0, y * np.log(y / mu), 0.0) - (y - mu)))


@dataclass
class Explanation:
    coefficient: float
    sd: float
    interval: tuple[float, float]
    absorbed: float          # A over the lead's cells
    deviance_before: float
    deviance_after: float
    cells: int


def explain_away(y: np.ndarray, mu: np.ndarray, phi: np.ndarray, x: np.ndarray, lead: np.ndarray,
                 region: np.ndarray | None = None, iterations: int = 50) -> Explanation:
    """Arrays over cells (any shape, flattened together). ``lead`` marks the lead's cells,
    ``region`` the cells the coefficient is estimated on (default: everything given)."""
    y, mu, x = (np.asarray(a, dtype=float).ravel() for a in (y, mu, x))
    phi = np.broadcast_to(np.asarray(phi, dtype=float), np.shape(mu)).ravel()
    S = np.asarray(lead, dtype=bool).ravel()
    fit = np.ones_like(S) if region is None else np.asarray(region, dtype=bool).ravel()
    fit &= np.isfinite(x) & (mu > 0)
    xs = (x - x[fit].mean()) / max(x[fit].std(), 1e-12)
    a, g = 0.0, 0.0                       # a free level over the region keeps g from absorbing the level
    pois = ~np.isfinite(phi)
    for _ in range(iterations):
        m = mu * np.exp(a + g * xs)
        w = np.where(pois, m, m / (1 + m / np.where(pois, 1, phi)))
        r = np.where(pois, y - m, (y - m) / (1 + m / np.where(pois, 1, phi)))
        X = np.column_stack([np.ones(fit.sum()), xs[fit]])
        H = (X * w[fit, None]).T @ X
        step = np.linalg.solve(H, X.T @ r[fit])
        a, g = a + step[0], g + step[1]
        if np.abs(step).max() < 1e-8:
            break
    cov = np.linalg.inv(H)
    sd_unit = float(np.sqrt(cov[1, 1]))
    scale = max(x[fit].std(), 1e-12)
    coef, sd = g / scale, sd_unit / scale
    z = special.ndtri(0.975)
    mu_new = mu * np.exp(a + g * xs)
    before = deviance(y[S], mu[S])
    after = deviance(y[S], mu_new[S])
    return Explanation(float(coef), float(sd), (float(coef - z * sd), float(coef + z * sd)),
                       float(1 - after / before) if before > 0 else float("nan"), before, after, int(S.sum()))


def decompose(N0: np.ndarray, r0: np.ndarray, N1: np.ndarray, r1: np.ndarray) -> dict[str, float | np.ndarray]:
    """Expected events E = Σ_{u,g} N·r between two periods, with N [U, G] person-years and r [U, G]
    rates. N = total × place share × composition within place. Returns the Shapley share of each
    of size, composition, place mix and risk (summing to E1 − E0), and risk's split by place
    and by group."""
    def parts(N: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        total = N.sum()
        place = N.sum(1) / total
        comp = np.divide(N, N.sum(1, keepdims=True), out=np.zeros_like(N), where=N.sum(1, keepdims=True) > 0)
        return total, place, comp

    t0, p0, c0 = parts(N0)
    t1, p1, c1 = parts(N1)
    names = ("size", "composition", "place", "risk")
    start = {"size": t0, "composition": c0, "place": p0, "risk": r0}
    end = {"size": t1, "composition": c1, "place": p1, "risk": r1}

    def E(v: dict) -> np.ndarray:
        return v["size"] * v["place"][:, None] * v["composition"] * v["risk"]

    shap = dict.fromkeys(names, 0.0)
    risk_cells = np.zeros_like(N0, dtype=float)
    orders = list(itertools.permutations(names))
    for order in orders:
        cur = dict(start)
        for n in order:
            before = E(cur)
            cur[n] = end[n]
            delta = E(cur) - before
            shap[n] += delta.sum() / len(orders)
            if n == "risk":
                risk_cells += delta / len(orders)
    return {**shap, "total": float(E(end).sum() - E(start).sum()),
            "risk_by_place": risk_cells.sum(1), "risk_by_group": risk_cells.sum(0)}
