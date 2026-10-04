"""Cohort scans: every attribute × every outcome on linked persons (ARCHITECTURE §7.8).

The input is a person table (one row per person, or per person-period) with
categorical attributes, outcome counts, person-time, and the adjustment
columns: age band, sex, year, place. For each (attribute level, outcome):

    outcome ~ Poisson(person_time · exp(level + age×sex + year + attribute + v_place)),
    v_place ~ N(0, 1/τ)  (τ by Fellner–Schall)

and log RR of the attribute level against its reference is tested against the
minimum relevant effect: H0 |log RR| ≤ log δ_RR. BH across the grid of a family.

Linkage uncertainty: with ``draws`` (tables from pegasus_data's ``link_draws``,
each a plausible set of persons), the scan runs per draw and the estimates are
combined by Rubin's rules.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy import special

from .. import control

DELTA_RR = 1.2  # provisional until calibrated (ARCHITECTURE §8.4)


@dataclass
class CohortResult:
    attribute: str
    level: str
    reference: str
    outcome: str
    log_rr: float
    sd: float
    p: float
    events: float
    person_time: float


def _codes(col: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    levels, inv = np.unique(col.astype(str), return_inverse=True)
    return levels, inv


def fit_one(y: np.ndarray, t: np.ndarray, fixed: list[np.ndarray], attr: np.ndarray, place: np.ndarray,
            iterations: int = 50, outer: int = 15) -> tuple[np.ndarray, np.ndarray]:
    """Penalised Poisson IRLS. ``fixed`` and ``attr`` are integer codes (first level = reference);
    returns (attribute coefficients, their sd) for levels 1…L−1."""
    n = len(y)
    blocks = [sp.csr_matrix(np.ones((n, 1)))]
    for f in fixed:
        k = f.max() + 1
        if k > 1:
            blocks.append(sp.csr_matrix((np.ones(n), (np.arange(n), f)), shape=(n, k))[:, 1:])
    ka = attr.max() + 1
    A = sp.csr_matrix((np.ones(n), (np.arange(n), attr)), shape=(n, ka))[:, 1:]
    kp = place.max() + 1
    P = sp.csr_matrix((np.ones(n), (np.arange(n), place)), shape=(n, kp))
    X = sp.hstack(blocks + [A, P]).tocsr()
    p_fixed = X.shape[1] - kp
    a_start = p_fixed - (ka - 1)
    beta = np.zeros(X.shape[1])
    beta[0] = np.log(max(y.sum(), 0.5) / t.sum())
    tau = 1.0
    off = np.log(np.maximum(t, 1e-12))
    for _ in range(outer):
        for _ in range(iterations):
            eta = X @ beta + off
            m = np.exp(eta)
            pen = np.zeros(X.shape[1])
            pen[p_fixed:] = tau
            H = (X.T @ sp.diags(m) @ X + sp.diags(pen + 1e-8)).tocsc()
            g = X.T @ (y - m) - pen * beta
            step = spla.spsolve(H, g)
            beta += np.clip(step, -5, 5)
            if np.abs(step).max() < 1e-8:
                break
        lu = spla.splu(H)
        E = np.zeros((X.shape[1], kp))
        E[p_fixed + np.arange(kp), np.arange(kp)] = 1.0
        tr = float(np.trace(lu.solve(E)[p_fixed:]))
        v = beta[p_fixed:]
        new = float(np.clip((kp - tau * tr) / max(v @ v, 1e-12), 1e-4, 1e8))
        done = abs(np.log(new / tau)) < 0.01
        tau = new
        if done:
            break
    E = np.zeros((X.shape[1], ka - 1))
    E[a_start + np.arange(ka - 1), np.arange(ka - 1)] = 1.0
    cov = lu.solve(E)[a_start:a_start + ka - 1]
    return beta[a_start:a_start + ka - 1], np.sqrt(np.clip(np.diag(cov), 0, None))


def scan(table: pa.Table, attributes: list[str], outcomes: list[str], ledger: control.Ledger, family: str,
         person_time: str = "person_time", adjust: tuple[str, ...] = ("age_band", "sex", "year"),
         place: str = "place", delta_rr: float = DELTA_RR, min_events: int = 20,
         draws: list[pa.Table] | None = None) -> list[CohortResult]:
    tables = draws or [table]
    hyps, specs = [], []
    for a in attributes:
        for o in outcomes:
            specs.append((a, o))
            hyps.append(control.Hypothesis(family, "scan", {"attribute": a, "outcome": o, "delta_rr": delta_rr,
                                                            "draws": len(tables)}))
    ids = ledger.register_many(hyps)
    out: list[CohortResult] = []
    rows = []
    for test, (a, o) in zip(ids, specs, strict=True):
        ests, vars_ = [], []
        levels = ref = None
        y_tot = t_tot = 0.0
        for tab in tables:
            y = tab.column(o).to_numpy().astype(float)
            t = tab.column(person_time).to_numpy().astype(float)
            levels, attr = _codes(tab.column(a).to_numpy(zero_copy_only=False))
            r = int(np.bincount(attr).argmax())         # the most common level is the reference
            ref = levels[r]
            attr = np.where(attr == r, 0, attr + (attr < r))  # reference first, the others in order
            fixed = [_codes(tab.column(c).to_numpy(zero_copy_only=False))[1] for c in adjust]
            pl = _codes(tab.column(place).to_numpy(zero_copy_only=False))[1]
            b, s = fit_one(y, t, fixed, attr, pl)
            ests.append(b)
            vars_.append(s ** 2)
            y_tot, t_tot = y.sum(), t.sum()
        est = np.mean(ests, axis=0)
        within = np.mean(vars_, axis=0)
        between = np.var(ests, axis=0, ddof=1) if len(ests) > 1 else 0.0
        sd = np.sqrt(within + (1 + 1 / len(ests)) * between)
        z = (np.abs(est) - np.log(delta_rr)) / np.maximum(sd, 1e-12)
        p = special.ndtr(-z)
        others = [lv for lv in levels if lv != ref]
        rows.append((test, float(p.min()) if len(p) else 1.0, float(est[np.argmin(p)]) if len(p) else None,
                     {"levels": len(others), "events": y_tot}))
        if y_tot < min_events:
            continue
        for lv, e, s_, pp in zip(others, est, sd, p, strict=True):
            out.append(CohortResult(a, str(lv), str(ref), o, float(e), float(s_), float(pp), y_tot, t_tot))
    ledger.complete_many(rows)
    return out
