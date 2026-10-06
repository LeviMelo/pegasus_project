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
from . import scales as scales_mod
from . import subset

# Minimum relevant effects (P5, ARCHITECTURE §8.4, §10.5): every lens tests against an effect worth reporting, not
# against zero. Re-made on the grid (ADR-0026, evaluation 2026-10-06 minimum effects): the smallest θ0 whose model
# worlds (refitted, 20 per field) and space-scrambled normal-score negatives keep false leads at q on SIM I60-I69,
# SIM I00-I02 and SIH-RD J09-J18. v0's 1.2 cost the outbreak lens half its power (place doublings 0.38 against 0.72).
RATE_RATIO = 1.1         # cell lenses (outbreak, change point, space-time): H0 is "the rate is at most 1.1 × expected"
SPATIAL_RATE_RATIO = 1.5  # spatial cluster (B0) on SIM: model worlds 2/20 at 1.2, 0/20 at 1.5
SPATIAL_RATE_RATIO_BY = {"SIH-RD": 2.0}   # SIH's B0 carries its hospital-use geography (ADR-0018): 20/20 worlds at 1.5, 0/20 at 2.0
TREND_PERIOD = {"municipality": 1.1, "region": 1.1, "state": 1.1}   # trend divergence, per scale: H0 is "the unit's course diverges by at most this ratio over the period"; v0's municipal 1.5 came from raw-score time shifts, whose single real shock cell the normal scores remove


def spatial_rate_ratio(field_id: str) -> float:
    """The spatial cluster's θ0 for a field (its dataset is the id's first part)."""
    return SPATIAL_RATE_RATIO_BY.get(field_id.split(":")[0], SPATIAL_RATE_RATIO)


GROUP_SD = {"municipality": 0.2, "region": 0.2, "state": 0.2}   # group disparity, per scale: H0 is "the groups' log-SIRs spread by at most this sd" (weighted by expected events)
GC_MIN_UNITS = 500       # a scale with fewer units takes no genomic-control factor
MARK_LOG = 0.015        # marks: H0 is "the mean log mark departs by at most 1.5%": calibrated on the PESO negatives (0/30 false-lead worlds at 1.5%, space-time 6/30 at 1%, 30/30 at 0.5%; evaluation 2026-10-05 lens positives)


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
                    replicates: int = 200, alpha: float = 0.05, rate_ratio: float | None = None) -> list[Finding]:
    """Graph-connected place sets over the whole period (time summed), expectation-based Poisson scan.
    ``rate_ratio`` overrides the minimum effect θ0 (the grid's calibration, §10.5)."""
    return _cells("spatial_cluster", s, edges, ledger, k, replicates, alpha, full_period=True,
                  rate_ratio=spatial_rate_ratio(s.field.id) if rate_ratio is None else rate_ratio)


def space_time(s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, k: int = 30,
               max_window: int | None = 4, replicates: int = 200, alpha: float = 0.05,
               rate_ratio: float | None = None) -> list[Finding]:
    """Place sets × contiguous windows of at most ``max_window`` years."""
    return _cells("space_time", s, edges, ledger, k, replicates, alpha, max_window=max_window, rate_ratio=rate_ratio)


def _cells(lens: str, s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, k: int, replicates: int,
           alpha: float, full_period: bool = False, max_window: int | None = None,
           rate_ratio: float | None = None) -> list[Finding]:
    rr = RATE_RATIO if rate_ratio is None else rate_ratio
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
        # counts: the null's boundary is θ0·μ for an excess and μ/θ0 for a deficit (§8.4)
        y = np.where(usable, s.y, 0.0)
        m = np.where(usable, rr * s.mu, 0.0)
        m_low = np.where(usable, s.mu / rr, 0.0)
    if not usable.any():
        ledger.complete(test, 1.0, None, {"subsets": 0, "reason": "no usable cell"})
        return []
    nbr = subset.neighbourhoods(edges, len(s.places), k)
    scanner = subset.Scanner(nbr, max_window=max_window, full_period=full_period,
                             kind="gaussian" if mark else "poisson")
    # a mark departs in either direction (low birth weight matters as much as high): both tails,
    # one null serving both (the Gaussian null is symmetric)
    # both directions: an excess and a deficit (deficits show substitution and displacement, e.g.
    # pneumonia deaths below their forecast while COVID-19 rose, evaluation 2026-10-04)
    if mark:
        directions = (("up", 1.0, y_up, m, scanner), ("down", -1.0, y_down, m, scanner))
    else:
        low = subset.Scanner(nbr, max_window=max_window, full_period=full_period, kind="poisson_low")
        directions = (("up", 1.0, y, m, scanner), ("down", -1.0, y, m_low, low))
    out = []
    for name, sign, data, mm, sc in directions:
        # the null depends on (μ, φ, neighbourhoods, windows, direction) only: one per field and
        # direction, shared by every scan of it, surrogates included
        null_key = (lens, name, s.field.id, s.tier, k, max_window, full_period, replicates, mark,
                    s.mu.ctypes.data, s.mu.shape, float(np.nansum(s.mu)))
        found, nul = subset.scan(data, mm, s.phi, sc, alpha=alpha, replicates=replicates,
                                 seed_parts=(lens, name, s.field.id, s.tier), nul=_NULLS.get(null_key))
        if nul is not None:
            _NULLS[null_key] = nul
        out += [Finding(lens, s.field.id, s.tier,
                        {"places": s.places[f.places].tolist(),
                         "years": [int(s.years[f.window[0]]), int(s.years[f.window[1]])], "direction": name},
                        float(np.exp(sign * f.observed / f.expected + sign * MARK_LOG)) if mark
                        else _rr(f.observed, f.expected / (rr if name == "up" else 1 / rr)),
                        min(1.0, f.p * len(directions)),
                        {"score": f.score, "observed": f.observed,
                         "expected": f.expected if mark else f.expected / (rr if name == "up" else 1 / rr),
                         "p_empirical": f.p_empirical, "null": "minimum effect",
                         "calibrated": bool(s.calibration.get("calibrated", True))}) for f in found]
    out = [f for f in out if f.p <= alpha]   # α after the two directions' doubling
    ledger.complete(test, min([f.p for f in out], default=1.0), out[0].effect if out else None,
                    {"subsets": len(out), "null_loc": getattr(nul, "loc", None), "null_scale": getattr(nul, "scale", None),
                     "calibrated": s.calibration.get("calibrated")})
    return out


# ---------------------------------------------------------------------- per place


def outbreak(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05, rate_ratio: float | None = None
             ) -> list[Finding]:
    """Cells above their predictive (B2: a place's own course): the upper tail P(Y ≥ y) under θ0 × μ is the
    one-sided p; BH across the field's cells. ``rate_ratio`` overrides θ0 (`RATE_RATIO`)."""
    rr = RATE_RATIO if rate_ratio is None else rate_ratio
    family = f"outbreak|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "outbreak", "field": s.field.id,
                                                               "tier": s.tier}))
    ok = (s.flags & (surprise.DENOMINATOR | surprise.NO_INFORMATION)) == 0
    if s.extras.get("kind") == "mark":
        # two-sided beyond ±δ on the mean log mark, Gaussian
        sdv = np.sqrt(np.divide(1.0, s.w, out=np.full(s.w.shape, np.inf), where=s.w > 0))
        excess = np.abs(np.nan_to_num(s.y) - np.nan_to_num(s.mu)) - MARK_LOG
        p = np.minimum(1.0, 2 * special.ndtr(-np.divide(excess, sdv, out=np.zeros_like(excess), where=sdv < np.inf)))
    elif s.tier.startswith("BP"):          # prospective: the alarm baseline already holds the watched years out
        p = _upper_tail(s.y, rr * s.mu, s.phi)
    else:                                  # each cell against its place's course from every other year (`_course`)
        mult, var_log = _course(s, [(t, t + 1) for t in range(s.y.shape[1])], past_only=False)
        phi = np.where(np.isfinite(s.phi), s.phi, np.inf) if np.ndim(s.phi) else np.full(s.y.shape, s.phi)
        p = _upper_tail(s.y, rr * s.mu * mult, 1.0 / (1.0 / phi + np.expm1(var_log)))
    flat = np.where(ok, p, 1.0).ravel()
    hits = np.nonzero(control.bh(flat, q))[0]
    U, T = s.y.shape
    out = [Finding("outbreak", s.field.id, s.tier, {"places": [int(s.places[i // T])], "years": [int(s.years[i % T])]},
                   _rr(s.y.flat[i], s.mu.flat[i]), float(flat[i]),
                   {"observed": float(s.y.flat[i]), "expected": float(s.mu.flat[i]), "z": float(s.z.flat[i])})
           for i in hits]
    ledger.complete(test, float(flat.min()) if flat.size else 1.0, None, {"cells": int(ok.sum()), "hits": len(out)})
    return out


def change_point(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05, min_years: int = 2,
                 replicates: int | None = None, rate_ratio: float | None = None, min_past: int = 3) -> list[Finding]:
    """A level shift in a place's trailing years: for each window [t, T−1] (at least ``min_years`` long, after at
    least ``min_past`` years), the upper tail of its total; the place's p is the smallest window p times the number
    of windows (Bonferroni: conservative across nested windows, no simulation and no floor). BH across places.
    ``replicates`` is accepted and unused.

    The window is read against the place's own course, estimated from the years before it and extrapolated
    (`_course`; ADR-0027). This is the baseline of outbreak detectors since Farrington (1996): a persistent place
    deviation or trend is the baseline, and the step under test never enters it. The window total's predictive is NB,
    moment-matched to its cells' dispersion plus the extrapolation's uncertainty. Read against B2, which refits each
    place's trend over the whole series, a place step ×3 was found 11 % of the time. Against B1 as it is, the same step
    was found 95 % of the time, but SIH's persistent place courses produced steps in every space-scrambled world
    (evaluation 2026-10-06, minimum effects).

    Two simulated nulls were tried first and failed on sparse fields (survey of IX, 2026-10-04):
    a Gumbel fitted by moments to replicate maxima, most of them zero, flagged 25 small places for
    rheumatic heart disease; fitting the Gumbel to the positive maxima only still gave p = 4e-9 to
    2 deaths against 0.03 expected, where the exact tail is near 1e-3."""
    family = f"change_point|{s.tier}|{s.field.block}|past"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "change_point", "field": s.field.id,
                                                               "tier": s.tier, "baseline": "past course",
                                                               "null": "NB predictive, Bonferroni"}))
    rr = RATE_RATIO if rate_ratio is None else rate_ratio
    U, T = s.y.shape
    starts = np.arange(min_past, T - min_years + 1)
    if len(starts) == 0:
        return []
    Yall = np.cumsum(s.y[:, ::-1], 1)[:, ::-1]
    Mall = np.cumsum(s.mu[:, ::-1], 1)[:, ::-1]
    cells = np.where(np.isfinite(s.phi), s.mu ** 2 / np.where(np.isfinite(s.phi), s.phi, 1.0), 0.0)
    Eall = np.cumsum(cells[:, ::-1], 1)[:, ::-1]
    Y, M, E = Yall[:, starts], rr * Mall[:, starts], rr ** 2 * Eall[:, starts]
    mult, var_log = _course(s, [(int(t), T) for t in starts], past_only=True)   # [U, starts]: multiplier, log variance
    M, E = M * mult, E * mult ** 2
    V = M + E + M ** 2 * np.expm1(var_log)                  # the cells' NB variance + the extrapolated course's
    p_win = np.ones(Y.shape)
    up = (Y > M) & (M > 0)
    pois = up & (V <= M * (1 + 1e-12))
    p_win[pois] = stats.poisson.sf(Y[pois] - 1, M[pois])
    nb = up & ~pois
    n = M[nb] ** 2 / (V[nb] - M[nb])
    p_win[nb] = stats.nbinom.sf(Y[nb] - 1, n, n / (n + M[nb]))
    k = p_win.argmin(1)
    p = np.minimum(1.0, p_win.min(1) * len(starts))
    ok = ((s.flags & surprise.DENOMINATOR) == 0).all(1)
    p = np.where(ok, p, 1.0)
    hits = np.nonzero(control.bh(p, q))[0]
    out = []
    for u in hits:
        t = int(starts[k[u]])
        base = M[u, k[u]] / rr
        out.append(Finding("change_point", s.field.id, s.tier, {"places": [int(s.places[u])],
                                                                "years": [int(s.years[t]), int(s.years[-1])]},
                           _rr(Y[u, k[u]], base), float(p[u]),
                           {"observed": float(Y[u, k[u]]), "expected": float(base), "windows": len(starts),
                            "baseline": "past course"}))
    ledger.complete(test, float(p.min()), None, {"places": int(ok.sum()), "hits": len(out)})
    return out


def _course(s: surprise.Surprise, windows: list[tuple[int, int]], past_only: bool, iterations: int = 8
            ) -> tuple[np.ndarray, np.ndarray]:
    """Each place's course outside each window [t0, t1), carried into the window: an NB regression of the counts on the
    tier's mean (offset) with a level and a slope, fitted on the years before t0 (``past_only``: a step to the series'
    end, Farrington 1996's baseline with its trend) or on every year outside the window (a spike: the year under test
    never enters its own baseline). Priors: level ~ N(0, σ_a²) and slope ~ N(0, σ_b²), both from the field's between-place
    spread (method of moments on the places with at least 30 expected events over the series), so a sparse place
    stays near the tier and a large one follows its own course. Returns the window total's multiplier against the
    tier and the variance of its log (delta method on the posterior's Laplace covariance)."""
    U, T = s.y.shape
    yrs = np.arange(T, dtype=float)
    y, mu = s.y, np.maximum(s.mu, 1e-300)
    phi = np.where(np.isfinite(s.phi), s.phi, 1e12) if np.ndim(s.phi) else np.full((U, T), s.phi if np.isfinite(s.phi) else 1e12)
    tot_y, tot_m = y.sum(1), mu.sum(1)
    big = tot_m >= 30
    # the between-place variance of the multiplier: the totals' excess over their NB noise (Σμ + Σμ²/φ)
    noise = mu.sum(1) + (mu ** 2 / phi).sum(1)
    var_a = float(np.mean(((tot_y[big] - tot_m[big]) ** 2 - noise[big]) / tot_m[big] ** 2)) if big.any() else 0.0
    var_a = max(var_a, 1e-4)
    if big.any():                                        # slopes of the big places' log ratio: their spread less their noise
        c = yrs - yrs.mean()
        r = np.log((y[big] + 0.5) / (mu[big] + 0.5))
        b = (r * c).sum(1) / (c ** 2).sum()
        se2 = ((1.0 / np.maximum(mu[big], 0.5) + 1.0 / phi[big]) * c ** 2).sum(1) / (c ** 2).sum() ** 2
        var_b = max(float(np.var(b) - np.mean(se2)), 1e-5)
    else:
        var_b = 1e-5
    mult = np.ones((U, len(windows)))
    var_log = np.zeros((U, len(windows)))
    for k, (t, t1) in enumerate(windows):
        past = np.arange(t) if past_only else np.r_[np.arange(t), np.arange(t1, T)]
        pivot = t - 1 if past_only else (t + t1 - 1) / 2   # the slope pivots on the last past year, or the window's centre
        x = yrs[past] - pivot
        a, b = np.zeros(U), np.zeros(U)
        ph = phi[:, past]
        for _ in range(iterations):                      # Fisher scoring on the NB 2-parameter MAP, all places at once
            lam = mu[:, past] * np.exp(np.clip(a[:, None] + b[:, None] * x[None], -20, 20))
            wt = 1.0 / (1.0 + lam / ph)                  # NB: the score (y − λ)/(1 + λ/φ), the information λ/(1 + λ/φ)
            g_a = ((y[:, past] - lam) * wt).sum(1) - a / var_a
            g_b = ((y[:, past] - lam) * wt * x).sum(1) - b / var_b
            h_aa = (lam * wt).sum(1) + 1 / var_a
            h_ab = (lam * wt * x).sum(1)
            h_bb = (lam * wt * x ** 2).sum(1) + 1 / var_b
            det = h_aa * h_bb - h_ab ** 2
            a, b = a + (h_bb * g_a - h_ab * g_b) / det, b + (h_aa * g_b - h_ab * g_a) / det
        lam = mu[:, past] * np.exp(np.clip(a[:, None] + b[:, None] * x[None], -20, 20))
        wt = 1.0 / (1.0 + lam / ph)
        h_aa, h_ab, h_bb = (lam * wt).sum(1) + 1 / var_a, (lam * wt * x).sum(1), (lam * wt * x ** 2).sum(1) + 1 / var_b
        det = h_aa * h_bb - h_ab ** 2
        cov_aa, cov_ab, cov_bb = h_bb / det, -h_ab / det, h_aa / det
        xw = yrs[t:t1] - pivot
        w = mu[:, t:t1] * np.exp(a[:, None] + b[:, None] * xw[None])
        tot = np.maximum(mu[:, t:t1].sum(1), 1e-300)
        mult[:, k] = w.sum(1) / tot
        xbar = np.divide((w * xw).sum(1), w.sum(1), out=np.full(U, xw.mean()), where=w.sum(1) > 0)
        var_log[:, k] = cov_aa + 2 * xbar * cov_ab + xbar ** 2 * cov_bb
    return mult, var_log


def group_disparity(y_g: np.ndarray, mu_g: np.ndarray, places: np.ndarray, field_id: str, ledger: control.Ledger,
                    q: float = 0.05, min_expected: float = 5.0, scales: list[scales_mod.Scale] | None = None,
                    sd: float | dict | None = None, phi: float = np.inf) -> list[Finding]:
    """Per unit of each scale (default: the municipality): does the unit's excess differ across groups
    (sex × age bands)? A likelihood-ratio heterogeneity G² of the groups' SIRs around the unit's own
    SIR, against the national group pattern (``mu_g``: B0 re-levelled to the national observed totals
    of every year and group, ``tools.Session.by_group``). Groups with μ < ``min_expected`` are pooled.

    ``phi`` is the block's NB dispersion: a group's count in a unit has variance
    Σ(μ + μ²/φ) over its cells, k_g = 1 + Σμ²/(φ Σμ) times the Poisson one, and each group's deviance
    is divided by its k_g (large units, whose cells are large, carry most of it).

    Overdispersion beyond that: at a scale of at least ``GC_MIN_UNITS`` units a genomic-control factor (the median
    G²/df of the NB-adjusted deviance); a scale of fewer units (a median over 27 states would absorb the
    departures sought) takes none, and its minimum effect is calibrated on the negatives (§8.4).
    The H0 boundary is the groups' log-SIRs spreading with sd ``sd`` (per scale): G²/c against
    non-central χ²(df, sd²·Σμ). All units of all scales are one family: BH within each scale at q/(number of scales)."""
    sc = scales or [scales_mod.municipality(places)]
    sd = GROUP_SD if sd is None else sd
    sd_of = (lambda name: sd[name]) if isinstance(sd, dict) else (lambda name: sd)
    family = f"group_disparity|B0|{field_id.split(':')[-1]}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "group_disparity", "field": field_id,
                                                               "tier": "B0", "scales": [s.name for s in sc],
                                                               "sd": {s.name: sd_of(s.name) for s in sc}}))
    rows = []                                   # (scale, unit, G2, df, c, p, Y, M)
    for s_ in sc:
        Yt, Mt = s_.sum(y_g), s_.sum(mu_g)     # [n, T, G]
        Y, M = Yt.sum(1), Mt.sum(1)
        kfac = 1.0 + (s_.sum((mu_g ** 2).sum(1)) / np.maximum(M, 1e-300) / phi if np.isfinite(phi) else 0.0)
        G2, df, big = _g2(Y, M, min_expected, kfac)
        tested = df > 0
        c = np.full(s_.n, max(float(np.median(G2[tested] / df[tested])), 1.0) if tested.any() and s_.n >= GC_MIN_UNITS
                    else 1.0)
        lam0 = sd_of(s_.name) ** 2 * (M / kfac).sum(1)
        p = np.where(tested, stats.ncx2.sf(G2 / c, np.maximum(df, 1), np.maximum(lam0, 1e-9)), 1.0)
        rows.append((s_, G2, df, c, p, Y, M))
    pool = np.concatenate([r[4] for r in rows])
    hit = _bh_by_scale([r[4] for r in rows], q)
    out, off = [], 0
    for s_, G2, df, c, p, Y, M in rows:
        for k in np.nonzero(hit[off:off + s_.n])[0]:
            sir_g = np.divide(Y[k], M[k], out=np.full(M.shape[1], np.nan), where=M[k] > 0)
            overall = Y[k].sum() / M[k].sum()
            worst = int(np.nanargmax(np.abs(np.log(np.where(M[k] >= min_expected, sir_g, np.nan) / overall))))
            mem = s_.members(k)
            locus = {"places": [int(places[u]) for u in mem], "groups": [worst]}
            if s_.name != "municipality":
                locus.update(scale=s_.name, unit=str(s_.units[k]))
            out.append(Finding("group_disparity", field_id, "B0", locus, _rr(Y[k, worst], M[k, worst] * overall),
                               float(p[k]), {"G2": float(G2[k]), "df": int(df[k]), "gc": float(c[k]),
                                             "sir": float(overall), "scale": s_.name}))
        off += s_.n
    ledger.complete(test, float(pool.min()) if pool.size else 1.0, None,
                    {"units": {r[0].name: int((r[2] > 0).sum()) for r in rows},
                     "gc": {r[0].name: float(np.median(r[3])) for r in rows}, "hits": len(out)})
    return out


def _g2(Y: np.ndarray, M: np.ndarray, min_expected: float, k: np.ndarray | float = 1.0
        ) -> tuple[np.ndarray, np.ndarray, list]:
    """G² and its df per unit (rows of Y, M [n, G]); the groups kept (μ ≥ min_expected, the rest pooled in
    one); each group's deviance divided by its variance factor ``k`` (the pooled group: M-weighted mean)."""
    n, G = Y.shape
    k = np.broadcast_to(k, Y.shape)
    G2, df, big = np.zeros(n), np.zeros(n, dtype=int), [np.zeros(G, dtype=bool)] * n
    for u in range(n):
        yy, mm = Y[u], M[u]
        b = mm >= min_expected
        big[u] = b
        if b.sum() < 2:
            continue
        kk = np.append(k[u][b], (k[u][~b] * mm[~b]).sum() / max(mm[~b].sum(), 1e-300) if (~b).any() else 1.0)
        yy = np.append(yy[b], yy[~b].sum())
        mm = np.append(mm[b], mm[~b].sum())
        keep = mm > 0
        yy, mm, kk = yy[keep], mm[keep], kk[keep]
        sir = yy.sum() / mm.sum()
        e = mm * sir
        with np.errstate(divide="ignore", invalid="ignore"):
            G2[u] = 2 * np.sum((np.where(yy > 0, yy * np.log(yy / e), 0) - (yy - e)) / kk)
        df[u] = len(yy) - 1
    return G2, df, big


def _bh_by_scale(ps: list[np.ndarray], q: float) -> np.ndarray:
    """One BH per scale at q / (number of scales), their rejections concatenated: the FDR of the family is
    then at most q (the sum of the scales' shares), and the 27 states are not tested at the price of the 5,570
    municipalities, as one BH over all units would charge them."""
    return np.concatenate([control.bh(p, q / len(ps)) for p in ps])


def _rr(observed: float, expected: float) -> float:
    """A rate ratio with a continuity correction, (y + ½)/(μ + ½): a zero count against a large
    expectation is a strong deficit, not an infinite one (ranking used log 0, survey of IX)."""
    return float((observed + 0.5) / (expected + 0.5))


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


def trend_scores(s: surprise.Surprise, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Each place's trend β_u less its graph neighbours' mean, with the sd of that difference, the minimum
    divergence δ (a ratio TREND_PERIOD between the period's first and last year, in β's standardised units),
    and which places have neighbours."""
    diff, sd, has = _contrast(s.extras["beta"], s.extras["beta_sd"], edges, "neighbours")
    return diff, sd, _trend_delta(s, "municipality"), has


def _trend_delta(s: surprise.Surprise, scale: str = "municipality", ratio: float | dict | None = None) -> float:
    # β is per standard deviation of the years: a divergence δ_β over the standardised range of
    # the period is a ratio TREND_PERIOD between its first and last year
    yrs = s.years.astype(float)
    span = (yrs.max() - yrs.min()) / max(yrs.std(), 1e-9)
    ratio = TREND_PERIOD if ratio is None else ratio          # ``ratio`` overrides the minimum divergence (the grid)
    ratio = ratio[scale] if isinstance(ratio, dict) else ratio
    return float(np.log(ratio) / span)


def _contrast(b: np.ndarray, sd: np.ndarray, edges: np.ndarray, reference: str
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The estimand's contrast of units' trends and its sd. ``neighbours``: β_u less the mean β of the
    unit's graph neighbours; ``national``: β_u itself (B1 already carries the national course of the
    field, so β is the departure from it)."""
    n = len(b)
    if reference == "national":
        return b, sd, np.ones(n, dtype=bool)
    A, S, V = np.zeros(n), np.zeros(n), np.zeros(n)
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
    return b - mean, np.sqrt(var), has


def _offset(s: surprise.Surprise) -> np.ndarray:
    """The expectation B2's trends are departures from: B1's (the stored ``offset`` of a surrogate, the
    generating mean; for fitted data B2's μ' without its place course)."""
    if "offset" in s.extras:
        return s.extras["offset"]
    st = (s.years - s.years.mean()) / max(float(s.years.std()), 1e-9)
    return s.mu / np.exp(s.extras["alpha"][:, None] + s.extras["beta"][:, None] * st[None, :])


def unit_trends(s: surprise.Surprise, scale: scales_mod.Scale) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The trend β (per sd of the years) of each unit of ``scale`` as a departure from the field's
    offset, its sd, and the unit's quasi-likelihood dispersion κ (≥ 1; its Pearson χ² per df around a smooth (cubic)
    course; 1 at the municipality, whose β is B2's shrunk estimate). A coarser unit is one NB
    cell series (Σy against Σμ, Var = Σ(μ + μ²/φ)), refitted by the same Newton as B2 with a vague prior."""
    b, sd = s.extras["beta"], s.extras["beta_sd"]
    if scale.name == "municipality":
        return b, sd, np.ones(len(b))
    off = _offset(s)
    y, o = scale.sum(s.y), scale.sum(off)
    inv = scale.sum(np.where(np.isfinite(s.phi) & (s.phi > 0), off ** 2 / np.where(np.isfinite(s.phi), s.phi, 1.0), 0.0))
    phi = np.divide(o ** 2, inv, out=np.full(o.shape, np.inf), where=inv > 0)
    st = (s.years - s.years.mean()) / max(float(s.years.std()), 1e-9)
    vague = lambda k: np.full(k, 1e-6)  # noqa: E731
    _, bb, sdd, _ = surprise.refit_place(y, o, phi, np.stack([np.ones_like(st), st], axis=1), tau=vague(2))
    # κ from a cubic course, not the line: the curvature of a real course is the estimand's own business (the
    # slope is a functional of the course), only the scatter around a smooth course is noise
    m, *_ = surprise.refit_place(y, o, phi, np.stack([st ** k for k in range(4)], axis=1), tau=vague(4))
    var = m + np.where(np.isfinite(phi), m ** 2 / np.where(np.isfinite(phi), phi, 1.0), 0.0)
    chi = np.divide((y - m) ** 2, var, out=np.zeros_like(m), where=var > 0).sum(1) / max(len(st) - 4, 1)
    kappa = np.maximum(chi, 1.0)
    return bb[:, 1], sdd[:, 1] * np.sqrt(kappa), kappa


def trend_divergence(s: surprise.Surprise, edges: np.ndarray, ledger: control.Ledger, q: float = 0.05,
                     scales: list[scales_mod.Scale] | None = None, reference: str = "neighbours",
                     ratio: float | dict | None = None) -> list[Finding]:
    """From B2: a unit's trend β against ``reference`` (two declared estimands, P4): ``neighbours``, the
    mean of its graph neighbours' β (a divergence from the surroundings), or ``national``, β itself (a
    divergence from the field's national course). Units are those of each of ``scales`` (default: the
    municipality): a trend shared by a whole state is a divergence only at the state's scale (municipality
    against neighbouring municipality, it cancels). Two-sided against the minimum divergence δ, in posterior
    sd (a coarser unit: Student t on T − 4 df, its sd inflated by its quasi-likelihood dispersion); all
    units of all scales are one family, BH within each scale at q/(number of scales), so the scales are paid
    for in the multiplicity."""
    if s.tier != "B2" or "beta" not in s.extras:
        raise ValueError("trend divergence reads B2's place trends")
    if reference not in ("neighbours", "national"):
        raise ValueError(reference)
    sc = scales or [scales_mod.municipality(s.places)]
    family = f"trend_divergence|B2|{s.field.block}" + ("" if reference == "neighbours" else "|national")
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "trend_divergence", "field": s.field.id,
                                                               "reference": reference,
                                                               "scales": [x.name for x in sc]}))
    dof = max(len(s.years) - 4, 1)
    rows = []
    for x in sc:
        b, sd, kappa = unit_trends(s, x)
        delta = _trend_delta(s, x.name, ratio)
        diff, sdd, has = _contrast(b, sd, x.edges(edges) if x.name != "municipality" else edges, reference)
        ok = has & (sdd > 0)
        d = np.divide(diff, sdd, out=np.zeros(len(b)), where=ok)
        excess = np.divide(np.abs(diff) - delta, sdd, out=np.zeros(len(b)), where=ok)
        tail = special.ndtr(-excess) if x.name == "municipality" else stats.t.sf(excess, dof)
        p = np.where(has, np.minimum(1.0, 2 * tail), 1.0)
        rows.append((x, b, mean_ref(b, diff), d, p, kappa))
    pool = np.concatenate([r[4] for r in rows])
    hit = _bh_by_scale([r[4] for r in rows], q)
    out, off = [], 0
    for x, b, ref, d, p, kappa in rows:
        for k in np.nonzero(hit[off:off + x.n])[0]:
            locus = {"places": [int(s.places[u]) for u in x.members(k)]}
            if x.name != "municipality":
                locus.update(scale=x.name, unit=str(x.units[k]))
            out.append(Finding("trend_divergence", s.field.id, "B2", locus, float(d[k]), float(p[k]),
                               {"beta": float(b[k]), "neighbours" if reference == "neighbours" else "reference":
                                float(ref[k]), "rate_ratio_per_sd_year": float(np.exp(b[k])),
                                "scale": x.name, "dispersion": float(kappa[k]), "estimand": reference}))
        off += x.n
    ledger.complete(test, float(pool.min()), None, {"units": {r[0].name: r[0].n for r in rows}, "hits": len(out)})
    return out


def mean_ref(b: np.ndarray, diff: np.ndarray) -> np.ndarray:
    """The reference trend the contrast was taken against (β less the contrast)."""
    return b - diff


def default_graph(places: np.ndarray) -> np.ndarray:
    return graphs.edges(places, graphs.DEFAULT)
