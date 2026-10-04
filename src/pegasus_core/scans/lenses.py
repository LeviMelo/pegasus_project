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
    usable = (s.flags & (surprise.DENOMINATOR | surprise.CALIBRATION)) == 0
    y = np.where(usable, s.y, 0.0)
    m = np.where(usable, s.mu, 0.0)
    scanner = subset.Scanner(subset.neighbourhoods(edges, len(s.places), k), max_window=max_window,
                             full_period=full_period)
    found, nul = subset.scan(y, m, s.phi, scanner, alpha=alpha, replicates=replicates,
                             seed_parts=(lens, s.field.id, s.tier))
    out = [Finding(lens, s.field.id, s.tier,
                   {"places": s.places[f.places].tolist(),
                    "years": [int(s.years[f.window[0]]), int(s.years[f.window[1]])]},
                   f.ratio, f.p, {"score": f.score, "observed": f.observed, "expected": f.expected,
                                  "p_empirical": f.p_empirical}) for f in found]
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
    p = special.ndtr(-s.z)  # z from the nearer tail; the upper-tail probability
    ok = (s.flags & (surprise.DENOMINATOR | surprise.CALIBRATION | surprise.NO_INFORMATION)) == 0
    flat = np.where(ok, p, 1.0).ravel()
    hits = np.nonzero(control.bh(flat, q))[0]
    U, T = s.y.shape
    out = [Finding("outbreak", s.field.id, s.tier, {"places": [int(s.places[i // T])], "years": [int(s.years[i % T])]},
                   float(s.y.flat[i] / max(s.mu.flat[i], 1e-12)), float(flat[i]),
                   {"observed": float(s.y.flat[i]), "expected": float(s.mu.flat[i]), "z": float(s.z.flat[i])})
           for i in hits]
    ledger.complete(test, float(flat.min()) if flat.size else 1.0, None, {"cells": int(ok.sum()), "hits": len(out)})
    return out


def change_point(s: surprise.Surprise, ledger: control.Ledger, replicates: int = 200, q: float = 0.05,
                 min_years: int = 2) -> list[Finding]:
    """A level shift in a place's trailing years: the best window [t, T−1] (at least ``min_years``
    long) by the Poisson score, against replicates of the same maximum per place; p from a
    Gumbel fitted per place by moments. BH across places."""
    from .. import config

    family = f"change_point|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "change_point", "field": s.field.id,
                                                               "tier": s.tier, "replicates": replicates}))

    def trailing(y: np.ndarray, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cy, cm = np.cumsum(y[:, ::-1], 1)[:, ::-1], np.cumsum(m[:, ::-1], 1)[:, ::-1]
        sc = subset.score(cy, cm)[:, : y.shape[1] - min_years + 1]
        return sc.max(1), sc.argmax(1)

    obs, start = trailing(s.y, s.mu)
    rng = np.random.default_rng(config.seed("change_point", s.field.id, s.tier))
    maxima = np.stack([trailing(subset.replicate(s.mu, s.phi, rng), s.mu)[0] for _ in range(replicates)])
    sd = maxima.std(0)
    beta = np.maximum(sd * np.sqrt(6) / np.pi, 1e-12)
    loc = maxima.mean(0) - 0.5772156649 * beta
    p = np.where(obs > 0, stats.gumbel_r.sf(obs, loc, beta), 1.0)
    ok = ((s.flags & (surprise.DENOMINATOR | surprise.CALIBRATION)) == 0).all(1) & (sd > 0)
    p = np.where(ok, p, 1.0)
    hits = np.nonzero(control.bh(p, q))[0]
    out = []
    for u in hits:
        t = int(start[u])
        Y, M = s.y[u, t:].sum(), s.mu[u, t:].sum()
        out.append(Finding("change_point", s.field.id, s.tier, {"places": [int(s.places[u])],
                                                                "years": [int(s.years[t]), int(s.years[-1])]},
                           float(Y / M), float(p[u]), {"score": float(obs[u]), "observed": float(Y),
                                                       "expected": float(M)}))
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
    p = np.where(tested, stats.chi2.sf(G2 / c, np.maximum(df, 1)), 1.0)
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
    d = np.divide(b - mean, np.sqrt(var), out=np.zeros(n), where=has & (var > 0))
    p = np.where(has, 2 * special.ndtr(-np.abs(d)), 1.0)
    hits = np.nonzero(control.bh(p, q))[0]
    out = [Finding("trend_divergence", s.field.id, "B2", {"places": [int(s.places[u])]}, float(d[u]), float(p[u]),
                   {"beta": float(b[u]), "neighbours": float(mean[u]), "rate_ratio_per_sd_year": float(np.exp(b[u]))})
           for u in hits]
    ledger.complete(test, float(p.min()), None, {"places": int(has.sum()), "hits": len(out)})
    return out


def default_graph(places: np.ndarray) -> np.ndarray:
    return graphs.edges(places, graphs.DEFAULT)
