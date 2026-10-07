"""Departure models (ARCHITECTURE §7.0, stage C; O6): each estimand's departure read through a model of its own.

**Cell excess** (`cell_excess`): Efron's two-group model on the predictive's scores (Efron 2004, 2007, 2010; the
`locfdr` method). The field's cells' z-scores (the predictive's randomised PIT, Φ⁻¹(u), stage B with its noise
structure) are a mixture

    f(z) = π0 f0(z) + (1 − π0) f1(z),

with f estimated by Lindsey's method (a Poisson regression on the histogram's counts, a natural spline in z) and the
null f0 = N(δ0, σ0²) estimated from the centre of the distribution (central matching), so any miscalibration of the
predictive is the field's own null, never a constant set per data system. Each cell's local false discovery rate is
lfdr(z) = π0 f0(z) / f(z), reported with each finding. The reported set is chosen by the tail-area Fdr with the
empirical null (Efron 2007): BH at q on the one-sided p-values 1 − Φ((z − δ0)/σ0), scaled by π0. The tail-area form
reads the empirical survival function, where the spline's log-linear tails would make lfdr → 0 at the extremes of a
null field (5/10 null worlds of SIH pneumonia had findings by mean lfdr, 2026-10-06). Relevance (P5) is the cell's own test against the minimum relevant effect:
P(Y ≥ y | rate θ0·μ) under the predictive, which a reported cell must also pass at q.

**The ladder of supports.** Every departure model runs on the field at each support of the ladder (municipality,
immediate region, state: `scans.scales.standard`, the field lifted by sums, `surprise.lift`), and one FDR runs over
the union, so a regional departure that no single municipality shows is found where it concentrates. A finding names
its support and the municipalities it covers.
"""

from __future__ import annotations

import numpy as np
from scipy import special, stats

from . import config, control, surprise

BINS = 120


def _spline_basis(x: np.ndarray, knots: int = 7) -> np.ndarray:
    """A natural cubic spline basis (truncated power form with linear tails) over ``x``."""
    k = np.quantile(x, np.linspace(0.05, 0.95, knots))

    def d(kj: float) -> np.ndarray:
        return (np.clip(x - kj, 0, None) ** 3 - np.clip(x - k[-1], 0, None) ** 3) / (k[-1] - kj)

    cols = [np.ones_like(x), x] + [d(kj) - d(k[-2]) for kj in k[:-2]]
    B = np.column_stack(cols)
    return (B - B.mean(0)) / np.where(B.std(0) > 0, B.std(0), 1.0) + np.r_[1.0, np.zeros(B.shape[1] - 1)]


def two_group(z: np.ndarray, centre: float = 1.5) -> dict:
    """Efron's two-group fit of scores ``z``: the mixture density f (Lindsey's method), the empirical null (δ0, σ0,
    π0) by central matching on |z − median| < ``centre``·IQR-scaled spread, and lfdr at every z."""
    z = np.asarray(z, dtype=float)
    lo, hi = np.quantile(z, [0.0005, 0.9995])
    edges = np.linspace(min(lo, -4.0), max(hi, 4.0), BINS + 1)
    mid = 0.5 * (edges[1:] + edges[:-1])
    width = edges[1] - edges[0]
    counts = np.histogram(np.clip(z, edges[0], edges[-1]), edges)[0].astype(float)
    B = _spline_basis(mid)
    beta = np.zeros(B.shape[1])
    beta[0] = np.log(max(counts.mean(), 1e-3))
    for _ in range(100):                                            # Poisson regression of counts on the basis
        eta = np.clip(B @ beta, -50, 50)
        lam = np.exp(eta)
        step = np.linalg.solve(B.T @ (B * lam[:, None]) + 1e-8 * np.eye(B.shape[1]), B.T @ (counts - lam))
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    f_bins = np.exp(np.clip(B @ beta, -50, 50)) / (len(z) * width)  # the mixture density at the bin mids
    # central matching: log f is quadratic near the centre where the null dominates (Efron 2004 §4)
    med = float(np.median(z))
    spread = float(stats.iqr(z) / 1.349)
    core = np.abs(mid - med) < centre * spread
    X = np.column_stack([np.ones(core.sum()), mid[core], mid[core] ** 2])
    c0, c1, c2 = np.linalg.lstsq(X, np.log(np.maximum(f_bins[core], 1e-300)), rcond=None)[0]
    if c2 >= 0:                                                     # no curvature: fall back to the theoretical null
        delta0, sigma0, pi0 = 0.0, 1.0, 1.0
    else:
        sigma0 = float(np.sqrt(-1.0 / (2 * c2)))
        delta0 = float(c1 * sigma0 ** 2)
        pi0 = float(min(1.0, np.exp(c0 + delta0 ** 2 / (2 * sigma0 ** 2)) * np.sqrt(2 * np.pi) * sigma0))
    f_z = np.interp(z, mid, f_bins)
    f0_z = stats.norm.pdf(z, delta0, sigma0)
    lfdr = np.clip(pi0 * f0_z / np.maximum(f_z, 1e-300), 0.0, 1.0)
    return {"delta0": delta0, "sigma0": sigma0, "pi0": pi0, "lfdr": lfdr}


def bayes_select(p_null: np.ndarray, eligible: np.ndarray, q: float) -> np.ndarray:
    """The largest set of eligible units, taken in increasing posterior null probability, whose mean is at most q
    (the Bayesian FDR of §8.2; Newton et al. 2004): for a model's own posteriors."""
    idx = np.nonzero(eligible)[0]
    if idx.size == 0:
        return idx
    order = idx[np.argsort(p_null[idx])]
    running = np.cumsum(p_null[order]) / np.arange(1, len(order) + 1)
    k = int(np.max(np.nonzero(running <= q)[0])) + 1 if np.any(running <= q) else 0
    return order[:k]


def _ladder(s: surprise.Surprise, scales: list | None) -> list[tuple[surprise.Surprise, object]]:
    """The field at each support: (the Surprise there, its scale; None for the municipality itself)."""
    if not scales:
        return [(s, None)]
    return [(s, None) if sc.name == "municipality" else (surprise.lift(s, sc), sc) for sc in scales]


def _members(s: surprise.Surprise, sc, k: int) -> list[int]:
    """The municipalities of unit ``k`` of a support (``sc`` None: the municipality itself)."""
    return [int(s.places[k])] if sc is None else [int(x) for x in s.places[sc.members(k)]]


def cell_excess(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05, rate_ratio: float | None = None,
                scales: list | None = None) -> list:
    """Cell excess departures of a field (stage C) over the ladder of supports ``scales`` (None: the municipality):
    at each support Efron's two-group model on its predictive scores, its empirical-null p-values scaled by its π0;
    one BH at q over every support's cells; the minimum relevant effect as each reported cell's own test. Returns
    `lenses.Finding`s whose ``stats`` carry the support, the lfdr, the empirical null and the effect."""
    from .scans import lenses

    rr = lenses.RATE_RATIO if rate_ratio is None else rate_ratio
    family = f"cell_excess|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "departure", {"model": "two-group (Efron)", "field": s.field.id,
                                                                    "tier": s.tier}))
    parts, ps, rel = [], [], []
    for sk, sc in _ladder(s, scales):
        ok = ((sk.flags & (surprise.DENOMINATOR | surprise.NO_INFORMATION)) == 0) & np.isfinite(sk.z)
        fit = two_group(sk.z[ok])
        lfdr = np.ones(sk.z.shape)
        lfdr[ok] = fit["lfdr"]
        p = np.ones(sk.z.shape)
        p[ok] = fit["pi0"] * stats.norm.sf(sk.z[ok], fit["delta0"], fit["sigma0"])
        parts.append((sk, sc, fit, lfdr, ok))
        ps.append(p.ravel())
        rel.append(lenses._upper_tail(sk.y, rr * sk.mu, sk.phi).ravel())     # P(Y ≥ y | rate θ0·μ)
    p_all, rel_all = np.concatenate(ps), np.concatenate(rel)
    sig = control.bh(p_all, q) & (rel_all <= q)
    out, offset = [], 0
    for sk, sc, fit, lfdr, _ok in parts:
        U, T = sk.y.shape
        for i in np.nonzero(sig[offset:offset + U * T])[0]:
            out.append(lenses.Finding("cell_excess", s.field.id, s.tier,
                                      {"places": _members(s, sc, i // T), "years": [int(sk.years[i % T])]},
                                      lenses._rr(sk.y.flat[i], sk.mu.flat[i]), float(p_all[offset + i]),
                                      {"support": "municipality" if sc is None else sc.name,
                                       "unit": str(sk.places[i // T]), "observed": float(sk.y.flat[i]),
                                       "expected": float(sk.mu.flat[i]), "lfdr": float(lfdr.flat[i]),
                                       "null": {k: round(fit[k], 4) for k in ("delta0", "sigma0", "pi0")}}))
        offset += U * T
    ledger.complete(test, float(p_all.min()) if p_all.size else 1.0, None,
                    {"cells": int(sum(o.sum() for *_, o in parts)), "hits": len(out),
                     "null": {("municipality" if sc is None else sc.name): {k: round(f[k], 4) for k in ("pi0", "sigma0")}
                              for _, sc, f, _, _ in parts}})
    return out


def excess(s: surprise.Surprise, ledger: control.Ledger, spectrum, q: float = 0.05, rate_ratio: float | None = None,
           footprints: tuple[float, ...] = (1, 3, 10, 30, 100, 300), replicates: int = 40, shape: str = "spike"
           ) -> list:
    """Excess departures of a field at unknown spatial scale (stage C): the multiscale peaks of its standardised kernel
    excess on the place graph (`multiscale.peaks`, STEM with the peak-height law from the predictive's replicates),
    one BH at q over every peak of every scale and temporal contrast, the minimum relevant effect as each peak's own
    one-sided test at q, and overlapping reported peaks merged into the most significant. ``shape`` is the departure's
    course in time (`multiscale.contrasts`): ``spike`` (one period) or ``step`` (a level from a start to the end, the
    change-point question at unknown spatial scale). A finding names its scale (the footprint's effective places) and
    the places holding half its kernel's mass. No zoning enters."""
    from . import multiscale
    from .scans import lenses

    rr = lenses.RATE_RATIO if rate_ratio is None else rate_ratio
    family = f"excess:{shape}|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "departure", {"model": "multiscale graph peaks (STEM)",
                                                                    "field": s.field.id, "tier": s.tier}))
    scales = spectrum.scales(footprints)
    found, null = multiscale.peaks(s, spectrum, scales, shape=shape, replicates=replicates,
                                   seed=config.seed("excess", shape, s.field.id, s.tier), rate_ratio=rr)
    if not found:
        ledger.complete(test, 1.0, None, {"peaks": 0, "hits": 0})
        return []
    p = np.array([pk.p for pk in found])
    keep = control.bh(p, q) & (np.array([pk.relevance_z for pk in found]) >= stats.norm.isf(q))
    chosen, taken = [], []
    for i in np.argsort(p):
        if not keep[i]:
            continue
        pk = found[i]
        fp = set(multiscale.footprint(spectrum, pk.centre, pk.s))
        overlapping = [(c, other) for (c, other, w) in taken if w[0] < pk.window[1] and pk.window[0] < w[1]]
        if any(pk.centre in other or c in fp for c, other in overlapping):
            continue
        taken.append((pk.centre, fp, pk.window))
        chosen.append((pk, sorted(fp)))
    out = [lenses.Finding("excess" if shape == "spike" else f"excess_{shape}", s.field.id, s.tier,
                          {"places": [int(s.places[u]) for u in fp],
                           "years": [int(s.years[pk.window[0]]), int(s.years[pk.window[1] - 1])]},
                          float(pk.rate_ratio), float(pk.p),
                          {"centre": int(s.places[pk.centre]), "scale_places": round(pk.places, 1), "s": pk.s,
                           "height": round(pk.height, 3), "relevance_z": round(pk.relevance_z, 3)})
           for pk, fp in chosen]
    ledger.complete(test, float(p.min()), None, {"peaks": len(found), "hits": len(out),
                                                 "null_peaks_per_replicate": {str(round(k, 4)): v for k, v in null.items()}})
    return out


def _laplace_glm(y: np.ndarray, mu: np.ndarray, phi: np.ndarray, X: np.ndarray, prec: np.ndarray, temper: np.ndarray,
                 iterations: int = 12) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per place (rows), the NB GLM log μ_t + X_t·β with a N(0, prec⁻¹) prior, its likelihood tempered by ``temper``
    (the composite-likelihood adjustment for serially correlated errors): the MAP β [U, p], its covariance [U, p, p],
    and the Laplace log marginal likelihood [U]."""
    U, T = y.shape
    p = X.shape[-1]
    b = np.zeros((U, p))
    P = np.broadcast_to(prec, (U, p, p))
    for _ in range(iterations):
        eta = np.clip(np.einsum("utp,up->ut", X, b), -30, 30)
        lam = mu * np.exp(eta)
        wt = 1.0 / (1.0 + lam / phi)
        g = temper[:, None] * np.einsum("ut,utp->up", (y - lam) * wt, X) - np.einsum("upq,uq->up", P, b)
        H = temper[:, None, None] * np.einsum("ut,utp,utq->upq", lam * wt, X, X) + P
        step = np.linalg.solve(H, g[..., None])[..., 0]
        b = b + step
        if np.abs(step).max() < 1e-8:
            break
    eta = np.clip(np.einsum("utp,up->ut", X, b), -30, 30)
    lam = mu * np.exp(eta)
    wt = 1.0 / (1.0 + lam / phi)
    H = temper[:, None, None] * np.einsum("ut,utp,utq->upq", lam * wt, X, X) + P
    ll = temper * stats.nbinom.logpmf(y, phi, phi / (phi + lam)).sum(1)
    logml = (ll - 0.5 * np.einsum("up,upq,uq->u", b, P, b) + 0.5 * np.linalg.slogdet(P)[1]
             - 0.5 * np.linalg.slogdet(H)[1])
    return b, np.linalg.inv(H), logml


def step(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05, rate_ratio: float | None = None,
         min_years: int = 2, min_past: int = 3, prior_change: float = 0.05, scales: list | None = None) -> list:
    """Step departures of a field (stage C): a Bayesian single change point per place (the established product-partition
    form with one change; Barry & Hartigan 1993, Chib 1998). Model M_τ: log μ_t = log μ̂_t + a + b·x_t + δ·1[t ≥ τ],
    τ over the windows that leave ``min_past`` periods before and ``min_years`` after; M_0 has no step. Priors:
    a ~ N(0, 1) and b ~ N(0, ½²) (nuisances present in every model, so their Occam factors cancel in the Bayes
    factors; a's prior is vague because B1's place effect has already absorbed part of any step, leaving the years
    before it below their expectation: a prior on a from B1's place totals, which B1 fits by construction, pinned a at
    0 and moved 3× steps into the slope, δ 0.25 for 1.1, 2026-10-06), δ ~ N(0, 1).
    Each model's evidence is its Laplace marginal likelihood, the place's likelihood tempered by 1/(1+ρ)/(1−ρ), the
    composite-likelihood adjustment for its serial correlation under the predictive (N1). P(step) is the posterior
    mass off M_0, its prior ``prior_change``. Relevance (P5) is P(δ > log θ0 | step) ≥ 0.5 at the most probable τ.
    The reported places are the largest set, in decreasing P(step), whose mean posterior null probability is at most
    q (the Bayesian FDR), over the union of the ladder's supports ``scales`` (None: the municipality). A step is its
    own term, so the course never takes it in (the absorption of B2)."""
    from .scans import lenses

    rr = lenses.RATE_RATIO if rate_ratio is None else rate_ratio
    family = f"step|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "departure", {"model": "Bayesian single change point",
                                                                    "field": s.field.id, "tier": s.tier}))
    fits = [(sk, sc, _step_posteriors(sk, rr, min_years, min_past, prior_change)) for sk, sc in _ladder(s, scales)]
    fits = [(sk, sc, f) for sk, sc, f in fits if f is not None]
    if not fits:
        return []
    p_null = np.concatenate([f["p_null"] for *_, f in fits])
    eligible = np.concatenate([f["eligible"] for *_, f in fits])
    chosen = set(bayes_select(p_null, eligible, q).tolist())
    out, offset = [], 0
    for sk, sc, f in fits:
        for i in range(len(f["rows"])):
            if offset + i not in chosen:
                continue
            t0 = int(f["starts"][f["k"][i]])
            out.append(lenses.Finding("step", s.field.id, s.tier,
                                      {"places": _members(s, sc, int(f["rows"][i])),
                                       "years": [int(sk.years[t0]), int(sk.years[-1])]},
                                      float(np.exp(f["d"][i])), float(f["p_null"][i]),
                                      {"support": "municipality" if sc is None else sc.name,
                                       "unit": str(sk.places[f["rows"][i]]), "p_step": float(1 - f["p_null"][i]),
                                       "delta": float(f["d"][i]), "delta_sd": float(f["sd"][i]),
                                       "p_relevant": float(f["p_relevant"][i]), "start": int(sk.years[t0])}))
        offset += len(f["rows"])
    ledger.complete(test, float(p_null.min()), None, {"units": len(p_null), "hits": len(out)})
    return out


def _step_posteriors(s: surprise.Surprise, rr: float, min_years: int, min_past: int, prior_change: float
                     ) -> dict | None:
    """`step`'s model at one support: per unit, the posterior null probability, the most probable start, δ and its
    sd, P(δ > log θ0), and whether the unit is eligible (an upward, likely relevant step)."""
    from .scans import lenses

    U, T = s.y.shape
    y, mu = s.y, np.maximum(s.mu, 1e-12)
    phi = np.where(np.isfinite(s.phi), s.phi, 1e12) if np.ndim(s.phi) else np.full((U, T), s.phi)
    ok = ((s.flags & surprise.DENOMINATOR) == 0).all(1) & (mu.sum(1) > 0.5)
    rows = np.nonzero(ok)[0]
    if rows.size == 0 or min_past + min_years > T:
        return None
    y, mu, phi = y[rows], mu[rows], phi[rows]
    x = (np.arange(T) - (T - 1) / 2) / max(T - 1, 1)               # the course's slope per series length
    var_a, var_b = 1.0, 0.25
    temper = 1.0 / np.atleast_1d(surprise.trend_inflation(lenses._lag1_correlation(
        surprise.Surprise(s.field, s.tier, s.places[rows], s.years, y, mu, phi, s.u[rows], s.z[rows], s.w[rows],
                          s.flags[rows], s.calibration, noise=s.noise), _Municipal(len(rows)))))
    X0 = np.broadcast_to(np.stack([np.ones(T), x], 1), (len(rows), T, 2))
    _, _, ml0 = _laplace_glm(y, mu, phi, X0, np.diag([1 / var_a, 1 / var_b]), temper)
    starts = np.arange(min_past, T - min_years + 1)
    mls, deltas, dsd = [], [], []
    for t0 in starts:
        stepcol = (np.arange(T) >= t0).astype(float)
        X = np.broadcast_to(np.stack([np.ones(T), x, stepcol], 1), (len(rows), T, 3))
        b, cov, ml = _laplace_glm(y, mu, phi, X, np.diag([1 / var_a, 1 / var_b, 1.0]), temper)
        mls.append(ml)
        deltas.append(b[:, 2])
        dsd.append(np.sqrt(cov[:, 2, 2]))
    mls, deltas, dsd = np.array(mls).T, np.array(deltas).T, np.array(dsd).T  # [places, starts]
    log_prior = np.log(prior_change / len(starts))
    joint = np.column_stack([ml0 + np.log(1 - prior_change), mls + log_prior])
    post = np.exp(joint - special.logsumexp(joint, axis=1, keepdims=True))
    p_null = post[:, 0]
    k = post[:, 1:].argmax(1)
    d, sd = deltas[np.arange(len(rows)), k], dsd[np.arange(len(rows)), k]
    p_relevant = special.ndtr((d - np.log(rr)) / np.maximum(sd, 1e-12))
    return {"rows": rows, "p_null": p_null, "eligible": (p_relevant >= 0.5) & (d > 0), "k": k, "starts": starts,
            "d": d, "sd": sd, "p_relevant": p_relevant}


class _Municipal:
    """The municipality scale for `lenses._lag1_correlation` on a subset of places."""
    name = "municipality"

    def __init__(self, n: int):
        self.n = n
