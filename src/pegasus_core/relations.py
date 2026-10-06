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
The term inside the monolith's joint fit is the v2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, stats


@dataclass
class LagCurve:
    """A fitted lag–response curve: β(ℓ) per lag with its standard error, the cumulative effect Σβ with its own, the
    lags where the simultaneous 95 % band excludes zero (``band``: its critical |z|), the penalty's strength and the
    deviance explained."""
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
        b = np.zeros(n)
        for _ in range(iterations):
            eta = np.clip(Xv @ b, -20, 20)
            lam = mv * np.exp(eta)
            w = lam / (1.0 + lam / ph)                      # NB information
            g = Xv.T @ ((yv - lam) / (1.0 + lam / ph)) - P @ b
            H = Xv.T @ (Xv * w[:, None]) + P
            step = np.linalg.solve(H, g)
            b = b + step
            if np.abs(step).max() < 1e-9:
                break
        eta = np.clip(Xv @ b, -20, 20)
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
    lam0 = mv
    lam1 = mv * np.exp(np.clip(Xv @ b, -20, 20))

    def dev(lam: np.ndarray) -> float:
        return float(2 * np.sum(np.where(yv > 0, yv * np.log(np.maximum(yv, 1e-300) / lam), 0.0) - (yv - lam)))

    # the window from a simultaneous band (the max |z| over lags under the curve's own covariance; mgcv's simulated
    # band): per-lag 95 % intervals marked a lag in 22 of 100 null worlds, the band in its 5
    corr = cov / np.outer(se, se)
    draws = np.random.default_rng(0).multivariate_normal(np.zeros(n), corr, size=20000, method="cholesky")
    band = float(np.quantile(np.abs(draws).max(1), 0.95))
    window = [int(ell) for ell in range(n) if abs(b[ell]) > band * se[ell]]
    return LagCurve(np.arange(n), b, se, cum, cum_se, float(np.exp(res.x)), window, band, dev(lam0) - dev(lam1),
                    int(sel.sum()))
