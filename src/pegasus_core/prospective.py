"""The prospective tier's predictive (ARCHITECTURE §6.1): what BP adds to the fitted effects.

BP carries a fit on the years up to t₀ over the later years. Its expectation was the fit's effects with the
history h extrapolated; its dispersion the block's φ. Measured on rolling origins (evaluation 2026-10-05, BP
level) that is miscentred in three ways, and each has a piece here:

* **The place-year component.** B1 needs φ_extra to calibrate in-sample, and BP, which predicts what the fit has
  not seen, needs it too. It is estimated on the *training* fit's cells (`insample_extra`), so no departure the
  tier is meant to show leaks into it.
* **The place's own course** (annual grain). Places drift apart; the fit's place effects are constant. Each
  place's B2 trend over the fit is carried forward damped (`course`), with the coefficients' posterior variance.
* **The regime of the history** (monthly grain). An epidemic series has no level to extrapolate; the predictive
  is a mixture over the fit's own years (`monolith.extrapolate_members`), each year's h a member.

The predictive of a cell is then a mixture of NBs, one per member (`mixture_pit`)."""

from __future__ import annotations

import numpy as np
from scipy import special, stats

from . import laplace, monolith

DAMPING = 0.5          # the place trend carried forward at this fraction (evaluation 2026-10-05, BP level)


def insample_extra(model: monolith.Monolith, leaves: np.ndarray, levels: list[np.ndarray],
                   exposure: np.ndarray | None = None) -> np.ndarray:
    """The field's φ_extra per place (shape [places, 1]) on the training fit's own B1 cells (macro-region and
    state hierarchy, `surprise.place_year_phi`)."""
    from . import surprise  # surprise imports this module

    mu, mu2 = model.expected(leaves, spatial=True)
    y = model.observed(leaves)
    cells = laplace.predictive_phi(mu, np.zeros_like(mu) if exposure is None else exposure, mu2, model.phi)
    return np.asarray(surprise.place_year_phi(y, mu, cells, *levels))[:, None]


def course(model: monolith.Monolith, leaves: np.ndarray, n_test: int, damping: float = DAMPING,
           exposure: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Each place's own course carried over ``n_test`` later periods: the shift (log scale) and its variance,
    both [places, n_test]. The B2 refit on the training fit's B1 cells (log μ' = log μ + α_u + β_u s_t, shrunk to
    the region's), the slope carried forward damped by ``damping`` and the coefficients' posterior variance
    X H⁻¹ Xᵀ added."""
    from . import surprise

    mu, mu2 = model.expected(leaves, spatial=True)
    y = model.observed(leaves)
    n = y.shape[1]
    sd = max(float(np.arange(n).std()), 1e-9)
    s = (np.arange(n) - (n - 1) / 2) / sd
    s_new = (np.arange(n, n + n_test) - (n - 1) / 2) / sd
    phi_agg = surprise.aggregate_phi(mu, mu2, model.phi)
    _, b, _, _, _, _, var = surprise.refit_place(y, mu, phi_agg, np.stack([np.ones(n), s], axis=1), variance=True,
                                                 X_new=np.stack([np.ones(n_test), s_new], axis=1))
    return b[:, [0]] + damping * b[:, [1]] * s_new[None, :], var


def mixture_pit(y: np.ndarray, comps: list[tuple[float, np.ndarray, np.ndarray]], seed: int
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The randomised PIT of a mixture of NBs, ``comps`` = [(weight, μ, φ_agg)], with the surprise z and the
    mixture's matched dispersion (the NB with its mean and variance, for the information weight)."""
    v = np.random.default_rng(seed).random(y.shape)
    low, pm, upp = np.zeros(y.shape), np.zeros(y.shape), np.zeros(y.shape)
    mean, second = np.zeros(y.shape), np.zeros(y.shape)
    for w, mu, a in comps:
        inf = ~np.isfinite(a)
        d = stats.nbinom(np.where(inf, 1.0, a), np.where(inf, 0.5, a / (a + np.maximum(mu, 1e-300))))
        dp = stats.poisson(mu)
        cdf = np.where(inf, dp.cdf(y - 1), d.cdf(y - 1))
        pmf = np.where(inf, dp.pmf(y), d.pmf(y))
        low += w * cdf
        upp += w * np.where(inf, dp.sf(y), d.sf(y))
        pm += w * pmf
        mean += w * mu
        second += w * (mu ** 2 * (1 + np.where(inf, 0.0, 1.0 / np.where(inf, 1.0, a))) + mu)
    lower = np.clip(low + v * pm, 1e-300, 1.0)
    upper = np.clip(upp + (1 - v) * pm, 1e-300, 1.0)
    z = np.where(lower < 0.5, special.ndtri(lower), -special.ndtri(upper))
    var = np.maximum(second - mean ** 2, 0.0)
    over = np.divide(var - mean, mean ** 2, out=np.zeros(y.shape), where=mean > 0)
    phi = np.divide(1.0, over, out=np.full(y.shape, np.inf), where=over > 1e-12)
    return np.clip(lower, 0.0, 1.0), z, phi
