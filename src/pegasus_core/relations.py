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

**The joint model** (`factor_model`; docs/plans/2026-10-06-o7-joint-relations.md): every field's departures from its
expectation (stage B), r_{f,u,t} = log((y + ½)/(μ + ½)) with its sampling variance v_{f,u,t} from B's predictive and
noise structure (N1), are explained together by K shared space–time factors (spatial dynamic factor analysis; Lopes,
Salazar & Gamerman 2008; the shared-component model of Knorr-Held & Best 2001):

    r_{f,u,t} = Σ_k λ_{f,k} F_{k,u,t} + ε_{f,u,t},   ε ~ N(0, v_{f,u,t} + σ_f²),
    F_{·,u,t} ~ N(0, I) per cell (the space–time GMRF prior of the design note is the next step),
    λ_{f,k} ~ N(0, γ_k), γ_k by automatic relevance determination (a factor no field needs shrinks away: K by evidence).

A relation is two fields loading on one factor. The fit is the EM of probabilistic factor analysis (`factor_model`):
the cells' factor posteriors, then every field's K loadings by a small weighted ridge regression, independent across
fields. The cost grows with F·U·T·K², never with F².
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


def departures(surprises: list, support: str = "municipality") -> Departures:
    """The departures matrix from fields' expectations (`surprise.Surprise`, one tier each) over their common places
    and periods, lifted by sums to ``support`` (`fields.lift`; the ladder of supports): r = log((y + ½)/(μ + ½)),
    v = Var(y)/(μ + ½)² with Var(y) the predictive's under its noise structure, summed over the support's places (the
    delta method). A regional relation concentrates at a coarser support, where the municipal noise averages out."""
    from . import fields as fields_
    from . import surprise as sp_

    places = surprises[0].places
    periods = np.asarray(surprises[0].years)
    for s in surprises[1:]:
        places = np.intersect1d(places, s.places)
        periods = np.intersect1d(periods, np.asarray(s.years))
    rs, vs, units = [], [], None
    for s in surprises:
        ui = np.searchsorted(s.places, places)
        ti = np.searchsorted(np.asarray(s.years), periods)
        y, mu = s.y[np.ix_(ui, ti)], s.mu[np.ix_(ui, ti)]
        phi = np.broadcast_to(np.asarray(s.phi, dtype=float), s.mu.shape)[np.ix_(ui, ti)]
        bad = ((s.flags[np.ix_(ui, ti)] & (sp_.DENOMINATOR | sp_.NO_INFORMATION)) != 0) | ~np.isfinite(mu)
        var = np.where(bad, 0.0, sp_.cell_variance(mu, phi, s.noise))
        y, mu = np.where(bad, 0.0, y), np.where(bad, 0.0, mu)
        units, (y, mu, var) = fields_.lift(y, places, support)[0], (fields_.lift(x, places, support)[1] for x in (y, mu, var))
        rs.append(np.log((y + 0.5) / (mu + 0.5)))
        vs.append(np.where(mu > 0, var / (mu + 0.5) ** 2, np.inf))
    return Departures([s.field.id for s in surprises], units, periods, np.stack(rs), np.stack(vs))


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
    R = torch.as_tensor(np.where(ok, d.r.reshape(F, n), 0.0), dtype=torch.float64, device=dev)
    V = torch.as_tensor(np.where(ok, d.v.reshape(F, n), 0.0), dtype=torch.float64, device=dev)
    OK = torch.as_tensor(ok, device=dev)
    sigma2 = torch.zeros(F, dtype=torch.float64, device=dev)
    W = torch.where(OK, 1.0 / torch.where(OK, V, torch.ones_like(V)), torch.zeros_like(V))
    Z = R * W.sqrt()
    ev, vec = torch.linalg.eigh(Z @ Z.T / n)
    top = torch.argsort(ev, descending=True)[:K]
    lam = vec[:, top] * torch.sqrt(torch.clamp(ev[top], min=1e-6))
    gamma = torch.ones(K, dtype=torch.float64, device=dev)
    eye = torch.eye(K, dtype=torch.float64, device=dev)
    trace, prev = [], None
    for it in range(iterations):
        W = torch.where(OK, 1.0 / torch.where(OK, V + sigma2[:, None], torch.ones_like(V)), torch.zeros_like(V))
        A = torch.zeros((F, K, K), dtype=torch.float64, device=dev)
        b = torch.zeros((F, K), dtype=torch.float64, device=dev)
        ll = 0.0
        resid2 = torch.zeros(F, dtype=torch.float64, device=dev)
        for a0 in range(0, n, chunk):                                   # E-step by chunks of cells
            w, r = W[:, a0:a0 + chunk], R[:, a0:a0 + chunk]
            P = eye + torch.einsum("fn,fk,fj->nkj", w, lam, lam)
            L = torch.linalg.cholesky(P)
            S = torch.cholesky_inverse(L)                                # Σ_n
            m = torch.einsum("nkj,nj->nk", S, (w * r).T @ lam)            # m_n
            Ezz = S + m[:, :, None] * m[:, None, :]
            A += torch.einsum("fn,nkj->fkj", w, Ezz)
            b += (w * r) @ m
            fit = lam @ m.T
            resid2 += torch.where(OK[:, a0:a0 + chunk], (r - fit) ** 2 + torch.einsum("fk,nkj,fj->fn", lam, S, lam),
                                  torch.zeros_like(r)).sum(1)
            # the marginal log likelihood of the chunk: −½ Σ (w r² − (Λᵀ W r)ᵀ Σ (Λᵀ W r) − log|W| + log|P|)
            g = (w * r).T @ lam
            ll += float(-0.5 * ((w * r * r).sum() - torch.einsum("nk,nk->", g, m)
                                - torch.log(torch.where(w > 0, w, torch.ones_like(w))).sum()
                                + 2 * torch.log(torch.diagonal(L, dim1=1, dim2=2)).sum()))
        # M-step: the loadings with their ARD prior, then the ARD variances and the extra noise variances
        H = A + torch.diag_embed((1.0 / gamma).expand(F, K))
        lam = torch.linalg.solve(H, b[..., None])[..., 0]
        cov = torch.linalg.inv(H)
        gamma = torch.clamp((lam ** 2 + torch.diagonal(cov, dim1=1, dim2=2)).mean(0), min=1e-10)
        sigma2 = torch.clamp((resid2 - torch.where(OK, V, torch.zeros_like(V)).sum(1)) / OK.sum(1).clamp(min=1),
                             min=0.0)
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
