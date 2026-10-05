"""Lenses: one field at a time (ARCHITECTURE §7.1).

Every lens returns rows (a locus, an effect, a p-value) for one family and
writes its test to the ledger before running. The observation lens is not a
separate function: it is any of these applied to a recording-practice field
(the ill-defined share, a coding pattern), flagged by the caller's family name.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import special, stats

from .. import control, graphs, surprise
from . import subset

# Minimum relevant effects (P5, ARCHITECTURE §8.4): every lens tests against an effect worth
# reporting, not against zero. Provisional until the harness calibrates them on negative controls.
RATE_RATIO = 1.2         # cell lenses: H0 is "the rate is at most 1.2 × expected"
TREND_PERIOD = 1.2       # trend divergence: H0 is "the place's course diverges by at most 20% over the period"
GROUP_SD = 0.2           # group disparity: H0 is "the groups' log-SIRs spread by at most this sd"
MARK_LOG = 0.03          # marks: H0 is "the mean log mark departs by at most 3%"


_NULLS: dict[tuple, subset.Null] = {}


@dataclass
class Finding:
    lens: str
    field: str
    tier: str
    locus: dict              # places (codes), years, groups, codes
    effect: float            # rate ratio, or posterior-sd divergence
    p: float
    stats: dict


# ---------------------------------------------------------------------- scans over cells


def spatial_cluster(s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, k: int = 30,
                    replicates: int = 200, alpha: float = 0.05) -> list[Finding]:
    """Graph-connected place sets over the whole period (time summed), expectation-based Poisson scan."""
    return _cells("spatial_cluster", s, edges, ledger, k, replicates, alpha, full_period=True)


def space_time(s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, k: int = 30,
               max_window: int | None = 4, replicates: int = 200, alpha: float = 0.05) -> list[Finding]:
    """Place sets × contiguous windows of at most ``max_window`` years."""
    return _cells("space_time", s, edges, ledger, k, replicates, alpha, max_window=max_window)


def _cells(lens: str, s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, k: int, replicates: int,
           alpha: float, full_period: bool = False, max_window: int | None = None) -> list[Finding]:
    family = f"{lens}|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": lens, "field": s.field.id, "tier": s.tier,
                                                               "k": k, "max_window": max_window,
                                                               "replicates": replicates}))
    # a miscalibrated field stays in the lenses, its findings carrying the flag (§6.2); only cells
    # without exposure or information are left out
    usable = (s.flags & (surprise.DENOMINATOR | surprise.NO_INFORMATION)) == 0
    mark = s.extras.get("kind") == "mark"
    if mark:
        # marks: the Gaussian score over weighted residuals of the mean log mark, beyond ±δ
        resid = np.nan_to_num(s.y) - np.nan_to_num(s.mu)
        y_up = np.where(usable, s.w * (resid - MARK_LOG), 0.0)
        y_down = np.where(usable, s.w * (-resid - MARK_LOG), 0.0)
        m = np.where(usable, s.w, 0.0)
    else:
        # counts: the null's boundary is θ0·μ, replicates included (§8.4)
        y = np.where(usable, s.y, 0.0)
        m = np.where(usable, RATE_RATIO * s.mu, 0.0)
    if not usable.any():
        ledger.complete(test, 1.0, None, {"subsets": 0, "reason": "no usable cell"})
        return []
    scanner = subset.Scanner(subset.neighbourhoods(edges, len(s.places), k), max_window=max_window,
                             full_period=full_period, kind="gaussian" if mark else "poisson")
    # a mark departs in either direction (low birth weight matters as much as high): both tails,
    # one null serving both (the Gaussian null is symmetric)
    directions = (("up", 1.0, y_up), ("down", -1.0, y_down)) if mark else (("up", 1.0, y),)
    # the null depends on (μ, φ, neighbourhoods, windows) only: one per field, shared by every
    # scan of it, surrogates included (the harness re-scans the same μ many times)
    null_key = (lens, s.field.id, s.tier, k, max_window, full_period, replicates, mark,
                s.mu.ctypes.data, s.mu.shape, float(np.nansum(s.mu)))
    out, nul = [], _NULLS.get(null_key)
    for name, sign, data in directions:
        found, nul = subset.scan(data, m, s.phi, scanner, alpha=alpha, replicates=replicates,
                                 seed_parts=(lens, s.field.id, s.tier), nul=nul)
        _NULLS[null_key] = nul
        out += [Finding(lens, s.field.id, s.tier,
                        {"places": s.places[f.places].tolist(),
                         "years": [int(s.years[f.window[0]]), int(s.years[f.window[1]])], "direction": name},
                        float(np.exp(sign * f.observed / f.expected + sign * MARK_LOG)) if mark
                        else f.ratio * RATE_RATIO,
                        min(1.0, f.p * len(directions)),
                        {"score": f.score, "observed": f.observed,
                         "expected": f.expected if mark else f.expected / RATE_RATIO,
                         "p_empirical": f.p_empirical, "null": "minimum effect",
                         "calibrated": bool(s.calibration.get("calibrated", True))}) for f in found]
    ledger.complete(test, min([f.p for f in out], default=1.0), out[0].effect if out else None,
                    {"subsets": len(out), "null_loc": nul.loc, "null_scale": nul.scale,
                     "calibrated": s.calibration.get("calibrated")})
    return out


# ---------------------------------------------------------------------- per place


def outbreak(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05) -> list[Finding]:
    """Cells above their predictive (B2: a place's own course): the upper tail P(Y ≥ y) is the
    one-sided p; BH across the field's cells."""
    family = f"outbreak|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "outbreak", "field": s.field.id,
                                                               "tier": s.tier}))
    ok = (s.flags & (surprise.DENOMINATOR | surprise.NO_INFORMATION)) == 0
    if s.extras.get("kind") == "mark":
        # two-sided beyond ±δ on the mean log mark, Gaussian
        sdv = np.sqrt(np.divide(1.0, s.w, out=np.full(s.w.shape, np.inf), where=s.w > 0))
        excess = np.abs(np.nan_to_num(s.y) - np.nan_to_num(s.mu)) - MARK_LOG
        p = np.minimum(1.0, 2 * special.ndtr(-np.divide(excess, sdv, out=np.zeros_like(excess), where=sdv < np.inf)))
    else:
        p = _upper_tail(s.y, RATE_RATIO * s.mu, s.phi)
    flat = np.where(ok, p, 1.0).ravel()
    hits = np.nonzero(control.bh(flat, q))[0]
    U, T = s.y.shape
    out = [Finding("outbreak", s.field.id, s.tier, {"places": [int(s.places[i // T])], "years": [int(s.years[i % T])]},
                   float(s.y.flat[i] / max(s.mu.flat[i], 1e-12)), float(flat[i]),
                   {"observed": float(s.y.flat[i]), "expected": float(s.mu.flat[i]), "z": float(s.z.flat[i])})
           for i in hits]
    ledger.complete(test, float(flat.min()) if flat.size else 1.0, None, {"cells": int(ok.sum()), "hits": len(out)})
    return out


def change_point(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05, min_years: int = 2,
                 replicates: int | None = None) -> list[Finding]:
    """A level shift in a place's trailing years: for each window [t, T−1] (at least ``min_years``
    long), the exact upper tail of its total under the predictive, a sum of NB cells
    moment-matched to NB(M, M²/Σ μ²/φ); the place's p is the smallest window p times the number
    of windows (Bonferroni: exact for discrete counts, conservative across nested windows, no
    simulation and no floor). BH across places. ``replicates`` is accepted and unused.

    Two simulated nulls were tried first and failed on sparse fields (survey of IX, 2026-10-04):
    a Gumbel fitted by moments to replicate maxima, most of them zero, flagged 25 small places for
    rheumatic heart disease; fitting the Gumbel to the positive maxima only still gave p = 4e-9 to
    2 deaths against 0.03 expected, where the exact tail is near 1e-3."""
    family = f"change_point|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "change_point", "field": s.field.id,
                                                               "tier": s.tier, "null": "exact NB, Bonferroni"}))
    U, T = s.y.shape
    starts = T - min_years + 1
    Y = np.cumsum(s.y[:, ::-1], 1)[:, ::-1][:, :starts]
    M = RATE_RATIO * np.cumsum(s.mu[:, ::-1], 1)[:, ::-1][:, :starts]   # H0 boundary: θ0 × expected
    extra_cells = np.where(np.isfinite(s.phi), (RATE_RATIO * s.mu) ** 2 / np.where(np.isfinite(s.phi), s.phi, 1.0), 0.0)
    E = np.cumsum(extra_cells[:, ::-1], 1)[:, ::-1][:, :starts]
    p_win = np.ones((U, starts))
    up = (Y > M) & (M > 0)
    pois = up & (E <= 0)
    p_win[pois] = stats.poisson.sf(Y[pois] - 1, M[pois])
    nb = up & (E > 0)
    n = M[nb] ** 2 / E[nb]
    p_win[nb] = stats.nbinom.sf(Y[nb] - 1, n, n / (n + M[nb]))
    start = p_win.argmin(1)
    p = np.minimum(1.0, p_win.min(1) * starts)
    ok = ((s.flags & surprise.DENOMINATOR) == 0).all(1)
    p = np.where(ok, p, 1.0)
    hits = np.nonzero(control.bh(p, q))[0]
    out = []
    for u in hits:
        t = int(start[u])
        out.append(Finding("change_point", s.field.id, s.tier, {"places": [int(s.places[u])],
                                                                "years": [int(s.years[t]), int(s.years[-1])]},
                           float(RATE_RATIO * Y[u, t] / M[u, t]), float(p[u]),
                           {"observed": float(Y[u, t]), "expected": float(M[u, t] / RATE_RATIO), "windows": starts}))
    ledger.complete(test, float(p.min()), None, {"places": int(ok.sum()), "hits": len(out)})
    return out


def group_disparity(y_g: np.ndarray, mu_g: np.ndarray, places: np.ndarray, field_id: str, ledger: control.Ledger,
                    q: float = 0.05, min_expected: float = 5.0) -> list[Finding]:
    """Per place: does the place's excess differ across groups (sex × age bands)? A likelihood-ratio
    heterogeneity G² of the groups' SIRs around the place's own SIR, against the national (B0)
    group pattern. Overdispersion is absorbed by a genomic-control factor (the median G²/df over
    places), so the reference is χ²_df after division. Groups with μ < ``min_expected`` pooled."""
    family = f"group_disparity|B0|{field_id.split(':')[-1]}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "group_disparity", "field": field_id,
                                                               "tier": "B0"}))
    Y, M = y_g.sum(1), mu_g.sum(1)                                     # over years: [U, G]
    G2 = np.zeros(len(places))
    df = np.zeros(len(places), dtype=int)
    for u in range(len(places)):
        yy, mm = Y[u], M[u]
        big = mm >= min_expected
        if big.sum() < 2:
            continue
        yy = np.append(yy[big], yy[~big].sum())
        mm = np.append(mm[big], mm[~big].sum())
        keep = mm > 0
        yy, mm = yy[keep], mm[keep]
        sir = yy.sum() / mm.sum()
        e = mm * sir
        with np.errstate(divide="ignore", invalid="ignore"):
            G2[u] = 2 * np.sum(np.where(yy > 0, yy * np.log(yy / e), 0) - (yy - e))
        df[u] = len(yy) - 1
    tested = df > 0
    c = max(float(np.median(G2[tested] / df[tested])), 1.0) if tested.any() else 1.0
    # H0 boundary: the groups' log-SIRs spread with sd GROUP_SD; G² is then about non-central
    # χ²(df, λ0) with λ0 ≈ GROUP_SD² · Σ_g μ_g (the place's expected events in the tested groups)
    lam0 = GROUP_SD ** 2 * M.sum(1)
    p = np.where(tested, stats.ncx2.sf(G2 / c, np.maximum(df, 1), np.maximum(lam0, 1e-9)), 1.0)
    hits = np.nonzero(control.bh(p, q))[0]
    out = []
    for u in hits:
        sir_g = np.divide(Y[u], M[u], out=np.full(M.shape[1], np.nan), where=M[u] > 0)
        overall = Y[u].sum() / M[u].sum()
        worst = int(np.nanargmax(np.abs(np.log(np.where(M[u] >= min_expected, sir_g, np.nan) / overall))))
        out.append(Finding("group_disparity", field_id, "B0", {"places": [int(places[u])], "groups": [worst]},
                           float(sir_g[worst] / overall), float(p[u]),
                           {"G2": float(G2[u]), "df": int(df[u]), "gc": c, "sir": float(overall)}))
    ledger.complete(test, float(p.min()) if p.size else 1.0, None, {"places": int(tested.sum()), "gc": c,
                                                                    "hits": len(out)})
    return out


def _upper_tail(y: np.ndarray, mean: np.ndarray, phi_agg: np.ndarray) -> np.ndarray:
    """P(Y ≥ y) under NB(mean, φ_agg) (Poisson where φ is infinite), cellwise; 1 where y ≤ mean."""
    out = np.ones(y.shape)
    up = (y > mean) & (mean > 0)
    pois = up & ~np.isfinite(phi_agg)
    out[pois] = stats.poisson.sf(y[pois] - 1, mean[pois])
    nb = up & np.isfinite(phi_agg)
    n = phi_agg[nb]
    out[nb] = stats.nbinom.sf(y[nb] - 1, n, n / (n + mean[nb]))
    return out


def trend_divergence(s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, q: float = 0.05
                     ) -> list[Finding]:
    """From B2: a place's trend β_u against its graph neighbours' mean, in posterior sd. Two-sided."""
    if s.tier != "B2" or "beta" not in s.extras:
        raise ValueError("trend divergence reads B2's place trends")
    family = f"trend_divergence|B2|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "trend_divergence", "field": s.field.id}))
    b, sd = s.extras["beta"], s.extras["beta_sd"]
    n = len(b)
    A = np.zeros(n)
    S = np.zeros(n)
    V = np.zeros(n)
    for i, j in edges:
        A[i] += b[j]
        A[j] += b[i]
        V[i] += sd[j] ** 2
        V[j] += sd[i] ** 2
        S[i] += 1
        S[j] += 1
    has = S > 0
    mean = np.divide(A, S, out=np.zeros(n), where=has)
    var = sd ** 2 + np.divide(V, S ** 2, out=np.zeros(n), where=has)
    # β is per standard deviation of the years: a divergence δ_β over the standardised range of
    # the period is a ratio TREND_PERIOD between its first and last year
    yrs = s.years.astype(float)
    span = (yrs.max() - yrs.min()) / max(yrs.std(), 1e-9)
    delta = np.log(TREND_PERIOD) / span
    diff = b - mean
    d = np.divide(diff, np.sqrt(var), out=np.zeros(n), where=has & (var > 0))
    excess = np.divide(np.abs(diff) - delta, np.sqrt(var), out=np.zeros(n), where=has & (var > 0))
    p = np.where(has, np.minimum(1.0, 2 * special.ndtr(-excess)), 1.0)
    hits = np.nonzero(control.bh(p, q))[0]
    out = [Finding("trend_divergence", s.field.id, "B2", {"places": [int(s.places[u])]}, float(d[u]), float(p[u]),
                   {"beta": float(b[u]), "neighbours": float(mean[u]), "rate_ratio_per_sd_year": float(np.exp(b[u]))})
           for u in hits]
    ledger.complete(test, float(p.min()), None, {"places": int(has.sum()), "hits": len(out)})
    return out


def default_graph(places: np.ndarray) -> np.ndarray:
    return graphs.edges(places, graphs.DEFAULT)
