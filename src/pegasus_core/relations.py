"""Relation models (ARCHITECTURE §7.5, §8.1; BACKLOG 3.5): how fields move together, and an exposure's lagged effect.

**The relation estimator** (stage D; `relation_map`, `relation_estimate`): one estimator of the time-varying pair
relation, at every spatial support from the finest graph band to the national course.

*Estimand.* The lagged association of a follower's and a leader's innovations: ρ_s(f, g, ℓ), the correlation of
follower f at t with leader g at t − ℓ over the coefficients of a support s. A support is a linear map of the places:
the graph Fourier bands (`multiscale.GraphSpectrum`; a continuum of spatial scales, which read as distance as well,
since a relation present in the low bands and absent in the high holds between places far apart), the macro-regions'
courses and the national course (information-weighted sums, the optimal weights for a common multiplicative
departure). The estimator is the same at every support; only the map differs.

*Innovations.* Every field's departures whitened by its own predictive (`innovations`, N1), so what two fields share
is not each one's serial dependence: i.i.d. N(0, 1) under the model.

*Null.* The statistic is a sum of the follower's values times the leader's Fourier coefficients, so its null is
the leader's **circular shifts**, one for every place and coefficient: a surrogate that keeps the leader's whole
spectrum and spatial structure (every cross-spectrum between places) and its nonlinear structure, and breaks its
timing against the follower (the same variance as the phase surrogates of Theiler et al. 1992 and Prichard &
Theiler 1994, whose Gaussian tail it does not share). All
T shifts of one pair come from one FFT (`_cross`); the null is the shifts clear of the tested lags (a relation lifts
its own neighbourhood and would otherwise widen its own null), and its tail is the Student-t whose degrees of freedom
are the smaller of the shifts' kurtosis's and their effective count (`_null_moments`, `_tail_p`): a leader whose
energy sits in a few periods, an epidemic, has a null far from normal, and the normal tail on the phase surrogates'
closed-form variance called place-permuted copies related 2-4 times too often below p = 0.001. There is no draw and
no p-value floor, and the tail is an extrapolation from the shifts, characterised on negative controls (evaluation
2026-10-11-relation-estimator). At lag 0 the larger p of the two orders is used. One BH at q over every support, pair
and lag.

*Where found: partial.* A reported relation is re-read conditionally: the follower is residualised on the lags of
every other field that has a reported relation with the follower or the leader at that support (ridge with its
penalty chosen by generalised cross-validation), and the same estimator, with the same shift null, tests
the residual against the leader. ``partial`` is the partial correlation and ``direct`` marks a relation that stays
at q with its sign (a relation carried by another found field is a shared driver, not a direct one).

*The lag profile* is the rows of one pair and support over ℓ, and, as one test, the cumulative association over the
lags 1..L (`profiles`). What the estimator does not give is the effect in the outcome's units: that is the
distributed-lag term below.

**The distributed-lag term** (Gasparrini, Armstrong & Kenward 2010; the penalised form of Gasparrini, Scheipl,
Armstrong & Kenward 2017; `Session.relation`):

    log μ_Y(u, t) = log μ̂_Y(u, t) + Σ_{ℓ=0..L} β(ℓ) · x(u, t − ℓ),

where μ̂_Y is the outcome's own fitted expectation (an offset: its season, trend, place course and profile stay the
model's, so shared seasonality is not read as a relation), x the exposure at the outcome's places and periods, and
β(ℓ) a smooth curve over lag: an RW2 penalty τ·Σ(Δ²β)², with τ chosen by the Laplace approximation of the marginal
likelihood. The counts are negative binomial with the outcome model's dispersion φ, by penalised IRLS. It answers
what the estimator cannot: how large the effect is (a rate ratio per unit of exposure, in the count likelihood where
a rare outcome's cells are mostly zero) and its smooth joint lag shape with a simultaneous band. It is the
**pairwise confirmation** of a relation the estimator reports (ADR-0029), never the search; it carries no null of its
own (a debt: the estimator's shift null of the exposure is the null to attach).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, stats

#: the graph-frequency bands the place graph's coefficients are split into (eigenvalue edges of the normalised Laplacian)
BAND_EDGES = (0.0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 2.01)


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



# ---------------------------------------------------------------------- the relation estimator (stage D)

@dataclass
class Departures:
    """Every field's innovations on a common lattice: r and its sampling variance v, [F, U, T] (v infinite where a cell
    carries no information), and ``w`` [F, U] the place's information weight (√ its mean cell variance; None: equal),
    which weights the places in the regional and national courses."""
    fields: list[str]
    places: np.ndarray
    periods: np.ndarray
    r: np.ndarray
    v: np.ndarray
    w: np.ndarray | None = None




def innovations(surprises: list) -> Departures:
    """Every field's departures whitened by its own predictive (stage B, N1): per place, the Pearson residuals
    x_t = (y_t − μ_t)/√V_t have the covariance over periods Σ = diag(1 − f) + √(f_t f_s) ρ^|t−s| (f the frailty's
    share of each cell's variance, ρ the copula's correlation), so e = L⁻¹x with LLᵀ = Σ are i.i.d. N(0, 1) under the
    model: the GLS innovations. A relation, lagged or not, is read on these (`lagged`, `bands`), never on raw
    departures: each field's serial correlation, stacked with its own past, was explained by shared factors and read
    as 2,400 relations in a world of independent fields; an AR pooled over places left 35, because big places carry
    the frailty's correlation and small ones the Poisson's independence (2026-10-07). Returned with unit v and the places' information weights."""
    from . import surprise as sp_

    places = surprises[0].places
    periods = np.asarray(surprises[0].years)
    for s in surprises[1:]:
        places = np.intersect1d(places, s.places)
        periods = np.intersect1d(periods, np.asarray(s.years))
    T = len(periods)
    out, wts = [], []
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
        wts.append(np.sqrt(np.where(bad, 0.0, V).mean(1)))
    r = np.stack(out)
    return Departures([s.field.id for s in surprises], places, periods, r, np.ones(r.shape), np.stack(wts))


def context_innovations(name: str, k: np.ndarray, n: np.ndarray, places: np.ndarray, periods: np.ndarray,
                        family: str, iterations: int = 50) -> Departures:
    """A time-varying context's departures on the same footing as a field's (`innovations`; ARCHITECTURE §8.2): its own
    predictive, the context's numerator k [U, T] against its denominator n (``binomial``: k of n, the samples with E. coli
    present of those assessed; ``poisson``: k on the exposure n, beds per resident; ``gaussian``: the mean level k/n, a
    temperature over the months observed, weighted by n, identity link) with a place and a period effect on
    the link scale (the place's level and the nation's course are the expectation, as B1 is a field's), a
    quasi-likelihood dispersion φ, and the within-place serial correlation of the Pearson residuals as an AR(1) pooled
    over places, whitened as a field's frailty is. A cell with no denominator carries no information (v infinite).
    What remains is the place-period departure from its own level and the national course, which a field's departures
    are related to over lags and supports (`relation_map`): an association with that adjustment set, never an effect."""
    from scipy.special import expit

    obs = np.isfinite(k) & np.isfinite(n) & (n > 0)
    k0, n0 = np.where(obs, k, 0.0), np.where(obs, n, 0.0)
    T = k.shape[1]
    rate = k0.sum() / max(n0.sum(), 1e-12)
    a = np.zeros(k.shape[0])
    b = np.full(T, rate if family == "gaussian" else
                np.log(rate / (1 - rate)) if family == "binomial" and 0 < rate < 1 else np.log(max(rate, 1e-12)))
    ridge = 1.0               # places with a few samples shrink toward the national level, not to their raw share

    def score(a_: np.ndarray, b_: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        eta = a_[:, None] + b_[None, :]
        if family == "binomial":
            p = expit(eta)
            E, V = n0 * p, n0 * p * (1 - p)
        elif family == "gaussian":
            E, V = n0 * eta, n0          # the level's variance per unit of n: its scale is the dispersion φ below
        else:
            E = n0 * np.exp(eta)
            V = E
        return k0 - E, V, E, V

    for _ in range(iterations):
        g, h, _, _ = score(a, b)
        a += (g.sum(1) - ridge * a) / (h.sum(1) + ridge)
        g, h, _, _ = score(a, b)
        b += g.sum(0) / np.maximum(h.sum(0), 1e-12)
    _, _, E, V = score(a, b)
    ok = obs & (V > 1e-12)
    x = np.where(ok, (k0 - E) / np.sqrt(np.where(ok, V, 1.0)), 0.0)
    dof = max(int(ok.sum()) - int(ok.any(1).sum()) - T, 1)
    phi = float((x ** 2).sum()) / dof
    # a count's dispersion is never below the law's (1); a level's is its whole scale, any size
    phi = max(phi, 1e-12) if family == "gaussian" else max(phi, 1.0)
    x = x / np.sqrt(phi)
    both = ok[:, 1:] & ok[:, :-1]
    rho = float(np.clip((x[:, 1:] * x[:, :-1])[both].sum() / max((x[:, :-1] ** 2)[both].sum(), 1e-12), -0.9, 0.9))
    L = np.linalg.cholesky(rho ** np.abs(np.subtract.outer(np.arange(T), np.arange(T))))
    e = np.linalg.solve(L, x[..., None])[..., 0]
    return Departures([name], places, periods, e[None], np.where(ok, 1.0, np.inf)[None],
                      np.sqrt(np.where(ok, V, 0.0).mean(1))[None])


def _bands(d: Departures, spectrum, edges: tuple[float, ...], log=None) -> dict[str, np.ndarray]:
    """The innovations on the place graph's Fourier basis (orthonormal, so the noise stays i.i.d. per coefficient),
    split by eigenvalue into ``edges``: label → [F, m, T] coefficients. A smooth regional factor concentrates in the
    low bands, a local one in the high; the label names the eigenvalue range and the effective places of the heat
    kernel at s = 1/λ (the band's spatial scale). A band of fewer than three coefficients is not returned."""
    import torch

    lam, Q = spectrum._eig
    ok = np.isfinite(d.v) & (d.v > 0)
    x = np.where(ok, d.r / np.sqrt(np.where(ok, d.v, 1.0)), 0.0)          # [F, U, T]
    F, U, T = x.shape
    X = torch.as_tensor(np.transpose(x, (1, 0, 2)).reshape(U, F * T), dtype=Q.dtype, device=Q.device)
    xh = (Q.T @ X).cpu().numpy().reshape(U, F, T).transpose(1, 0, 2)      # [F, eigen, T]
    lam_ = lam.cpu().numpy()
    out = {}
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        idx = np.nonzero((lam_ >= lo) & (lam_ < hi))[0]
        if idx.size < 3:
            if log:
                log(f"band λ {lo:g}-{hi:g}: {idx.size} coefficients, fewer than 3: unanswered")
            continue
        mid = float(np.sqrt(max(lo, lam_[idx].min(), 1e-6) * hi))
        out[f"λ {lo:g}-{hi:g} (~{spectrum.footprint(1.0 / mid):.0f} places)"] = xh[:, idx, :]
    return out


def _courses(d: Departures) -> dict[str, np.ndarray]:
    """The national and macro-regional courses (the IBGE code's first digit): each field's innovations summed over the
    region's places with the places' information weights ``d.w`` (√V: the optimal weights for a departure common to
    the region), over √Σw², so a course is N(0, 1) per period under the model. {"national": [F, 1, T],
    "macro-regional": [F, R, T]}."""
    ok = np.isfinite(d.v) & (d.v > 0)
    x = np.where(ok, d.r / np.sqrt(np.where(ok, d.v, 1.0)), 0.0)
    w = np.ones(x.shape[:2]) if d.w is None else d.w
    region = np.asarray(d.places).astype(np.int64) // 100000
    groups = {"national": [np.ones(len(region), dtype=bool)]}
    if len(np.unique(region)) > 1:               # one region is the national course again
        groups["macro-regional"] = [region == r for r in np.unique(region)]
    out = {}
    for label, masks in groups.items():
        out[label] = np.stack([np.einsum("fu,fut->ft", w[:, m], x[:, m, :]) / np.sqrt(
            np.maximum((w[:, m] ** 2).sum(1), 1e-300))[:, None] for m in masks], axis=1)
    return out


def _standardise(a: np.ndarray) -> np.ndarray:
    """[F, m, T] centred in time per coefficient and scaled to unit root mean square per field (a field with no
    information stays zero)."""
    a = a - a.mean(2, keepdims=True)
    rms = np.sqrt((a ** 2).mean((1, 2), keepdims=True))
    return a / np.where(rms > 0, rms, 1.0)


def _cross(follow: np.ndarray, lead: np.ndarray, lags: list[int], first: int
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The statistic S(ℓ) = Σ_k Σ_{t ≥ first} follow(k, t) · lead(k, t − ℓ) of every follower [P, m, T] against every
    leader [Q, m, T] ([P, Q, len(lags)]), with its null's variance and degrees of freedom ([P, Q], `_null_moments`)
    and the statistic at every circular shift ([P, Q, T]; the lags are its first entries).

    The null is the same statistic over the shifts of the leader (``first`` is the largest lag): a circular shift
    keeps the leader's whole structure, nonlinear included (a spike stays a spike), and breaks its timing against the
    follower. The shifts S(τ) = Re Σ_ω Ñ(ω) e^{−2πiωτ/T}, Ñ(ω) = (1/T) Σ_{t ≥ first} Σ_k follow(k, t) ĝ(k, ω)
    e^{2πiωt/T}, are one FFT of a cross-spectrum; over all T of them the second moment is Σ_ω |Ñ(ω)|², which is
    also the variance over the phase surrogates (one phase per frequency, common to all coefficients: Prichard &
    Theiler 1994) in closed form. A relation lifts the shifts near its own lag, and a null that contains it is
    wide where it should be narrow, so the null is the shifts outside the tested lags and as many on either side
    (τ in (2·first, T − first)), which are exchangeable with the observed one under independence (`_null_moments`)."""
    T = follow.shape[2]
    Fl = np.fft.fft(lead, axis=2)                                            # [Q, m, ω]
    M = np.tensordot(follow * (np.arange(T) >= first), Fl, axes=([1], [1])).transpose(0, 2, 1, 3)   # [P, Q, t, ω]
    t = np.arange(T)
    Nt = np.einsum("pqtw,tw->pqw", M, np.exp(2j * np.pi * np.outer(t, t) / T), optimize=True) / T
    shifts = np.fft.fft(Nt, axis=-1).real                                    # [P, Q, τ]: S at every circular shift
    var, df = _null_moments(shifts[..., 2 * first + 1:T - first], shifts)
    return shifts[..., lags], var, df, shifts


#: the smallest effective size of the clear shifts for which they, and not all T, are the null: the variance of a
#: sample of n_eff draws is known to 1/√(2 n_eff) (24 % at 10), and below it the clear shifts of a short series
#: (T = 48, L = 12: 11 smooth ones) called 119 of 225 rows related on two epidemic waves (evaluation 2026-10-11)
NULL_MIN_EFFECTIVE = 10.0


def _moments(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Variance, effective size and kurtosis-based degrees of freedom of a null sample [..., n] (mean zero: the leader
    is centred). The effective size is n over 1 + 2 Σ ρ_k, the positive autocorrelations of the shifts (smooth in τ
    when the series are); the kurtosis's degrees of freedom are 3 + 6/(ν − 4) solved for ν."""
    n = x.shape[-1]
    var = (x ** 2).mean(-1)
    kurt = (x ** 4).mean(-1) / np.maximum(var ** 2, 1e-300)
    ss = np.maximum((x ** 2).sum(-1), 1e-300)
    rho = np.stack([(x[..., :-k] * x[..., k:]).sum(-1) / ss * (1 - k / n) for k in range(1, max(n // 3, 1) + 1)], -1)
    neff = n / (1 + 2 * np.clip(rho, 0, 1).sum(-1))
    excess = kurt - 3.0
    return var, neff, np.where(excess > 1e-6, 4.0 + 6.0 / np.maximum(excess, 1e-6), np.inf)


def _null_moments(clear: np.ndarray, every: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The variance of the null and the degrees of freedom of the Student-t that stands for it. A leader whose
    energy sits in a few periods (an epidemic, an outbreak) has a null far from normal, one shift carrying the
    alignment, so ν is the smaller of the kurtosis's and the effective size less one. The null is the shifts clear of
    the tested lags (``clear``) where their effective size is at least `NULL_MIN_EFFECTIVE`, else every shift
    (``every``; its second moment is the phase surrogates' closed-form variance), per pair."""
    var_c, neff_c, nu_c = _moments(clear) if clear.shape[-1] >= 4 else (None, None, None)
    var_a, neff_a, nu_a = _moments(every)
    if var_c is None:
        return var_a, np.maximum(np.minimum(nu_a, neff_a - 1.0), 2.05)
    ok = neff_c >= NULL_MIN_EFFECTIVE
    var = np.where(ok, var_c, var_a)
    df = np.where(ok, np.minimum(nu_c, neff_c - 1.0), np.minimum(nu_a, neff_a - 1.0))
    return var, np.maximum(df, 2.05)


def _tail_p(S: np.ndarray, var: np.ndarray, df: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two-sided p and its z-equivalent for the statistic ``S`` against a null of variance ``var``: the Student-t with
    ``df`` degrees of freedom (`_null_moments`) scaled to that variance. A normal tail on the closed-form variance
    called place-permuted copies of real fields related 2-4 times too often below p = 0.001 (evaluation 2026-10-11)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(var > 1e-300, S / np.sqrt(var), 0.0)
    p = np.clip(2 * stats.t.sf(np.abs(z) * np.sqrt(df / (df - 2.0)), df), 1e-300, 1.0)
    return p, np.sign(z) * stats.norm.isf(p / 2)


def _ridge_residual(Y: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """The columns of Y [n, c] net of the regressors Z [n, p], each by a ridge whose penalty minimises the generalised
    cross-validation criterion n·RSS/(n − df)² over a wide grid: the strength is learned from the data, and a Z with
    more columns than cells (a national course of a dozen periods) shrinks instead of fitting."""
    n = Z.shape[0]
    U, s, _ = np.linalg.svd(Z, full_matrices=False)
    UtY = U.T @ Y
    grid = max(s.max(), 1e-12) ** 2 * np.logspace(-8, 2, 41)
    sh = s[None, :] ** 2 / (s[None, :] ** 2 + grid[:, None])                  # [G, r]
    out = np.empty_like(Y)
    for j in range(Y.shape[1]):
        c = UtY[:, j]
        rss = float(Y[:, j] @ Y[:, j]) - ((2 * sh - sh ** 2) * (c ** 2)[None, :]).sum(1)
        df = sh.sum(1)
        gcv = np.where(n - df > 1e-6, n * rss / np.maximum(n - df, 1e-6) ** 2, np.inf)
        g = int(np.argmin(gcv))
        out[:, j] = Y[:, j] - U @ (sh[g] * c)
    return out


def _support_rows(label: str, a: np.ndarray, names: list[str], lags: int) -> tuple[list[dict], list[dict]]:
    """Every pair, lag and direction at one support: the follower f at t against the leader g at t − ℓ (lag 0 once
    per pair, with the larger p of its two orders), and the lag profiles (`_profiles`)."""
    F, _, T = a.shape
    a = _standardise(a)
    ells = list(range(lags + 1))
    S, V, DF, shifts = _cross(a, a, ells, lags)
    nf = np.sqrt((a[:, :, lags:] ** 2).sum((1, 2)))                                              # follower window
    ng = np.stack([np.sqrt((a[:, :, lags - ell:T - ell] ** 2).sum((1, 2))) for ell in ells], 1)   # leader window at ℓ
    P, Z = _tail_p(S, V[..., None], DF[..., None])
    rows = []
    for f in range(F):
        for g in range(F):
            if f == g:
                continue
            for ell in ells:
                if ell == 0 and g < f:
                    continue
                p, z = P[f, g, ell], Z[f, g, ell]
                if ell == 0 and P[g, f, 0] > p:                 # lag 0 is symmetric: the larger p of the two orders
                    p, z = P[g, f, 0], Z[g, f, 0]
                den = nf[f] * ng[g, ell]
                rows.append({"support": label, "field": names[f], "leader": names[g], "lag": ell,
                             "rho": float(S[f, g, ell] / den) if den > 0 else 0.0, "z": float(z), "p": float(p),
                             "_f": f, "_g": g})
    return rows, _profiles(label, names, S, shifts, nf, ng, lags)


def _profiles(label: str, names: list[str], S: np.ndarray, shifts: np.ndarray, nf: np.ndarray, ng: np.ndarray,
              lags: int) -> list[dict]:
    """The lag profile of every ordered pair at one support, as the cumulative association of the leader strictly
    preceding the follower, ℓ = 1..L (the cumulative effect of a distributed-lag term, Gasparrini et al. 2010): the
    sum of S(ℓ) over those lags, tested against the same statistic at every circular shift of the leader (`_cross`),
    so the profile is one test per pair and support where its lags are L, and the lag of its largest term (``peak``)
    is read from the lag rows. ``rho`` is the mean of the lag correlations."""
    T = shifts.shape[2]
    if lags < 1:
        return []
    window = np.arange(1, lags + 1)
    cum = shifts[..., (np.arange(T)[:, None] + window[None, :]) % T].sum(-1)           # [F, F, τ]: Σ_ℓ S(τ + ℓ)
    var, df = _null_moments(cum[..., 2 * lags:T - 2 * lags], cum)       # windows clear of the tested one and its neighbours
    P, Z = _tail_p(cum[..., 0], var, df)
    F = len(names)
    out = []
    for f in range(F):
        for g in range(F):
            if f == g:
                continue
            rho = np.array([S[f, g, ell] / (nf[f] * ng[g, ell]) if nf[f] * ng[g, ell] > 0 else 0.0 for ell in window])
            out.append({"support": label, "field": names[f], "leader": names[g], "rho": float(rho.mean()),
                        "z": float(Z[f, g]), "p": float(P[f, g]),
                        "peak": int(window[np.argmax(rho * np.sign(rho.sum() or 1.0))])})
    return out


def _direct(a: np.ndarray, rows: list[dict], lags: int, q: float) -> None:
    """Partial and direct for the reported ``rows`` of one support (module docstring): the follower, and the leader's
    window, net of the lags 0..L of every other field with a reported relation with either (ridge, GCV), the residual
    follower tested against the leader by `_cross`. A reported relation with nothing to condition on is its own partial.
    Sets ``partial``, ``p_partial`` and ``direct`` on each row."""
    from . import control

    a = _standardise(a)
    F, m, T = a.shape
    found: dict[int, set[int]] = {}
    for r in rows:
        found.setdefault(r["_f"], set()).add(r["_g"])
        found.setdefault(r["_g"], set()).add(r["_f"])
    tested = []
    for r in rows:
        f, g, ell = r["_f"], r["_g"], r["lag"]
        others = sorted((found[f] | found[g]) - {f, g})
        if not others:
            r["partial"], r["p_partial"], r["direct"] = r["rho"], r["p"], True
            continue
        Z = np.stack([a[h, :, lags - lam:T - lam].ravel() for h in others for lam in range(lags + 1)], axis=1)
        rf, rg = _ridge_residual(np.stack([a[f, :, lags:].ravel(), a[g, :, lags - ell:T - ell].ravel()], 1), Z).T
        follow = np.zeros((1, m, T))
        follow[0, :, lags:] = rf.reshape(m, T - lags)
        S, V, DF, _ = _cross(follow, a[g][None], [ell], lags)
        p, z = _tail_p(S[0, 0, 0], V[0, 0], DF[0, 0])
        r["partial"] = float(rf @ rg / max(np.linalg.norm(rf) * np.linalg.norm(rg), 1e-300))
        r["p_partial"], r["_zc"] = float(p), float(z)
        tested.append(r)
    if tested:
        keep = control.bh(np.array([r["p_partial"] for r in tested]), q)
        for r, k in zip(tested, keep, strict=True):
            r["direct"] = bool(k) and np.sign(r["_zc"]) == np.sign(r["rho"])


def relation_estimate(d: Departures, spectrum, lags: int = 2, q: float = 0.05, courses: bool = True,
                      conditional: bool = True, ledger=None, log=None, edges: tuple[float, ...] = BAND_EDGES) -> dict:
    """The relation estimator over the innovations ``d`` (module docstring): every pair of distinct fields at every lag
    0..``lags`` (one of the two leading) in each graph band of the place graph ``spectrum`` and, with ``courses``,
    the macro-regional and national courses; the shift-null p of each (`_cross`); one BH at q over all of it; and,
    with ``conditional``, the partial and direct read of the reported ones. Returns ``rows`` (``support``, ``field`` the
    follower, ``leader``, ``lag``, ``rho``, ``z``, ``p``, ``reported``, and ``partial``, ``direct`` where reported),
    ``profiles`` (per ordered pair and support, the cumulative association over lags 1..L with its own BH at q: the lag
    profile as one test, ``peak`` its largest lag), ``unanswered`` (the bands too small to read) and ``fields``. Each support's family is written to ``ledger`` (a fresh
    `control.Ledger` when None) before it is computed, and completed with its result (§9.2)."""
    from . import control

    ledger = ledger if ledger is not None else control.Ledger()
    T = len(d.periods)
    if lags >= T:
        raise ValueError(f"{lags} lags leave no period of {T}")
    unanswered: list[str] = []

    def note(msg: str) -> None:
        unanswered.append(msg)
        if log:
            log(msg)

    supports = _bands(d, spectrum, edges, note)
    if courses:
        supports.update(_courses(d))
    fields_spec = sorted(d.fields)
    rows, profiles, arrays = [], [], {}
    for label, a in supports.items():
        tid = ledger.register(control.Hypothesis(f"relation|{label}", "scan", {
            "model": "lagged cross-covariance of N1 innovations, leader circular-shift null", "fields": fields_spec,
            "lags": lags}))
        mine, prof = _support_rows(label, a, d.fields, lags)
        rows += mine
        profiles += prof
        arrays[label] = (a, tid)
        if log:
            log(f"support {label}: {a.shape[1]} coefficients, {len(mine)} pair-lags")
    if rows:
        keep = control.bh(np.array([r["p"] for r in rows]), q)
        for r, k in zip(rows, keep, strict=True):
            r["reported"] = bool(k)
    if profiles:
        keep = control.bh(np.array([r["p"] for r in profiles]), q)
        for r, k in zip(profiles, keep, strict=True):
            r["reported"] = bool(k)
    for label, (a, tid) in arrays.items():
        mine = [r for r in rows if r["support"] == label]
        ledger.complete(tid, float(min((r["p"] for r in mine), default=1.0)), None,
                        {"pairs": len(mine), "reported": sum(r["reported"] for r in mine)})
        if conditional and any(r["reported"] for r in mine):
            _direct(a, [r for r in mine if r["reported"]], lags, q)
    for r in rows:
        r.pop("_f"), r.pop("_g"), r.pop("_zc", None)
    return {"rows": rows, "profiles": profiles, "unanswered": unanswered, "fields": d.fields}


def restrict(d: Departures, periods: tuple[int, int] | None = None, macro: list[int] | None = None) -> Departures:
    """The innovations of the periods labelled ``periods`` (first, last: inclusive) and the places of the macro-regions
    ``macro`` (the IBGE code's first digit): a relation asked of a window and a part of the country. The innovations
    were whitened over the whole fitted series, so cutting them afterwards keeps their null."""
    ti = np.ones(len(d.periods), dtype=bool) if periods is None else (d.periods >= periods[0]) & (d.periods <= periods[1])
    ui = np.ones(len(d.places), dtype=bool) if macro is None else np.isin(np.asarray(d.places).astype(np.int64) // 100000,
                                                                          macro)
    if not ti.any() or not ui.any():
        raise ValueError(f"no cell in periods {periods}, macro-regions {macro}")
    return Departures(d.fields, d.places[ui], d.periods[ti], d.r[:, ui][:, :, ti], d.v[:, ui][:, :, ti],
                      None if d.w is None else d.w[:, ui])


def relation_map(surprises: list, spectrum, lags: int = 2, q: float = 0.05, courses: bool = True,
                 conditional: bool = True, ledger=None, log=None, contexts: list[Departures] | None = None,
                 periods: tuple[int, int] | None = None, macro: list[int] | None = None) -> dict:
    """Stage D over a set of fields (ARCHITECTURE §7.5): their N1 innovations (`innovations`), with any time-varying
    ``contexts`` (`context_innovations`) entered beside them, read by `relation_estimate`. ``periods`` and ``macro``
    cut the innovations (`restrict`) to a window and to macro-regions; ``spectrum`` is then the cut places' graph, and
    the "national" support is the cut places' course."""
    d = innovations(surprises)
    for c in contexts or ():
        # a context's innovations on the fields' lattice; a place or period it lacks is no information, never a zero
        # departure
        ui, ti = np.searchsorted(c.places, d.places), np.searchsorted(c.periods, d.periods)
        hu = (ui < len(c.places)) & (c.places[np.minimum(ui, len(c.places) - 1)] == d.places)
        ht = (ti < len(c.periods)) & (c.periods[np.minimum(ti, len(c.periods) - 1)] == d.periods)
        r = np.zeros((1, len(d.places), len(d.periods)))
        v = np.full_like(r, np.inf)
        w = np.zeros((1, len(d.places)))
        sub = np.ix_(np.nonzero(hu)[0], np.nonzero(ht)[0])
        r[0][sub] = c.r[0][np.ix_(ui[hu], ti[ht])]
        v[0][sub] = c.v[0][np.ix_(ui[hu], ti[ht])]
        w[0][hu] = c.w[0][ui[hu]]
        d = Departures(d.fields + c.fields, d.places, d.periods, np.concatenate([d.r, r]), np.concatenate([d.v, v]),
                       np.concatenate([d.w, w]))
    if periods is not None or macro is not None:
        d = restrict(d, periods, macro)
    return relation_estimate(d, spectrum, lags=lags, q=q, courses=courses, conditional=conditional, ledger=ledger,
                             log=log)
