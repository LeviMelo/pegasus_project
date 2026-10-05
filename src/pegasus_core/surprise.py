"""Expectation tiers, calibration and surprise (ARCHITECTURE §6).

For a field (a node of a block's tree) and a tier, every cell (place, year)
gets its observed count y, its expectation μ, the aggregate dispersion
φ_agg = φ·μ²/Σμ² (a sum of independent NB cells with a common φ), the
randomised PIT u, the surprise z = Φ⁻¹(u) and the information weight
w = μ/(1+μ/φ_agg). Nothing is averaged over z: subset statistics use Σy, Σμ.

The cube is virtual: `Expectations.surprise` computes it from the fitted
parameters on demand and caches it only when asked (scanned fields).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pyarrow as pa
import torch
from scipy import optimize, special, stats

from . import config, fields, gateway, laplace, monolith, store

TIERS = ("B0", "B1", "B2", "B2s", "BP")
SPATIAL = {"B0": False, "B1": True, "B2": True, "B2s": True, "BP": True}

# flags, a bitmask per cell
DENOMINATOR = 1      # events where the population is zero (denominator tension)
CALIBRATION = 2      # the field failed calibration at this tier even with its own φ
RECORDING = 4        # pegasus_data marks the recording unreliable (not yet served)
NO_INFORMATION = 8   # μ ≈ 0: the cell carries no information

# a field is calibrated when its PIT's KS distance is below these, whatever the p-value
# (with 10⁵ cells any departure is "significant"; P5: test against a relevant effect). A
# macro-region holds ~5,000–25,000 cells, whose sampling KS alone reaches ~0.02.
KS_TOLERANCE = 0.03
KS_REGION_TOLERANCE = 0.05


@dataclass
class Surprise:
    field: fields.Field
    tier: str
    places: np.ndarray
    years: np.ndarray        # the time axis: years, or YYYYMM period codes at the monthly grain
    y: np.ndarray            # [U, T]
    mu: np.ndarray           # [U, T]
    phi: np.ndarray          # [U, T] aggregate dispersion (inf: Poisson)
    u: np.ndarray            # [U, T] randomised PIT
    z: np.ndarray            # [U, T]
    w: np.ndarray            # [U, T]
    flags: np.ndarray        # [U, T] int8
    calibration: dict = field(default_factory=dict)
    extras: dict = field(default_factory=dict)   # B2: alpha, beta and their posterior sd per place

    def table(self) -> pa.Table:
        U, T = self.y.shape
        return pa.table({"u": np.repeat(self.places, T).astype(np.int32),
                         "year": np.tile(self.years, U).astype(np.int32),
                         "y": self.y.ravel(), "mu": self.mu.ravel(), "phi": self.phi.ravel(),
                         "pit": self.u.ravel(), "z": self.z.ravel(), "w": self.w.ravel(),
                         "flags": self.flags.ravel().astype(np.int8)})


class Expectations:
    """The fitted monolith of one event type, read field by field and tier by tier."""

    def __init__(self, dataset: str, event: str, years: range | list[int], graph: str = "contiguity",
                 structure: str = "ICD10", source: dict | None = None, laplace: int = 0, device: str = "cpu",
                 center: str = "plugin", forecast: bool = True):
        """``source`` names a non-default reader (``monolith.assemble``): code-list counts
        ({"source": "code_list", "column": "CODANOMAL"}) or a mark ({"source": "mark",
        "mark": "PESO", "bounds": (200, 7000)}). ``laplace`` is the number of posterior draws (0: the
        MAP's predictive, NB(mu, phi)); with draws, a cell's predictive integrates mu over the Laplace
        posterior (ARCHITECTURE 5.3, `laplace.py`), centred on the MAP's expectation (``center="plugin"``) or
        on the posterior mean (``"posterior"``)."""
        self.dataset, self.event, self.years, self.graph = dataset, event, list(years), graph
        self.source = dict(source or {})
        self.laplace, self.device, self.forecast, self.center = int(laplace), device, forecast, center
        self._posteriors: dict = {}
        classifier = self.source.get("column") or self.source.get("classifier")
        self.registry = fields.Registry(dataset, event, structure, classifier=classifier)
        self._models: dict[str, monolith.Monolith] = {}
        self._macro: np.ndarray | None = None

    def model(self, block: str) -> monolith.Monolith:
        if block not in self._models:
            cls = monolith.MarkModel if self.source.get("source") == "mark" else monolith.Monolith
            self._models[block] = cls.load(self.dataset, self.event, block, self.years, self.graph,
                                           device=self.device, **self.source)
        return self._models[block]

    def posterior(self, key, model: monolith.Monolith) -> laplace.Posterior:
        """The Laplace posterior of a fitted block, drawn once per Expectations (``key`` names the fit)."""
        if key not in self._posteriors:
            self._posteriors[key] = laplace.Posterior(model)
            self._posteriors[key].sample(self.laplace)
        return self._posteriors[key]

    def field(self, node: str) -> fields.Field:
        return self.registry.field(node)

    def prospective(self, node: str | fields.Field, train_last: int, history: str = "auto") -> Surprise:
        """Tier BP: the years after ``train_last`` against a fit on the years up to it, the history
        extrapolated (`monolith.extrapolate`). Surveillance needs it: a fit over the whole period
        learns an epidemic as normal (COVID-19 in SIM: B34 deaths 2020 observed 213,152 against
        212,821 expected at B1, evaluation 2026-10-04). Calibration is recorded, never flagged:
        departing from the past is what this tier exists to show."""
        f = node if isinstance(node, fields.Field) else self.field(node)
        train = [y for y in self.years if y <= train_last]
        test = [y for y in self.years if y > train_last]
        cls = monolith.MarkModel if self.source.get("source") == "mark" else monolith.Monolith
        if cls is monolith.MarkModel:
            raise NotImplementedError("the prospective tier is for counts")
        model = cls.load(self.dataset, self.event, f.block, train, self.graph, device=self.device, **self.source)
        tm, x = monolith.extrapolate(model, monolith.assemble(self.dataset, self.event, f.block, test, **self.source),
                                     history)
        leaves = np.array([tm.data.leaves.index(c) for c in self.registry.leaves(f.node) if c in tm.data.leaves])
        mu, mu2 = tm.expected(leaves, spatial=True, x=x)
        var = None
        if self.laplace:
            post = self.posterior(("BP", f.block, train_last), model)
            fv = laplace.forecast_variance(model, tm) if self.forecast else None
            gen = torch.Generator(device=model.device)
            gen.manual_seed(config.seed("laplace", "forecast", model.key()))
            mom = post.moments(leaves, True, x_fn=lambda xd: (tm, monolith.extrapolate_effects(
                model, tm, xd, history,
                increments=None if fv is None else laplace.forecast_increments(model, tm, fv, gen))))
            mu, mu2, var = _recentre(mom, mu, self.center)
        y = tm.observed(leaves)
        out = _assemble(f, "BP", tm, y, mu, mu2, model.phi, self.macroregions(tm.data.places), flag_calibration=False,
                        var=var)
        out.extras = {"train": [int(train[0]), int(train[-1])]}
        return out

    def place_effects(self, node: str | fields.Field) -> tuple[np.ndarray, np.ndarray]:
        """E_b's input: the field's own place intercept over B0 (shrunk), with its posterior sd."""
        s = self.surprise(node, "B0")
        if s.extras.get("kind") == "mark":
            b, sd, _ = ridge_place(s.y - s.mu, s.w, np.ones((s.y.shape[1], 1)))
            return b[:, 0], sd[:, 0]
        _, b, sd, _ = refit_place(s.y, s.mu, s.phi, np.ones((s.y.shape[1], 1)))
        return b[:, 0], sd[:, 0]

    def macroregions(self, places: np.ndarray) -> np.ndarray:
        if self._macro is None:
            self._macro = gateway.regions(places, "ibge_macroregion")
        return self._macro

    def surprise(self, node: str | fields.Field, tier: str = "B1", cache: bool = False) -> Surprise:
        f = node if isinstance(node, fields.Field) else self.field(node)
        if tier not in TIERS:
            raise KeyError(tier)
        m = self.model(f.block)
        if tier == "B2s" and m.data.grain != "month":
            raise NotImplementedError("B2s needs a sub-annual grain; this block is annual")
        key = {**m.key(), "field": f.id, "tier": tier, "surprise": 1}
        if cache:
            hit = store.get_table("surprise", key)
            if hit is not None:
                return _from_table(f, tier, hit, store.manifest("surprise", key))
        leaves = np.array([m.data.leaves.index(c) for c in self.registry.leaves(f.node) if c in m.data.leaves])
        if len(leaves) == 0:
            raise LookupError(f"{f.id}: no leaf of the node is in block {f.block}")
        if isinstance(m, monolith.MarkModel):
            out = _mark_surprise(f, tier, m, leaves, self.macroregions(m.data.places))
            if cache:
                store.put_table("surprise", key, out.table(), {"calibration": out.calibration})
            return out
        mu, mu2 = m.expected(leaves, spatial=SPATIAL[tier])
        if tier == "B0":
            # dropping centred log-scale place effects drops E[exp(s + v)] > 1 too: re-level B0 to
            # the national total of each year, so B0 says how a place differs from Brazil
            ref, _ = m.expected(leaves, spatial=True)
            c = ref.sum(0) / np.maximum(mu.sum(0), 1e-300)
            mu, mu2 = mu * c, mu2 * c ** 2
        y = m.observed(leaves)
        extras: dict = {}
        mom = None
        if self.laplace:
            mom = self.posterior(f.block, m).moments(leaves, SPATIAL[tier], relevel=(tier == "B0"))
        mu_point = mu
        if tier == "B2":
            axis = m.data.years if m.data.grain == "year" else np.arange(y.shape[1], dtype=float)
            mu, extras = refit_place_trend(y, mu, mu2, m.phi, axis)
        elif tier == "B2s":
            mu, extras = refit_place_season(y, mu, mu2, m.phi, m.data.month_of_year)
        if tier in ("B2", "B2s"):
            # the refit moved each cell's mean by r = mu / mu_point; the sum of squared cell means moves by r^2
            # (a B1 sum under a refit mean made the aggregate dispersion phi mu^2 / sum(mu^2) meaningless)
            mu2 = mu2 * np.divide(mu, mu_point, out=np.ones_like(mu), where=mu_point > 0) ** 2
        var = None
        eta_var = extras.pop("eta_var", None)
        if mom is not None:
            mu, mu2, var = _predictive(mom, mu, mu_point, eta_var, self.center)
        out = _assemble(f, tier, m, y, mu, mu2, m.phi, self.macroregions(m.data.places), var=var)
        out.extras = extras
        if cache:
            store.put_table("surprise", key, out.table(), {"calibration": out.calibration,
                                                            **{k: v.tolist() for k, v in extras.items()}})
        return out


def _recentre(mom: dict, mu_point: np.ndarray, center: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(mean, sum mu^2, Var mu) of the draws, centred on the plug-in (the MAP's expectation, which
    the fit's score equations tie to the observed totals) or left on the posterior mean (which sits
    exp(Var(eta)/2) above it, and over-shoots the totals of the cells the fit has seen)."""
    mean, var, mu2 = mom["mean"], mom["var"], mom["mu2"]
    if center == "posterior":
        return mean, mu2, var
    s = np.divide(mu_point, mean, out=np.ones_like(mean), where=mean > 0)
    return mu_point, mu2 * s ** 2, var * s ** 2


def _predictive(mom: dict, mu_tier: np.ndarray, mu_point: np.ndarray, eta_var: np.ndarray | None,
                center: str = "plugin") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The posterior-predictive mean, sum of mu^2 and Var(mu) of a tier from the draws' moments of the
    B1/B0 expectation. B2 and B2s refit each place's course around the B1 expectation: the refit scales
    the draws by r = mu_tier/mu_point and adds the place coefficients' own posterior variance
    ``eta_var`` (independent of the draws: an approximation, additive on the log scale)."""
    mean, mu2, var = _recentre(mom, mu_point, center)
    if eta_var is None:
        return mean, mu2, var
    r = np.divide(mu_tier, mu_point, out=np.ones_like(mu_tier), where=mu_point > 0)
    cv2 = var / np.maximum(mean, 1e-300) ** 2
    mean = r * mean * (np.exp(eta_var / 2) if center == "posterior" else 1.0)
    cv2_total = (1 + cv2) * np.exp(eta_var) - 1
    return mean, r ** 2 * mu2, cv2_total * mean ** 2


def _assemble(f: fields.Field, tier: str, m: monolith.Monolith, y: np.ndarray, mu: np.ndarray, mu2: np.ndarray,
              phi_block: float, macro: np.ndarray, flag_calibration: bool = True,
              var: np.ndarray | None = None) -> Surprise:
    """PIT and calibration with the block's phi; if miscalibrated, with the field's own phi; if
    still miscalibrated, flagged (ARCHITECTURE 6.2). ``var`` is Var(mu) over the Laplace posterior
    (None: the MAP's predictive)."""
    pop = m.data.N.sum(axis=2)
    seed = config.seed(f.id, tier, "pit", m.key())
    cells = laplace.predictive_phi(mu, np.zeros_like(mu) if var is None else var, mu2, phi_block)
    extra = place_year_phi(y, mu, cells)
    attempts = [("block", phi_block, cells), ("field", extra, 1.0 / (1.0 / cells + 1.0 / extra))]
    for source, phi, phi_agg in attempts:
        u, z = randomised_pit(y, mu, phi_agg, seed)
        cal = calibration(u, mu, macro)
        cal["phi_source"], cal["phi"] = source, phi
        if cal["calibrated"]:
            break
    flags = np.zeros(y.shape, dtype=np.int8)
    flags[(pop <= 0) & (y > 0)] |= DENOMINATOR
    flags[mu < 1e-6] |= NO_INFORMATION
    if flag_calibration and not cal["calibrated"]:
        flags |= CALIBRATION
    if not flag_calibration:
        # prospective: the block's φ only; the field's place-year component would be estimated
        # from the very departures the tier is meant to show
        phi_agg = cells
        u, z = randomised_pit(y, mu, phi_agg, seed)
    w = np.where(np.isinf(phi_agg), mu, mu / (1 + mu / phi_agg))
    return Surprise(f, tier, m.data.places, m.data.periods(), y, mu, phi_agg, u, z, w, flags, cal)


def _mark_surprise(f: fields.Field, tier: str, m: monolith.MarkModel, leaves: np.ndarray,
                   macro: np.ndarray) -> Surprise:
    """A mark field's cells (u, t): y the observed mean log mark, μ its expectation, z Gaussian
    with the variance of a mean of n events; w = 1/variance. Cells without events carry nothing."""
    mu, var = m.expected(leaves, spatial=SPATIAL[tier])
    y = m.observed(leaves)
    n = m.events(leaves)
    has = n > 0
    if tier == "B0":
        # additive re-levelling on the log scale: B0 matches B1's n-weighted national mean per year
        ref, _ = m.expected(leaves, spatial=True)
        shift = (np.nansum(n * ref, 0) - np.nansum(n * mu, 0)) / np.maximum(n.sum(0), 1e-300)
        mu = mu + shift[None, :]
    extras: dict = {"kind": "mark", "events": n}
    w = np.where(has, 1.0 / np.where(has, var, 1.0), 0.0)
    if tier == "B2":
        s = (m.data.years - m.data.years.mean()) / max(m.data.years.std(), 1e-9)
        X = np.stack([np.ones_like(s), s], axis=1)
        b, sd, tau = ridge_place(np.where(has, y - mu, 0.0), w, X)
        mu = mu + b @ X.T
        extras.update({"alpha": b[:, 0], "beta": b[:, 1], "alpha_sd": sd[:, 0], "beta_sd": sd[:, 1], "tau": tau})
    extra_var = 0.0
    for source in ("model", "field"):
        sdv = np.sqrt(np.where(has, var + extra_var, 1.0))
        z = np.where(has, (np.where(has, y, 0.0) - np.where(has, mu, 0.0)) / sdv, 0.0)
        u = special.ndtr(z)
        cal = calibration(np.where(has, u, 0.5), np.where(has, 1.0, 0.0), macro)
        cal["variance_source"], cal["extra_variance"] = source, extra_var
        if cal["calibrated"]:
            break
        # a place-year component by moments over the informative cells
        r2 = (y - mu)[has] ** 2 - var[has]
        extra_var = float(max(np.mean(r2), 0.0))
    flags = np.where(has, 0, NO_INFORMATION).astype(np.int8)
    if not cal["calibrated"]:
        flags |= CALIBRATION
    w = np.where(has, 1.0 / np.where(has, var + extra_var, 1.0), 0.0)
    return Surprise(f, tier, m.data.places, m.data.years, np.where(has, y, np.nan), np.where(has, mu, np.nan),
                    np.full(y.shape, np.nan), u, z, w, flags, cal, extras)


def ridge_place(r: np.ndarray, w: np.ndarray, X: np.ndarray, outer: int = 30
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per place, a Gaussian ridge of residuals r_ut on X_t with weights w_ut and b_u ~ N(0, 1/τ):
    exact per place, the τ's by Fellner–Schall. Returns (b, posterior sd, τ)."""
    k = X.shape[1]
    tau = np.ones(k)
    live = w.sum(1) > 0
    for _ in range(outer):
        H = np.einsum("ut,ti,tj->uij", w, X, X) + np.diag(tau)
        g = (w * r) @ X
        b = np.linalg.solve(H, g[..., None])[..., 0]
        b[~live] = 0
        Hinv = np.linalg.inv(H)
        tr = np.einsum("uii->ui", Hinv[live]).sum(0)
        quad = (b[live] ** 2).sum(0)
        new = np.clip((live.sum() - tau * tr) / np.maximum(quad, 1e-12), 1e-4, 1e8)
        done = np.abs(np.log(new / tau)).max() < 0.01
        tau = new
        if done:
            break
    H = np.einsum("ut,ti,tj->uij", w, X, X) + np.diag(tau)
    b = np.linalg.solve(H, ((w * r) @ X)[..., None])[..., 0]
    b[~live] = 0
    sd = np.sqrt(np.clip(np.einsum("uii->ui", np.linalg.inv(H)), 0, None))
    return b, sd, tau


def aggregate_phi(mu: np.ndarray, mu2: np.ndarray, phi: float) -> np.ndarray:
    """φ of a sum of NB(μ_i, φ) cells: Var = Σμ + Σμ²/φ = μ + μ²/φ_agg."""
    if not np.isfinite(phi):
        return np.full(mu.shape, np.inf)
    return np.divide(phi * mu ** 2, mu2, out=np.full(mu.shape, np.inf), where=mu2 > 0)


def place_year_phi(y: np.ndarray, mu: np.ndarray, phi_cells: np.ndarray) -> float:
    """The field's place-year variance component, by maximum likelihood on its aggregate cells:
    Var(Y) = μ + μ²/φ_cells + μ²/φ_extra, i.e. NB with 1/φ = 1/φ_cells + 1/φ_extra. Cells
    within a place-year share variation the expectation does not model; summing them adds it
    coherently, which the independent-cell φ_cells misses (a U-shaped PIT, chapter IX B1)."""
    ok = mu > 1e-9
    yy, mm, pc = y[ok], mu[ok], phi_cells[ok]
    inv_c = np.where(np.isfinite(pc), 1.0 / pc, 0.0)

    def nll(log_extra: float) -> float:
        phi = 1.0 / (inv_c + np.exp(-log_extra))
        return -float(np.sum(special.gammaln(yy + phi) - special.gammaln(phi) + phi * np.log(phi / (phi + mm))
                             + yy * np.log(mm / (phi + mm))))

    res = optimize.minimize_scalar(nll, bounds=(np.log(1e-2), np.log(1e7)), method="bounded")
    return float("inf") if res.x > np.log(0.99e7) else float(np.exp(res.x))


def randomised_pit(y: np.ndarray, mu: np.ndarray, phi_agg: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """u = F(y−1) + V·p(y), V ~ U(0,1); z = Φ⁻¹(u) computed from the nearer tail, so
    surprises far in either tail keep their precision."""
    V = np.random.default_rng(seed).random(y.shape)
    pois = ~np.isfinite(phi_agg)
    lower = np.empty(y.shape)
    upper = np.empty(y.shape)
    if pois.any():
        d = stats.poisson(mu[pois])
        pm = d.pmf(y[pois])
        lower[pois] = d.cdf(y[pois] - 1) + V[pois] * pm
        upper[pois] = d.sf(y[pois]) + (1 - V[pois]) * pm
    nb = ~pois
    if nb.any():
        n = phi_agg[nb]
        d = stats.nbinom(n, n / (n + np.maximum(mu[nb], 1e-300)))
        pm = d.pmf(y[nb])
        lower[nb] = d.cdf(y[nb] - 1) + V[nb] * pm
        upper[nb] = d.sf(y[nb]) + (1 - V[nb]) * pm
    lower = np.clip(lower, 1e-300, 1.0)
    upper = np.clip(upper, 1e-300, 1.0)
    z = np.where(lower < 0.5, special.ndtri(lower), -special.ndtri(upper))
    return np.clip(lower, 0.0, 1.0), z


def calibration(u: np.ndarray, mu: np.ndarray, macro: np.ndarray) -> dict:
    """Uniformity of the PIT: KS overall and per macro-region, and the 10-bin histogram."""
    informative = mu > 1e-6
    flat = u[informative]
    ks = stats.kstest(flat, "uniform")
    hist = np.histogram(flat, bins=10, range=(0, 1))[0]
    by_region = {}
    for r in np.unique(macro):
        sel = (macro[:, None] == r) & informative
        if sel.sum() >= 50:
            by_region[str(r)] = float(stats.kstest(u[sel], "uniform").statistic)
    worst = max(by_region.values(), default=0.0)
    return {"ks": float(ks.statistic), "ks_p": float(ks.pvalue), "histogram": (hist / hist.sum()).round(4).tolist(),
            "ks_by_macroregion": by_region, "cells": int(informative.sum()),
            "calibrated": bool(ks.statistic <= KS_TOLERANCE and worst <= KS_REGION_TOLERANCE)}


def refit_place_trend(y: np.ndarray, mu: np.ndarray, mu2: np.ndarray, phi: float, years: np.ndarray
                      ) -> tuple[np.ndarray, dict]:
    """B2: per place, log μ' = log μ + α_u + β_u·s_t (s standardised years), the B1
    expectation as offset, so a place's course shrinks to its region's."""
    s = (years - years.mean()) / max(years.std(), 1e-9)
    mu_new, b, sd, tau, ev = refit_place(y, mu, aggregate_phi(mu, mu2, phi), np.stack([np.ones_like(s), s], axis=1),
                                         variance=True)
    return mu_new, {"alpha": b[:, 0], "beta": b[:, 1], "alpha_sd": sd[:, 0], "beta_sd": sd[:, 1], "tau": tau,
                    "eta_var": ev}


def refit_place_season(y: np.ndarray, mu: np.ndarray, mu2: np.ndarray, phi: float, month_of_year: np.ndarray
                       ) -> tuple[np.ndarray, dict]:
    """B2s: B2 at monthly grain plus each place's own annual harmonic (sin, cos of the month), so a
    place's seasonal amplitude and phase depart from its group's season by a shrunk amount."""
    T = len(month_of_year)
    s = (np.arange(T) - (T - 1) / 2) / max(np.arange(T).std(), 1e-9)
    angle = 2 * np.pi * month_of_year / 12
    X = np.stack([np.ones(T), s, np.sin(angle), np.cos(angle)], axis=1)
    mu_new, b, sd, tau, ev = refit_place(y, mu, aggregate_phi(mu, mu2, phi), X, variance=True)
    return mu_new, {"alpha": b[:, 0], "beta": b[:, 1], "alpha_sd": sd[:, 0], "beta_sd": sd[:, 1],
                    "season_sin": b[:, 2], "season_cos": b[:, 3], "tau": tau, "eta_var": ev}


def place_intercepts(y: np.ndarray, mu: np.ndarray, mu2: np.ndarray, phi: float) -> tuple[np.ndarray, np.ndarray]:
    """A field's own place effect over an expectation (B0 for E_b): α_u ~ N(0, 1/τ), shrunk."""
    _, b, sd, _ = refit_place(y, mu, aggregate_phi(mu, mu2, phi), np.ones((y.shape[1], 1)))
    return b[:, 0], sd[:, 0]


def refit_place(y: np.ndarray, mu: np.ndarray, phi_agg: np.ndarray, X: np.ndarray, iterations: int = 30,
                outer: int = 20, tau: np.ndarray | None = None, variance: bool = False) -> tuple:
    """Per place u, log μ'_ut = log μ_ut + X_t·b_u with b_u ~ N(0, diag(1/τ)): exact p×p Newton per
    place under NB working weights, the τ's by Fellner–Schall. Returns (μ', b, posterior sd, τ)."""
    live = mu.sum(axis=1) > 0
    U, k = mu.shape[0], X.shape[1]
    pois = np.isinf(phi_agg)
    b = np.zeros((U, k))
    fixed = tau is not None
    tau = np.asarray(tau, dtype=float) if fixed else np.ones(k)
    H = np.broadcast_to(np.eye(k), (U, k, k)).copy()
    for _ in range(1 if fixed else outer):
        for _ in range(iterations):
            m = mu * np.exp(b @ X.T)
            wgt = np.where(pois, m, m / (1 + m / np.where(pois, 1.0, phi_agg)))
            resid = np.where(pois, y - m, (y - m) / (1 + m / np.where(pois, 1.0, phi_agg)))
            grad = resid @ X - tau * b
            H = np.einsum("ut,ti,tj->uij", wgt, X, X) + np.diag(tau)
            step = np.linalg.solve(H, grad[..., None])[..., 0]
            step[~live] = 0
            b += np.clip(step, -3, 3)
            if np.abs(step).max() < 1e-6:
                break
        if fixed:
            break
        Hinv = np.linalg.inv(H)
        quad = (b[live] ** 2).sum(axis=0)
        tr = np.einsum("uii->ui", Hinv[live]).sum(axis=0)
        new = np.clip((live.sum() - tau * tr) / np.maximum(quad, 1e-12), 1e-4, 1e8)
        change = np.abs(np.log(new / tau)).max()
        tau = new
        if change < 0.01:
            break
    Hinv = np.linalg.inv(H)
    sd = np.sqrt(np.clip(np.einsum("uii->ui", Hinv), 0, None))
    if variance:   # Var(X_t . b_u): the refit's own contribution to the uncertainty of log mu'
        return mu * np.exp(b @ X.T), b, sd, tau, np.einsum("ti,uij,tj->ut", X, Hinv, X)
    return mu * np.exp(b @ X.T), b, sd, tau


def _from_table(f: fields.Field, tier: str, t: pa.Table, meta: dict | None) -> Surprise:
    places = np.unique(t.column("u").to_numpy())
    years = np.unique(t.column("year").to_numpy())
    shape = (len(places), len(years))
    col = lambda c: t.column(c).to_numpy().reshape(shape)  # noqa: E731
    meta = meta or {}
    extras = {k: np.asarray(meta[k]) for k in ("alpha", "beta", "alpha_sd", "beta_sd", "tau") if k in meta}
    return Surprise(f, tier, places, years, col("y"), col("mu"), col("phi"), col("pit"), col("z"), col("w"),
                    col("flags"), meta.get("calibration", {}), extras)
