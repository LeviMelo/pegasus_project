"""Relation models (ARCHITECTURE §7.5, O7): an exposure field's lagged effect on an outcome field's rate.

**The distributed-lag term** (Gasparrini, Armstrong & Kenward 2010; the penalised form of Gasparrini, Scheipl,
Armstrong & Kenward 2017):

    log μ_Y(u, t) = log μ̂_Y(u, t) + Σ_{ℓ=0..L} β(ℓ) · x(u, t − ℓ),

where μ̂_Y is the outcome's own fitted expectation (an offset: its season, trend, place course and profile stay the
model's, so shared seasonality is not read as a relation), x the exposure at the outcome's places and periods, and
β(ℓ) a smooth curve over lag: an RW2 penalty τ·Σ(Δ²β)², with τ chosen by the Laplace approximation of the marginal
likelihood. The counts are negative binomial with the outcome model's dispersion φ, by penalised IRLS.

This is the two-stage form, with the offset fixed at the outcome model's fit. Where the exposure is widespread, the
outcome's history has absorbed part of the lagged effect (evaluation 2026-10-06, absorption), so β is conservative.
The term inside the monolith's joint fit is the v2. It is the **pairwise confirmation** of a relation the joint model
reports (ADR-0029, stage D), never the search.

**The joint model** (stage D; docs/plans/2026-10-06-o7-joint-relations.md): which fields move together over places
and periods, at which spatial scale, and which leads which. One pipeline, no pairwise search and no zoning:

1. `innovations`: every field's departures whitened by its own predictive (N1): per place, the Pearson residuals
   times L⁻¹, LLᵀ the covariance over periods that B states. Under the model they are i.i.d. N(0, 1), so whatever
   co-varies across fields afterwards is shared, not each field's own serial dependence.
2. `bands`: the innovations on the graph Fourier basis of the place graph (`multiscale.GraphSpectrum`), split into
   frequency bands: a continuum of spatial scales from the whole country to a few neighbouring towns, set by the
   graph and not by administrative units. The transform is orthonormal, so the noise stays i.i.d. per coefficient.
3. `lagged`: each field stacked with its own past (the stacked form of a dynamic factor model).
4. `factor_model`: per band, the EM of probabilistic factor analysis with automatic relevance determination
   (Rubin & Thayer 1982; Bishop 1999): z ~ N(0, I) per coefficient, r = Λz + ε, K chosen by the ARD.
5. `relation_table`: every pair of distinct fields at every lag and band, its implied correlation ρ = (ΛΛᵀ)_fg over
   the total variances, z = ρ·√n (exact under step 1's i.i.d. null), one BH over everything.

A relation is two fields loading on one factor: statistical, never causal by itself (P16). Measured on a planted world
over the real municipal graph (evaluation 2026-10-07, factor model): no false relation in a null world and none in a
planted one, the planted lead found at its scale and lag. The cost grows with F·n·K², never with F².
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import optimize, stats


@dataclass
class LagCurve:
    """A fitted lag–response curve: β(ℓ) per lag with its standard error, the cumulative effect Σβ with its own, the
    lags where the simultaneous 95 % band excludes zero (``band``: its critical |z|), the penalty's strength and the
    NB deviance the term explains (2 Δℓ)."""
    lags: np.ndarray
    beta: np.ndarray
    se: np.ndarray
    cumulative: float
    cumulative_se: float
    tau: float
    window: list[int]
    band: float
    deviance_gain: float
    cells: int

    def summary(self) -> dict:
        return {"lags": self.lags.tolist(), "beta": np.round(self.beta, 5).tolist(), "se": np.round(self.se, 5).tolist(),
                "cumulative": round(self.cumulative, 5), "cumulative_se": round(self.cumulative_se, 5),
                "rr_per_unit": round(float(np.exp(self.cumulative)), 4), "tau": round(self.tau, 4),
                "window": self.window, "band_z": round(self.band, 3), "deviance_gain": round(self.deviance_gain, 3), "cells": self.cells}


def lag_matrix(x: np.ndarray, max_lag: int) -> np.ndarray:
    """[U, T, L+1] the exposure at lags 0..L (periods before the series' start are missing: NaN)."""
    U, T = x.shape
    out = np.full((U, T, max_lag + 1), np.nan)
    for ell in range(max_lag + 1):
        out[:, ell:, ell] = x[:, :T - ell]
    return out


def _rw2(n: int) -> np.ndarray:
    D = np.diff(np.eye(n), n=2, axis=0)
    return D.T @ D


def distributed_lag(y: np.ndarray, mu: np.ndarray, x: np.ndarray, max_lag: int, phi: float | np.ndarray = np.inf,
                    rows: np.ndarray | None = None, iterations: int = 30) -> LagCurve:
    """The penalised distributed-lag fit of counts ``y`` [U, T] on the exposure ``x`` [U, T] at lags 0..``max_lag``,
    offset by the outcome model's ``mu`` [U, T], NB with dispersion ``phi`` (scalar or per cell). ``rows`` restricts the
    places (a region; None: all). Cells whose lags reach before the series' start are left out."""
    X = lag_matrix(x, max_lag)
    sel = np.ones(y.shape, dtype=bool) if rows is None else np.zeros(y.shape, dtype=bool)
    if rows is not None:
        sel[rows] = True
    sel &= np.isfinite(X).all(2) & (mu > 0)
    yv, mv, Xv = y[sel], mu[sel], X[sel]
    ph = np.broadcast_to(np.asarray(phi, dtype=float), y.shape)[sel]
    ph = np.where(np.isfinite(ph), ph, 1e12)
    K = _rw2(max_lag + 1)
    n = max_lag + 1

    def fit(log_tau: float) -> tuple[np.ndarray, np.ndarray, float]:
        """The penalised MAP at τ = exp(log_tau); returns β, the penalised information, the Laplace log marginal."""
        tau = np.exp(log_tau)
        P = tau * K + 1e-8 * np.eye(n)       # RW2 leaves level and slope unpenalised: a vanishing ridge keeps it proper
        def objective(b: np.ndarray) -> float:
            lam = mv * np.exp(np.clip(Xv @ b, -30, 30))
            return float(np.sum(yv * np.log(lam) - (yv + ph) * np.log1p(lam / ph))) - 0.5 * b @ P @ b

        b = np.zeros(n)
        f0 = objective(b)
        for _ in range(iterations):
            eta = np.clip(Xv @ b, -30, 30)
            lam = mv * np.exp(eta)
            w = lam / (1.0 + lam / ph)                      # NB information
            g = Xv.T @ ((yv - lam) / (1.0 + lam / ph)) - P @ b
            H = Xv.T @ (Xv * w[:, None]) + P
            step = np.linalg.solve(H, g)
            t = 1.0
            while t > 1e-6:                                 # step halving on the penalised likelihood (IRLS safeguard)
                f1 = objective(b + t * step)
                if f1 >= f0 - 1e-10:
                    break
                t *= 0.5
            b, f0 = b + t * step, f1
            if np.abs(t * step).max() < 1e-9:
                break
        eta = np.clip(Xv @ b, -30, 30)
        lam = mv * np.exp(eta)
        w = lam / (1.0 + lam / ph)
        H = Xv.T @ (Xv * w[:, None]) + P
        ll = float(np.sum(stats.nbinom.logpmf(yv, ph, ph / (ph + lam))))
        # Laplace: log p(y|τ) ≈ ℓ(β̂) − ½β̂ᵀPβ̂ + ½ log|P|₊ − ½ log|H| (the RW2's rank n − 2)
        rank = n - 2
        lml = ll - 0.5 * b @ P @ b + 0.5 * rank * log_tau - 0.5 * np.linalg.slogdet(H)[1]
        return b, H, lml

    res = optimize.minimize_scalar(lambda lt: -fit(lt)[2], bounds=(-5.0, 20.0), method="bounded",
                                   options={"xatol": 1e-3})
    b, H, _ = fit(float(res.x))
    cov = np.linalg.inv(H)
    se = np.sqrt(np.diag(cov))
    one = np.ones(n)
    cum, cum_se = float(one @ b), float(np.sqrt(one @ cov @ one))
    def loglik(lam: np.ndarray) -> float:
        return float(np.sum(stats.nbinom.logpmf(yv, ph, ph / (ph + lam))))

    gain = 2 * (loglik(mv * np.exp(np.clip(Xv @ b, -30, 30))) - loglik(mv))   # the NB likelihood the fit maximises

    # the window from a simultaneous band (the max |z| over lags under the curve's own covariance; mgcv's simulated
    # band): per-lag 95 % intervals marked a lag in 22 of 100 null worlds, the band in its 5
    corr = cov / np.outer(se, se)
    draws = np.random.default_rng(0).multivariate_normal(np.zeros(n), corr, size=20000, method="cholesky")
    band = float(np.quantile(np.abs(draws).max(1), 0.95))
    window = [int(ell) for ell in range(n) if abs(b[ell]) > band * se[ell]]
    return LagCurve(np.arange(n), b, se, cum, cum_se, float(np.exp(res.x)), window, band, gain,
                    int(sel.sum()))


# ---------------------------------------------------------------------- the joint model (stage D, O7)

@dataclass
class Departures:
    """Every field's departures from its expectation on a common lattice: r and its sampling variance v, [F, U, T]
    (v infinite where a cell carries no information)."""
    fields: list[str]
    places: np.ndarray
    periods: np.ndarray
    r: np.ndarray
    v: np.ndarray


@dataclass
class Factors:
    """A fitted joint factor model: loadings λ [F, K] with their conditional sd (given the scores: too small to test
    a loading by, see `relations`), the factors' posterior means [K, U, T], each field's extra variance σ_f², its
    typical sampling variance (the harmonic mean of v + σ²), the effective number of cells, the ARD variances γ [K],
    and the fit's trace."""
    fields: list[str]
    loadings: np.ndarray
    loadings_sd: np.ndarray
    factors: np.ndarray
    sigma2: np.ndarray
    gamma: np.ndarray
    noise_var: np.ndarray = None
    cells: float = 0.0
    trace: list = field(default_factory=list)

    def relations(self) -> tuple[np.ndarray, np.ndarray]:
        """[F, F] the implied correlation of two fields' departures, ΛΛᵀ over their total variances (shared + extra +
        sampling; rotation-free), and its z against independence, ρ·√n_eff (the sampling sd of a correlation over
        n_eff cells). The z is the relation's statistic: stage D's FDR runs on it."""
        C = self.loadings @ self.loadings.T
        tot = np.diag(C) + self.sigma2 + self.noise_var
        rho = C / np.sqrt(np.outer(tot, tot))
        np.fill_diagonal(rho, 1.0)
        return rho, rho * np.sqrt(self.cells)


def factor_model(d: Departures, K: int = 10, iterations: int = 200, tol: float = 1e-6, chunk: int = 20000,
                 log=None) -> Factors:
    """The joint model of the departures ``d`` (module docstring) with up to ``K`` factors, by the EM of probabilistic
    factor analysis (Rubin & Thayer 1982) with heteroscedastic, known-plus-estimated noise per cell and automatic
    relevance determination on the loadings' columns (Bishop 1999): each cell's factor scores z ~ N(0, I) have the
    posterior N(m_n, Σ_n), Σ_n = (I + Λᵀ W_n Λ)⁻¹, and the loadings' update reads E[z zᵀ] = Σ_n + m_n m_nᵀ. The
    posterior covariance is what keeps a factor from absorbing the fields' own noise: the alternating MAP without it
    made every field load on every factor (null pairs' shared correlation to 0.83 on a planted world, 2026-10-06).
    Initialised by the leading eigenvectors of the precision-weighted departures' covariance."""
    import torch

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    F, U, T = d.r.shape
    n = U * T
    ok = np.isfinite(d.v.reshape(F, n))
    f32, f64 = torch.float32, torch.float64      # the cells' contractions in single precision (a laptop GPU runs
    R = torch.as_tensor(np.where(ok, d.r.reshape(F, n), 0.0), dtype=f32, device=dev)   # double at 1/64 the rate),
    V = torch.as_tensor(np.where(ok, d.v.reshape(F, n), 0.0), dtype=f32, device=dev)   # the sums and M-step in double
    OK = torch.as_tensor(ok, device=dev)
    sigma2 = torch.zeros(F, dtype=f32, device=dev)
    W = torch.where(OK, 1.0 / torch.where(OK, V, torch.ones_like(V)), torch.zeros_like(V))
    Z = R * W.sqrt()
    ev, vec = torch.linalg.eigh(Z @ Z.T / n)
    top = torch.argsort(ev, descending=True)[:K]
    lam = vec[:, top] * torch.sqrt(torch.clamp(ev[top], min=1e-6))
    gamma = torch.ones(K, dtype=f64, device=dev)
    eye = torch.eye(K, dtype=f32, device=dev)
    trace, prev = [], None
    for it in range(iterations):
        W = torch.where(OK, 1.0 / torch.where(OK, V + sigma2[:, None], torch.ones_like(V)), torch.zeros_like(V))
        A = torch.zeros((F, K, K), dtype=f64, device=dev)
        b = torch.zeros((F, K), dtype=f64, device=dev)
        ll = 0.0
        resid2 = torch.zeros(F, dtype=f64, device=dev)
        for a0 in range(0, n, chunk):                                   # E-step by chunks of cells
            w, r = W[:, a0:a0 + chunk], R[:, a0:a0 + chunk]
            P = eye + torch.einsum("fn,fk,fj->nkj", w, lam, lam)
            L = torch.linalg.cholesky(P)
            S = torch.cholesky_inverse(L)                                # Σ_n
            m = torch.einsum("nkj,nj->nk", S, (w * r).T @ lam)            # m_n
            Ezz = S + m[:, :, None] * m[:, None, :]
            A += torch.einsum("fn,nkj->fkj", w, Ezz).double()
            b += ((w * r) @ m).double()
            fit = lam @ m.T
            resid2 += torch.where(OK[:, a0:a0 + chunk], (r - fit) ** 2 + torch.einsum("fk,nkj,fj->fn", lam, S, lam),
                                  torch.zeros_like(r)).double().sum(1)
            # the marginal log likelihood of the chunk: −½ Σ (w r² − (Λᵀ W r)ᵀ Σ (Λᵀ W r) − log|W| + log|P|)
            g = (w * r).T @ lam
            ll += float(-0.5 * ((w * r * r).double().sum() - (g * m).double().sum()
                                - torch.log(torch.where(w > 0, w, torch.ones_like(w))).double().sum()
                                + 2 * torch.log(torch.diagonal(L, dim1=1, dim2=2)).double().sum()))
        # M-step: the loadings with their ARD prior, then the ARD variances and the extra noise variances
        H = A + torch.diag_embed((1.0 / gamma).expand(F, K))
        lam64 = torch.linalg.solve(H, b[..., None])[..., 0]
        cov = torch.linalg.inv(H)
        gamma = torch.clamp((lam64 ** 2 + torch.diagonal(cov, dim1=1, dim2=2)).mean(0), min=1e-10)
        lam = lam64.float()
        sigma2 = torch.clamp((resid2 - torch.where(OK, V, torch.zeros_like(V)).double().sum(1)) / OK.sum(1).clamp(min=1),
                             min=0.0).float()
        trace.append(round(ll, 3))
        if log and (it % 10 == 0):
            log(f"iteration {it}: log likelihood {ll:.6g}, γ {np.round(gamma.cpu().numpy(), 5).tolist()}")
        if prev is not None and abs(ll - prev) < tol * abs(ll):
            break
        prev = ll
    sd = torch.sqrt(torch.clamp(torch.diagonal(cov, dim1=1, dim2=2), min=0.0))
    # the factors' posterior means at every cell, for maps (the last E-step's)
    W = torch.where(OK, 1.0 / torch.where(OK, V + sigma2[:, None], torch.ones_like(V)), torch.zeros_like(V))
    scores = []
    for a0 in range(0, n, chunk):
        w, r = W[:, a0:a0 + chunk], R[:, a0:a0 + chunk]
        S = torch.linalg.inv(eye + torch.einsum("fn,fk,fj->nkj", w, lam, lam))
        scores.append(torch.einsum("nkj,nj->nk", S, (w * r).T @ lam))
    Fk = torch.cat(scores).T.reshape(K, U, T)
    c = lambda x: x.cpu().numpy()  # noqa: E731
    noise_var = c(OK.sum(1) / W.sum(1))
    cells = float(np.median(c(W.sum(1)) ** 2 / c((W ** 2).sum(1))))           # Kish's effective n, the fields' median
    return Factors(d.fields, c(lam), c(sd), c(Fk), c(sigma2), c(gamma), noise_var, cells, trace)


def innovations(surprises: list) -> Departures:
    """Every field's departures whitened by its own predictive (stage B, N1): per place, the Pearson residuals
    x_t = (y_t − μ_t)/√V_t have the covariance over periods Σ = diag(1 − f) + √(f_t f_s) ρ^|t−s| (f the frailty's
    share of each cell's variance, ρ the copula's correlation), so e = L⁻¹x with LLᵀ = Σ are i.i.d. N(0, 1) under the
    model: the GLS innovations. A relation, lagged or not, is read on these (`lagged`, `bands`), never on raw
    departures: each field's serial correlation, stacked with its own past, was explained by shared factors and read
    as 2,400 relations in a world of independent fields; an AR pooled over places left 35, because big places carry
    the frailty's correlation and small ones the Poisson's independence (2026-10-07). Returned with unit v."""
    from . import surprise as sp_

    places = surprises[0].places
    periods = np.asarray(surprises[0].years)
    for s in surprises[1:]:
        places = np.intersect1d(places, s.places)
        periods = np.intersect1d(periods, np.asarray(s.years))
    T = len(periods)
    out = []
    for s in surprises:
        ui = np.searchsorted(s.places, places)
        ti = np.searchsorted(np.asarray(s.years), periods)
        y, mu = s.y[np.ix_(ui, ti)], s.mu[np.ix_(ui, ti)]
        phi = np.broadcast_to(np.asarray(s.phi, dtype=float), s.mu.shape)[np.ix_(ui, ti)]
        bad = ((s.flags[np.ix_(ui, ti)] & (sp_.DENOMINATOR | sp_.NO_INFORMATION)) != 0) | ~(mu > 0)
        V = sp_.cell_variance(mu, phi, s.noise)
        x = np.where(bad, 0.0, (y - mu) / np.sqrt(np.where(bad, 1.0, V)))
        f = np.where(bad, 0.0, (V - mu) / np.where(bad, 1.0, V))
        S = np.sqrt(f[:, :, None] * f[:, None, :]) * s.noise.corr_matrix(T)[None]
        S[:, np.arange(T), np.arange(T)] = 1.0
        L = np.linalg.cholesky(S)
        out.append(np.linalg.solve(L, x[..., None])[..., 0])
    r = np.stack(out)
    return Departures([s.field.id for s in surprises], places, periods, r, np.ones(r.shape))


def lagged(d: Departures, lags: int) -> Departures:
    """The departures augmented by each field's own past (the stacked form of a dynamic factor model): field f at lag
    ℓ is ``f@ℓ``, r_{f@ℓ}(u, t) = r_f(u, t − ℓ), over the periods with every lag observed. A factor loaded by A@0 and
    B@ℓ is a relation in which A at t moves with B at t − ℓ: B leads A by ℓ periods."""
    T = len(d.periods)
    if lags >= T:
        raise ValueError(f"{lags} lags leave no period of {T}")
    r = np.concatenate([d.r[:, :, lags - ell:T - ell] for ell in range(lags + 1)])
    v = np.concatenate([d.v[:, :, lags - ell:T - ell] for ell in range(lags + 1)])
    names = [f"{f}@{ell}" for ell in range(lags + 1) for f in d.fields]
    return Departures(names, d.places, d.periods[lags:], r, v)


def bands(d: Departures, spectrum, edges_of_bands: tuple[float, ...] = (0.0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1,
                                                                        0.2, 0.5, 2.01), min_cells: int = 0, log=print
          ) -> dict[str, Departures]:
    """The departures in graph-frequency bands (`multiscale.GraphSpectrum`; no zoning): each field's departures
    standardised by their sampling sd (i.i.d. under the null), projected on the Laplacian's eigenvectors (orthonormal,
    so the noise stays i.i.d. per coefficient), and split by eigenvalue into ``edges_of_bands``. A smooth regional
    factor concentrates in the low bands, a local one in the high. Each band is a `Departures` over its coefficients
    with unit sampling variance, keyed by its label: the eigenvalue range and the effective places of the heat kernel
    at s = 1/λ (the band's spatial scale).

    A band with fewer than ``min_cells`` cells (coefficients × periods; pass the number of lagged fields to be fitted)
    is not returned, and is named in the log as unanswered: a factor model on fewer cells than variables is not
    identified, and its implied correlations are not relations. With SIH's places permuted, the national band
    (5 eigenvectors × 12 periods against 195 lagged fields) reported 42 false cross-system relations against 1
    observed, and merged up to 216 cells it reported 377 (2026-10-07, evaluation relations-real). The relations of
    the national and macro-regional scales are OPEN_QUESTIONS 9's."""
    import torch

    lam, Q = spectrum._eig
    ok = np.isfinite(d.v) & (d.v > 0)
    x = np.where(ok, d.r / np.sqrt(np.where(ok, d.v, 1.0)), 0.0)          # [F, U, T]
    F, U, T = x.shape
    X = torch.as_tensor(np.transpose(x, (1, 0, 2)).reshape(U, F * T), dtype=Q.dtype, device=Q.device)
    xh = (Q.T @ X).cpu().numpy().reshape(U, F, T).transpose(1, 0, 2)      # [F, eigen, T]
    lam_ = lam.cpu().numpy()
    out = {}
    for lo, hi in zip(edges_of_bands[:-1], edges_of_bands[1:], strict=True):
        idx = np.nonzero((lam_ >= lo) & (lam_ < hi))[0]
        if idx.size < 3:
            continue
        mid = float(np.sqrt(max(lo, lam_[idx].min(), 1e-6) * hi))
        label = f"λ {lo:g}-{hi:g} (~{spectrum.footprint(1.0 / mid):.0f} places)"
        if idx.size * T < min_cells:
            if log:
                log(f"band {label}: {idx.size * T} cells for {min_cells}: not identified by the band model; its scale "
                    "is read on the fields' courses (`course_relations`)")
            continue
        out[label] = Departures(d.fields, idx, d.periods, xh[:, idx, :], np.ones((F, idx.size, T)))
    return out


@dataclass
class SpectralFactors:
    """The joint model with each factor's own spatial spectrum (`spectral_factor_model`): loadings Λ [F, K] (each
    column of unit norm), the factors' score variances per graph-frequency band G [K, B], each field's extra variance
    σ² [F], the bands' coefficient counts n [B], labels and the effective places of their heat-kernel scale."""
    fields: list[str]
    loadings: np.ndarray
    G: np.ndarray
    sigma2: np.ndarray
    n: np.ndarray
    labels: list[str]
    places: np.ndarray
    trace: list = field(default_factory=list)

    def band(self, b) -> _BandView:
        """The fit read over band ``b`` (an index, or a list of fine bands pooled)."""
        return _BandView(self, np.atleast_1d(b))

    def report_bands(self, octaves: float = 1.5) -> dict[str, list[int]]:
        """The fine bands pooled into reporting groups ``octaves`` wide in footprint (effective places): the fine grid
        is the model's resolution; a relation is asked over scales wide enough to hold its coefficients."""
        lp = np.log2(self.places)
        edges = np.arange(lp.min(), lp.max() + octaves, octaves)
        groups: dict[str, list[int]] = {}
        for b, v in enumerate(lp):
            g = int(np.searchsorted(edges, v, side="right") - 1)
            lo, hi = 2 ** edges[g], 2 ** min(edges[g] + octaves, lp.max())
            groups.setdefault(f"~{lo:.0f}-{hi:.0f} places", []).append(b)
        return groups

    def factor_scales(self) -> list[float]:
        """Each factor's spatial scale: the effective places of the band where its spectrum peaks."""
        return [float(self.places[int(np.argmax(g))]) for g in self.G]


@dataclass
class _BandView:
    """One band of a `SpectralFactors`, read as `relation_table` reads a `Factors`."""
    fit: SpectralFactors
    b: np.ndarray

    @property
    def fields(self) -> list[str]:
        return self.fit.fields

    def relations(self) -> tuple[np.ndarray, np.ndarray]:
        L, n = self.fit.loadings, self.fit.n[self.b]
        g = (self.fit.G[:, self.b] * n).sum(1) / n.sum()                 # the factors' mean variance over the bands
        C = (L * g) @ L.T
        tot = np.diag(C) + 1.0 + self.fit.sigma2
        rho = C / np.sqrt(np.outer(tot, tot))
        np.fill_diagonal(rho, 1.0)
        return rho, rho * np.sqrt(n.sum())


def spectral_factor_model(d: Departures, spectrum, K: int = 12, n_bands: int = 24, iterations: int = 300,
                          tol: float = 1e-7, log=None) -> SpectralFactors:
    """One joint model of the (whitened, `innovations`, possibly `lagged`) departures over every spatial scale: on the
    graph Fourier coefficients x_f(k, t) of the place graph ``spectrum``,

        x(k, t) = Λ s(k, t) + ε,   s_j(k, t) ~ N(0, g_j(λ_k)),   ε_f ~ N(0, 1 + σ_f²),

    each factor j with its own spatial spectral density g_j, piecewise constant over ``n_bands`` log-spaced bands of
    the Laplacian's eigenvalues and smoothed across neighbouring bands (EM with smoothing, Silverman et al. 1990): a
    stationary process on the graph per factor (Marques et al. 2017). A factor no field needs has g → 0 everywhere.
    The bands are a fine grid on a continuum, not a choice: one fit reads every scale, a factor spanning several is
    one factor, and each reports its own scale (`SpectralFactors.factor_scales`). Under the model the posterior of
    s(k, t) depends on its band only, so the E-step costs B small K × K inversions."""
    import torch

    lam, Q = spectrum._eig
    dev = Q.device
    ok = np.isfinite(d.v) & (d.v > 0)
    x = np.where(ok, d.r / np.sqrt(np.where(ok, d.v, 1.0)), 0.0)          # [F, U, T]
    F, U, T = x.shape
    Xin = torch.as_tensor(np.transpose(x, (1, 0, 2)).reshape(U, F * T), dtype=Q.dtype, device=dev)
    X = (Q.T @ Xin).reshape(U, F, T).permute(1, 0, 2).reshape(F, U * T).float()          # [F, k·T]
    lam_ = lam.cpu().numpy()
    pos = lam_[lam_ > 1e-9]
    edges = np.concatenate([[-1.0], np.geomspace(pos.min(), 2.0 + 1e-6, n_bands)])
    band_k = np.clip(np.searchsorted(edges, lam_, side="right") - 1, 0, n_bands - 1)
    band = torch.as_tensor(np.repeat(band_k, T), device=dev)                              # [k·T]
    used = np.unique(band_k)
    B = len(used)
    remap = np.full(n_bands, -1)
    remap[used] = np.arange(B)
    band = torch.as_tensor(remap[np.repeat(band_k, T)], device=dev)
    nb = torch.bincount(band, minlength=B).float()
    mids = [float(np.sqrt(max(edges[b], pos.min()) * edges[b + 1])) for b in used]
    places = np.array([spectrum.footprint(1.0 / m) for m in mids])
    labels = [f"λ {max(edges[b], 0):.3g}-{edges[b + 1]:.3g} (~{p:.0f} places)" for b, p in zip(used, places, strict=True)]
    # initialisation: the leading components of the coefficients
    ev, vec = torch.linalg.eigh(X @ X.T / X.shape[1])
    top = torch.argsort(ev, descending=True)[:K]
    Lam = vec[:, top].float()
    G = torch.clamp(ev[top] - 1.0, min=1e-3)[:, None].repeat(1, B).float()
    sigma2 = torch.zeros(F, device=dev)
    eye = torch.eye(K, device=dev)
    onehot = torch.nn.functional.one_hot(band, B).float()                                 # [k·T, B]
    trace, prev = [], None
    for it in range(iterations):
        w = 1.0 / (1.0 + sigma2)                                                           # [F]
        LtW = Lam.T * w                                                                    # [K, F]
        P = torch.diag_embed(1.0 / G.T) + (LtW @ Lam)[None]                                # [B, K, K]
        S = torch.linalg.inv(P)                                                            # Σ_b
        Y = LtW @ X                                                                        # [K, k·T]
        m = torch.einsum("nkj,jn->kn", S[band], Y)                                         # [K, k·T]
        # sufficient statistics
        Smm = torch.einsum("kn,jn,nb->bkj", m, m, onehot)                                  # Σ_{n∈b} m mᵀ
        Ess = (S * nb[:, None, None] + Smm)                                                # [B, K, K]
        A = Ess.sum(0)
        bx = X @ m.T                                                                       # [F, K]
        Lam = bx @ torch.linalg.inv(A + 1e-6 * eye)
        # the factors' spectra, EM then smoothed in log over neighbouring bands
        Gnew = torch.diagonal(Ess, dim1=1, dim2=2).T / nb[None]                            # [K, B]
        lg = torch.log(torch.clamp(Gnew, min=1e-8))
        pad = torch.cat([lg[:, :1], lg, lg[:, -1:]], 1)
        G = torch.exp(0.25 * pad[:, :-2] + 0.5 * pad[:, 1:-1] + 0.25 * pad[:, 2:])
        # each loading column to unit norm, its scale moved into the spectrum
        norm = torch.clamp(Lam.norm(dim=0), min=1e-8)
        Lam, G = Lam / norm, G * (norm ** 2)[:, None]
        resid = X - Lam @ m
        sigma2 = torch.clamp((resid ** 2).mean(1) + torch.einsum("fk,bkj,fj,b->f", Lam, S, Lam, nb) / X.shape[1] - 1.0,
                             min=0.0)
        ll = float(-(resid ** 2).sum())
        trace.append(round(ll, 2))
        if log and it % 20 == 0:
            log(f"iteration {it}: {ll:.6g}; factor peaks {np.round(G.max(1).values.cpu().numpy(), 4).tolist()}")
        if prev is not None and abs(ll - prev) < tol * abs(ll):
            break
        prev = ll
    c = lambda a: a.detach().cpu().numpy()  # noqa: E731
    return SpectralFactors(d.fields, c(Lam), c(G), c(sigma2), c(nb), labels, places, trace)


def relation_table(fits: dict[str, Factors] | SpectralFactors, q: float = 0.05) -> list[dict]:
    """Stage D's report over fits at several supports (``fits``: support → `Factors`, on `lagged` departures or not):
    every pair of distinct fields, at relative lag ℓ ≥ 0 (one of the two at lag 0), its implied correlation and z,
    a two-sided p, and one BH at q over every pair, lag and support. A relation is statistical (P16): whether it is a
    cause, a shared driver or a shared recording artefact is stage E's question."""
    from . import control

    if isinstance(fits, SpectralFactors):
        fits = {label: fits.band(bs) for label, bs in fits.report_bands().items()}
    rows = []
    for support, fit in fits.items():
        rho, z = fit.relations()
        base = [n.split("@")[0] for n in fit.fields]
        lag = [int(n.split("@")[1]) if "@" in n else 0 for n in fit.fields]
        for i in range(len(base)):
            for j in range(i + 1, len(base)):
                if base[i] == base[j] or min(lag[i], lag[j]) != 0:
                    continue
                a, b = (i, j) if lag[i] == 0 else (j, i)       # a at lag 0; b at lag ℓ (b leads a by ℓ)
                rows.append({"support": support, "field": base[a], "leader": base[b], "lag": lag[b],
                             "rho": float(rho[i, j]), "z": float(z[i, j])})
    if not rows:
        return []
    p = 2 * stats.norm.sf(np.abs([r["z"] for r in rows]))
    keep = control.bh(p, q)
    for r, pi, k in zip(rows, p, keep, strict=True):
        r["p"], r["reported"] = float(pi), bool(k)
    return rows


def relation_map(surprises: list, spectrum, lags: int = 2, K: int = 16, q: float = 0.05, courses: bool = True,
                 direct: bool = True, ledger=None, log=None) -> dict:
    """Stage D over a set of fields (ARCHITECTURE §7.5): their N1-whitened innovations (`innovations`) in the graph's
    frequency bands (`bands`, the bands too small for the lagged fields left unanswered), each band's departures
    stacked with their own past to ``lags`` periods (`lagged`), the EM factor model with ARD per band
    (`factor_model`), and every pair, lag and band under one BH at q (`relation_table`). The scales the bands
    cannot identify are answered on the fields' courses (``courses``: `course_relations`, national and macro-regional,
    their own family at q). Returns ``rows`` (every pair, ``reported`` marking the relations), ``unanswered`` (the
    bands not fitted) and ``fields``. Every band's family and the courses' are written to ``ledger`` (a fresh
    `control.Ledger` when None) before they are fitted, and completed with their result (§9.2)."""
    from . import control

    ledger = ledger if ledger is not None else control.Ledger()
    d = innovations(surprises)
    T = len(d.periods)
    min_cells = int(np.ceil((lags + 1) * len(d.fields) * T / max(T - lags, 1)))   # lagged cells ≥ lagged fields
    unanswered: list[str] = []

    def note(msg: str) -> None:
        unanswered.append(msg)
        if log:
            log(msg)

    fits, graphs_, tests = {}, {}, {}
    fields_spec = sorted(d.fields)
    for label, db in bands(d, spectrum, min_cells=min_cells, log=note).items():
        tests[label] = ledger.register(control.Hypothesis(f"relation|{label}", "scan", {
            "model": "band factor model on N1 innovations", "fields": fields_spec, "lags": lags, "K": K}))
        dl = lagged(db, lags)
        fits[label] = factor_model(dl, K=K)
        if direct:
            graphs_[label] = direct_relations(dl, fits[label])
        if log:
            log(f"band {label}: {db.r.shape[1]} coefficients, "
                f"{int((fits[label].gamma > 1e-3 * fits[label].gamma.max()).sum())} factors kept")
    rows = relation_table(fits, q=q)
    for label, tid in tests.items():
        mine = [r for r in rows if r["support"] == label]
        ledger.complete(tid, float(min((r["p"] for r in mine), default=1.0)), None,
                        {"pairs": len(mine), "reported": sum(r["reported"] for r in mine)})
    for r in rows:              # direct given the factors (§7.6), or carried by a shared driver
        g = graphs_.get(r["support"])
        if g is not None:
            names = g["fields"]
            i, j = names.index(f"{r['field']}@0"), names.index(f"{r['leader']}@{r['lag']}")
            r["partial"] = float(g["partial"][i, j])
            # direct given the factors when the residual keeps the relation's sign; a partial of the other sign is the
            # factors over-explaining a shared movement (dengue deaths and admissions: ρ +0.44, partial −0.38, 2026-10-07)
            r["direct"] = abs(r["partial"]) > 1e-8 and np.sign(r["partial"]) == np.sign(r["rho"])
    if courses:
        tid = ledger.register(control.Hypothesis("relation|courses", "scan", {
            "model": "national and macro-regional courses, phase surrogates", "fields": fields_spec, "lags": lags}))
        cr = course_relations(surprises, lags=lags, q=q)
        ledger.complete(tid, float(min((r["p"] for r in cr), default=1.0)), None,
                        {"pairs": len(cr), "reported": sum(r["reported"] for r in cr)})
        rows += cr
        if log:
            log(f"courses: {sum(r['reported'] for r in rows if r['support'] in ('national', 'macro-regional'))} "
                "national and macro-regional relations")
    return {"rows": rows, "unanswered": unanswered, "fields": d.fields}



# ---------------------------------------------------------------------- the national and macro-regional courses


def phase_surrogates(x: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """[n, T] surrogates of a series with its power spectrum kept and its phases drawn at random (Theiler et al.
    1992): its own autocorrelation stays, any relation to another series is destroyed."""
    T = len(x)
    f = np.fft.rfft(x - x.mean())
    ph = rng.uniform(0, 2 * np.pi, (n, len(f)))
    ph[:, 0] = 0.0
    if T % 2 == 0:
        ph[:, -1] = 0.0                                  # the Nyquist term stays real
    return np.fft.irfft(np.abs(f)[None, :] * np.exp(1j * ph), n=T) + x.mean()


def course_relations(surprises: list, lags: int = 2, q: float = 0.05, replicates: int = 999, seed: int = 0) -> list[dict]:
    """Relations at the scales the band factor model cannot identify (OPEN_QUESTIONS 9): each field's course as the
    yearly log ratio of observed to expected, nationally and in each macro-region (the IBGE code's first digit). A
    pair's statistic at lag ℓ is the correlation of follower(t) with leader(t − ℓ), pooled over the regions after
    centring each region's series. Its null comes from phase surrogates of the leader's series (`phase_surrogates`),
    which keep each series' own autocorrelation, so the test has the T periods' degrees of freedom and no more; a
    place permutation is no null here, as it keeps every course (evaluation 2026-10-07, relations real). Two
    supports: ``national`` and ``macro-regional``. Rows as `relation_table`'s, with one BH at q over them all."""
    from . import control

    rng = np.random.default_rng(seed)
    names = [s.field.id for s in surprises]
    places = np.asarray(surprises[0].places).astype(np.int64)
    regions = places // 100000
    supports = {"national": [np.ones(len(places), dtype=bool)],
                "macro-regional": [regions == r for r in np.unique(regions)]}
    rows = []
    for support, masks in supports.items():
        series = []                                      # [F][R] the centred log-ratio courses
        for s in surprises:
            pl = np.asarray(s.places).astype(np.int64)
            per = []
            for mk in masks:
                sel = np.isin(pl, places[mk])
                o, e = s.y[sel].sum(0), s.mu[sel].sum(0)
                lr = np.log((o + 0.5) / (e + 0.5))
                per.append(lr - lr.mean())
            series.append(per)
        T = len(series[0][0])
        surrogates = [[phase_surrogates(x, replicates, rng) for x in per] for per in series]   # once per field
        for i in range(len(names)):
            for j in range(len(names)):
                if i == j:
                    continue
                for ell in range(lags + 1):
                    if ell == 0 and j < i:
                        continue                         # lag 0 is symmetric: each pair once
                    a = np.concatenate([x[ell:] for x in series[i]])
                    b_series = series[j]
                    b = np.concatenate([x[:T - ell] for x in b_series])
                    r = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0
                    sur = np.concatenate([x[:, :T - ell] for x in surrogates[j]], 1)
                    sur = sur - sur.mean(1, keepdims=True)
                    ac = a - a.mean()
                    rs = (sur @ ac) / np.maximum(np.linalg.norm(sur, axis=1) * np.linalg.norm(ac), 1e-300)
                    p = (1 + int(np.sum(np.abs(rs) >= abs(r)))) / (replicates + 1)
                    rows.append({"support": support, "field": names[i], "leader": names[j], "lag": ell, "rho": r,
                                 "z": float(stats.norm.isf(p / 2) * np.sign(r)), "p": p})
    if rows:
        keep = control.bh(np.array([r["p"] for r in rows]), q)
        for r, k in zip(rows, keep, strict=True):
            r["reported"] = bool(k)
    return rows


# ---------------------------------------------------------------------- direct relations: sparse + low rank (§7.6)


def direct_relations(d: Departures, fit: Factors, lambdas: tuple[float, ...] = (0.5, 0.35, 0.25, 0.18, 0.12, 0.08, 0.05),
                     subsamples: int = 20, beta: float = 0.05, seed: int = 0) -> dict:
    """Which of a band's relations are direct (ARCHITECTURE §7.6): the latent-variable graphical model of
    Chandrasekaran, Parrilo & Willsky (2012), the precision of the fields' departures as sparse minus low rank. The low
    rank is the factor model's (``fit``, on the same departures ``d``); the sparse part is the graphical lasso of
    the residual r − ΛF, its penalty chosen by StARS (Liu, Roeder & Wasserman 2010): the least penalty whose edges
    are stable across ``subsamples`` subsamples of 10√n cells (instability ≤ ``beta``). A relation the factors carry
    and the sparse graph does not is a shared driver; one in the graph is direct given the factors. Returns the
    partial correlations [F, F], the chosen penalty and the instability path."""
    import warnings

    from sklearn.covariance import graphical_lasso

    warnings.filterwarnings("ignore", module="sklearn")    # its convergence notices, once per subsample
    F = len(d.fields)
    R = d.r.reshape(F, -1)
    ok = np.isfinite(d.v.reshape(F, -1)).all(0) & np.isfinite(R).all(0)
    low = np.einsum("fk,kn->fn", fit.loadings, fit.factors.reshape(fit.factors.shape[0], -1))
    X = (R - low)[:, ok]
    X = (X - X.mean(1, keepdims=True)) / np.maximum(X.std(1, keepdims=True), 1e-12)
    n = X.shape[1]
    rng = np.random.default_rng(seed)
    b = int(min(n, max(10 * np.sqrt(n), 5 * F)))
    path = []
    chosen = lambdas[0]
    for lam in sorted(lambdas, reverse=True):
        freq = np.zeros((F, F))
        for _ in range(subsamples):
            idx = rng.choice(n, b, replace=False)
            S = np.corrcoef(X[:, idx])
            try:
                _, P = graphical_lasso(S, alpha=lam, max_iter=200)
            except FloatingPointError:
                continue
            freq += np.abs(P) > 1e-8
        theta = freq / subsamples
        off = ~np.eye(F, dtype=bool)
        instab = float(np.mean(2 * theta[off] * (1 - theta[off])))
        path.append({"lambda": lam, "instability": round(instab, 4)})
        if instab > beta:
            break                                       # StARS: the least penalty before the edges turn unstable
        chosen = lam
    _, P = graphical_lasso(np.corrcoef(X), alpha=chosen, max_iter=500)
    dg = np.sqrt(np.diag(P))
    partial = -P / np.outer(dg, dg)
    np.fill_diagonal(partial, 1.0)
    return {"partial": partial, "lambda": chosen, "path": path, "fields": d.fields}
