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
            iterations: int = 50, outer: int = 15, warm: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Penalised Poisson IRLS. ``fixed`` and ``attr`` are integer codes (first level = reference);
    returns (attribute coefficients, their sd) for levels 1…L−1. ``warm`` (a dict, updated in place) carries the
    solution from one fit to the next on the same cells: a link draw's outcome differs from the last in a few persons.

    Each row (a cell) sits in one place, so the Hessian's place block is diagonal and the Newton system is solved by
    its Schur complement on the few fixed columns: a dense solve of their size, and the trace of the place block's
    inverse that Fellner–Schall's τ needs in closed form. The full sparse factorisation with a dense right-hand side
    per place it replaces took hours on a year of births (2026-10-08)."""
    n = len(y)
    blocks = [np.ones((n, 1))]                   # the fixed columns are few: dense, so the products are BLAS
    for f in [*fixed, attr]:
        k = int(f.max()) + 1
        if k > 1 or f is attr:
            blocks.append((f[:, None] == np.arange(1, k)[None, :]).astype(float))
    F = np.hstack(blocks)
    pf = F.shape[1]
    ka = int(attr.max()) + 1
    a_start = pf - (ka - 1)
    kp = int(place.max()) + 1
    P = sp.csr_matrix((np.ones(n), (np.arange(n), place)), shape=(n, kp))
    b = np.zeros(pf)
    b[0] = np.log(max(y.sum(), 0.5) / t.sum())
    v = np.zeros(kp)
    tau = 1.0
    if warm:
        b, v, tau = warm["b"].copy(), warm["v"].copy(), warm["tau"]
    off = np.log(np.maximum(t, 1e-12))
    for _ in range(outer):
        for _ in range(iterations):
            m = np.exp(F @ b + v[place] + off)
            Fm = F * m[:, None]
            A = F.T @ Fm + 1e-8 * np.eye(pf)
            B = (P.T @ Fm).T
            D = np.bincount(place, weights=m, minlength=kp) + tau
            gf = F.T @ (y - m)
            gp = np.bincount(place, weights=y - m, minlength=kp) - tau * v
            BD = B / D
            S = A - BD @ B.T
            sf = np.linalg.solve(S, gf - BD @ gp)
            sp_ = (gp - B.T @ sf) / D
            b += np.clip(sf, -5, 5)
            v += np.clip(sp_, -5, 5)
            # the Newton decrement, not the step: a level without events walks to −∞ by steps that never shrink, while
            # its mean, and so the decrement, vanishes (every round ran its fifty iterations before)
            if gf @ sf + gp @ sp_ < 1e-8:
                break
        Si = np.linalg.inv(S)
        tr = float(np.sum(1.0 / D) + np.einsum("ij,ji->", Si, BD @ BD.T))   # tr of the place block of H⁻¹
        new = float(np.clip((kp - tau * tr) / max(v @ v, 1e-12), 1e-4, 1e8))
        done = abs(np.log(new / tau)) < 0.01
        tau = new
        if done:
            break
    if warm is not None:
        warm.update(b=b, v=v, tau=tau)
    cov = Si[a_start:, a_start:]          # the fixed block of H⁻¹ is the Schur complement's inverse
    return b[a_start:], np.sqrt(np.clip(np.diag(cov), 0, None))


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
        # the covariates are the draws' common part, only the outcome differs: the persons are collapsed once to their
        # covariate patterns (attribute level × adjusters × place), whose sums of outcome and person-time are the
        # Poisson likelihood's sufficient statistics, so each draw's fit reads cells, not persons (2.7 million births
        # a draw before: hours)
        base = tables[0]
        levels, attr = _codes(base.column(a).to_numpy(zero_copy_only=False))
        r = int(np.bincount(attr).argmax())         # the most common level is the reference
        ref = levels[r]
        attr = np.where(attr == r, 0, attr + (attr < r))  # reference first, the others in order
        fixed = [_codes(base.column(c).to_numpy(zero_copy_only=False))[1] for c in adjust]
        pl = _codes(base.column(place).to_numpy(zero_copy_only=False))[1]
        cols = [attr, *fixed, pl]
        pattern, inv = np.unique(np.ravel_multi_index(cols, [int(c.max()) + 1 for c in cols]), return_inverse=True)
        cells = np.unravel_index(pattern, [int(c.max()) + 1 for c in cols])
        t_cells = np.bincount(inv, weights=base.column(person_time).to_numpy().astype(float), minlength=len(pattern))
        warm: dict = {}
        for tab in tables:
            y = tab.column(o).to_numpy().astype(float)
            y_cells = np.bincount(inv, weights=y, minlength=len(pattern))
            b, s = fit_one(y_cells, t_cells, list(cells[1:-1]), cells[0], cells[-1], warm=warm)
            ests.append(b)
            vars_.append(s ** 2)
            y_tot, t_tot = y.sum(), t_cells.sum()
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
