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
from scipy import optimize, special, stats

from . import config, facility, fields, gateway, laplace, monolith, prospective, store

TIERS = ("B0", "B1", "B2", "B2s", "BP", "BPA")
SPATIAL = {"B0": False, "B1": True, "B2": True, "B2s": True, "BP": True, "BPA": True}
# The prospective tier has two objects (ADR-0012): the calibrated EXPECTATION (BP; for surprises) and the
# ALARM BASELINE (BPA; for epidemic detection, a flat level that past epidemics do not enter).
PURPOSE_TIER = {"expectation": "BP", "alarm": "BPA"}

# flags, a bitmask per cell
DENOMINATOR = 1      # events where the population is zero (denominator tension)
CALIBRATION = 2      # the field failed calibration at this tier even with its own φ
RECORDING = 4        # pegasus_data marks the recording unreliable (not yet served)
NO_INFORMATION = 8   # μ ≈ 0: the cell carries no information
NEW_CATEGORY = 16    # BP: events of a category the training fit never saw, out of the node (ADR-0011)
NEW_CATEGORY_ALARM = 5   # events in a year at which a category unseen by the fit is reported (ADR-0011)

# a field is calibrated when its PIT's KS distance is below these, whatever the p-value
# (with 10⁵ cells any departure is "significant"; P5: test against a relevant effect). A
# macro-region holds ~5,000–25,000 cells, whose sampling KS alone reaches ~0.02.
KS_TOLERANCE = 0.03
KS_REGION_TOLERANCE = 0.05

# the levels of the place-year dispersion component's hierarchy below its field-wide value
# (ARCHITECTURE §5.2): each level's estimate is shrunk to its parent's, by the between-group
# variance the data themselves show. () is one value per field.
DISPERSION_LEVELS: tuple[str, ...] = ("macro", "state")
MIN_DISPERSION_CELLS = 200


@dataclass(frozen=True)
class Noise:
    """The predictive's noise structure over the periods of a place (stage B, N1; ADR-0029). Each cell is
    NB(μ, φ/κ): a gamma frailty of variance κ/φ times a Poisson, so κ corrects the block's dispersion for this field.
    The frailties of a place's periods are joined by a Gaussian copula whose latent correlation at lag k is ρ^k (an
    AR(1)), so the marginal stays the NB exactly. A place's own slow structure (its level and trend beyond the
    reference tier) is not noise: it is what the trend and step departure models test (`noise_structure`).

    The Surprise's φ already carries κ (`with_noise`); its ``noise`` then keeps κ = 1 and records the estimate in the
    calibration."""
    kappa: float = 1.0
    rho: float = 0.0

    @property
    def null(self) -> bool:
        return self.kappa == 1.0 and self.rho == 0.0

    def frailty_variance(self, phi: np.ndarray) -> np.ndarray:
        """κ/φ per cell (0 where φ is infinite)."""
        phi = np.asarray(phi, dtype=float)
        return self.kappa * np.divide(1.0, phi, out=np.zeros(phi.shape), where=np.isfinite(phi) & (phi > 0))


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
    noise: Noise = None      # N1: the predictive's noise structure over periods (`noise_structure`)

    def __post_init__(self):
        if self.noise is None:
            self.noise = Noise()

    def table(self) -> pa.Table:
        U, T = self.y.shape
        return pa.table({"u": np.repeat(self.places, T).astype(np.int32),
                         "year": np.tile(self.years, U).astype(np.int32),
                         "y": self.y.ravel(), "mu": self.mu.ravel(), "phi": self.phi.ravel(),
                         "pit": self.u.ravel(), "z": self.z.ravel(), "w": self.w.ravel(),
                         "flags": self.flags.ravel().astype(np.int8)})


EXPOSURE_RHO = 0.0   # correlation of log N between the sex-age cells of a place-year (monolith.exposure_variance)


class Expectations:
    """The fitted monolith of one event type, read field by field and tier by tier."""

    def __init__(self, dataset: str, event: str, years: range | list[int], graph: str = "contiguity",
                 structure: str = "ICD10", source: dict | None = None, laplace: int = 0, device: str = "cpu",
                 center: str = "plugin", population: str | None = None,
                 exposure_rho: float | None = EXPOSURE_RHO, supply: bool = False, rank: int = 0):
        """``source`` names a non-default reader (``monolith.assemble``): code-list counts
        ({"source": "code_list", "column": "CODANOMAL"}) or a mark ({"source": "mark",
        "mark": "PESO", "bounds": (200, 7000)}). ``laplace`` is the number of posterior draws (0: the
        MAP's predictive, NB(mu, phi)); with draws, a cell's predictive integrates mu over the Laplace
        posterior (ARCHITECTURE 5.3, `laplace.py`), centred on the MAP's expectation (``center="plugin"``) or
        on the posterior mean (``"posterior"``). ``population`` names the exposure (``gateway.population``:
        popsvs, account-2; None: the configured default). When it carries intervals (the account) the
        predictive's variance adds the exposure's, Var(mu) from log N ~ N(log N^, s^2) with the
        correlation ``exposure_rho`` between a place-year's cells (None: ignored)."""
        self.population, self.exposure_rho = population, exposure_rho
        self.rank = int(rank)       # the low-rank interaction's R of the stored fits (ADR-0021); 0: the base model
        self.supply = supply        # fit the facility-supply term onto each loaded count block (facility.attach_supply, ADR-0016)
        self.supplies: dict = {}
        self.dataset, self.event, self.years, self.graph = dataset, event, list(years), graph
        self.source = dict(source or {})
        self.laplace, self.device, self.center = int(laplace), device, center
        self._posteriors: dict = {}
        classifier = self.source.get("column") or self.source.get("classifier")
        self.registry = fields.Registry(dataset, event, structure, classifier=classifier)
        self._models: dict[str, monolith.Monolith] = {}
        self._macro: np.ndarray | None = None

    def model(self, block: str) -> monolith.Monolith:
        if block not in self._models:
            cls = monolith.model_class(self.source)
            self._models[block] = cls.load(self.dataset, self.event, block, self.years, self.graph,
                                           device=self.device, **self._reader(), **({"rank": self.rank} if self.rank else {}))
            if self.supply and cls is monolith.Monolith and self._models[block].data.grain == "year":
                self.supplies[block] = facility.attach_supply(self._models[block], self.dataset, self.event)
        return self._models[block]

    def _reader(self) -> dict:
        """The reader arguments of ``monolith.assemble``: the event source and the population."""
        return {**self.source, **({} if self.population is None else {"population": self.population})}

    def _exposure(self, m: monolith.Monolith, leaves: np.ndarray, spatial: bool, x=None) -> np.ndarray | None:
        """Var(mu) from the population's uncertainty, None where it has none or is switched off."""
        if self.exposure_rho is None or m.data.S is None:
            return None
        return m.exposure_variance(leaves, spatial, self.exposure_rho, x)

    def posterior(self, key, model: monolith.Monolith) -> laplace.Posterior:
        """The Laplace posterior of a fitted block, drawn once per Expectations (``key`` names the fit)."""
        if key not in self._posteriors:
            self._posteriors[key] = laplace.Posterior(model)
            self._posteriors[key].sample(self.laplace)
        return self._posteriors[key]

    def field(self, node: str) -> fields.Field:
        return self.registry.field(node)

    def prospective(self, node: str | fields.Field, train_last: int, history: str = "auto",
                    course: bool | None = None, purpose: str = "expectation") -> Surprise:
        """Tier BP (``purpose="expectation"``) or BPA (``"alarm"``), two objects (ADR-0012): the expectation is
        calibrated and shows surprises; the alarm baseline detects epidemics. They differ in the history
        (`monolith.regime_history`): the expectation's regime mixture takes past epidemics as normal, the alarm's
        flat level (dengue: ``level36``) does not, and with it the lens recovers the epidemics the mixture
        explains (dengue 2019–23, recall 0.81 against 0.48). Everything else (the training fit's φ_extra,
        the Laplace and exposure variance) is shared. At the annual grain the two coincide, but for the tier's
        name. Tier BP: the years after ``train_last`` against a fit on the years up to it, the history
        extrapolated (`monolith.extrapolate_members`). Surveillance needs it: a fit over the whole period
        learns an epidemic as normal (COVID-19 in SIM: B34 deaths 2020 observed 213,152 against
        212,821 expected at B1, evaluation 2026-10-04). Calibration is recorded, never flagged:
        departing from the past is what this tier exists to show.

        The predictive of a cell is a mixture of NBs over the history's regimes (`prospective.py`): the
        expectation of each member carries the place's own damped course (``course``: None, the annual
        grain), the block's φ and the training fit's own place-year component φ_extra, with the Laplace
        draws' and the exposure's variance when present."""
        f = node if isinstance(node, fields.Field) else self.field(node)
        train = [y for y in self.years if y <= train_last]
        test = [y for y in self.years if y > train_last]
        cls = monolith.model_class(self.source)
        if issubclass(cls, monolith.MarkModel):
            raise NotImplementedError("the prospective tier is for counts")
        model = cls.load(self.dataset, self.event, f.block, train, self.graph, device=self.device, **self._reader(),
                         **({"rank": self.rank} if self.rank else {}))
        if purpose not in PURPOSE_TIER:
            raise ValueError(f"purpose {purpose!r}: one of {sorted(PURPOSE_TIER)}")
        regime = monolith.regime_history(model, history, purpose)
        point = "level36" if regime == "climatology" else regime
        tm, x_point = monolith.extrapolate(model, monolith.assemble(self.dataset, self.event, f.block, test,
                                                                    **self._reader()), point)
        names = [c for c in self.registry.leaves(f.node) if c in tm.data.leaves]
        trained = np.bincount(model.data.e, weights=model.data.y, minlength=len(model.data.leaves))
        new = [c for c in names if trained[model.data.leaves.index(c)] == 0]       # unseen by the fit (ADR-0011)
        names = [c for c in names if c not in new]
        if not names:
            raise LookupError(f"{f.id}: no category of the node has events in the fit up to {train_last}")
        leaves = np.array([tm.data.leaves.index(c) for c in names])
        li = np.array([model.data.leaves.index(c) for c in names])
        macro = self.macroregions(tm.data.places)
        extra = prospective.insample_extra(model, li, _dispersion_levels(tm.data.places, macro),
                                           self._exposure(model, li, True))
        T = tm.N.shape[1]
        shift, cvar = (0.0, 0.0)
        if (model.data.grain != "month") if course is None else course:
            shift, cvar = prospective.course(model, li, T)
        mu_point, _ = tm.expected(leaves, spatial=True, x=x_point)
        rel = np.expm1(cvar) + 0.0 * mu_point                      # relative Var(mu), added to each member's 1/φ
        if self.laplace:
            post = self.posterior(("BP", f.block, train_last), model)
            mom = post.moments(leaves, True, x_fn=lambda xd: (tm, monolith.extrapolate_effects(model, tm, xd, point)))
            rel = rel + mom["var"] / np.maximum(mom["mean"], 1e-300) ** 2
        ev = self._exposure(tm, leaves, True, x_point)
        if ev is not None:
            rel = rel + ev / np.maximum(mu_point, 1e-300) ** 2
        comps, mean = [], 0.0
        for w, x in monolith.extrapolate_members(model, tm, regime, model.effects()):
            mu, mu2 = tm.expected(leaves, spatial=True, x=x)
            mu, mu2 = mu * np.exp(shift), mu2 * np.exp(2 * shift)
            cells = laplace.predictive_phi(mu, rel * mu ** 2, mu2, model.phi)
            comps.append((w, mu, 1.0 / (1.0 / cells + 1.0 / extra)))
            mean = mean + w * mu
        y = tm.observed(leaves)
        u, z, phi = prospective.mixture_pit(y, comps, config.seed(f.id, "BP", "pit", tm.key()))
        cal = calibration(u, mean, macro)
        cal.update({"phi_source": "training fit", "regimes": len(comps), "phi": float(np.median(extra)),
                    "purpose": purpose, "history": regime})
        pop = tm.data.N.sum(axis=2)
        flags = np.zeros(y.shape, dtype=np.int8)
        flags[(pop <= 0) & (y > 0)] |= DENOMINATOR
        flags[mean < 1e-6] |= NO_INFORMATION
        unseen = {c: tm.observed(np.array([tm.data.leaves.index(c)])) for c in new}
        for ev in unseen.values():
            flags[ev > 0] |= NEW_CATEGORY
        w_info = np.where(np.isinf(phi), mean, mean / (1 + mean / phi))
        # the noise structure is the training fit's (N1): estimated on the years before t0, never on the watched ones
        mu_tr, mu2_tr = model.expected(li, spatial=True)
        phi_tr = 1.0 / (1.0 / laplace.predictive_phi(mu_tr, np.zeros_like(mu_tr), mu2_tr, model.phi)
                        + 1.0 / np.broadcast_to(np.asarray(extra, dtype=float), np.shape(extra)))
        noise = noise_structure(model.observed(li), mu_tr, np.broadcast_to(phi_tr, mu_tr.shape))
        cal["noise"] = {"kappa": noise.kappa, "rho": noise.rho}
        out = Surprise(f, PURPOSE_TIER[purpose], tm.data.places, tm.data.periods(), y, mean, phi, u, z, w_info, flags, cal,
                       noise=noise)
        out.extras = {"train": [int(train[0]), int(train[-1])]}
        if unseen:
            # a category the fit never saw has no expectation: it is out of the node (it would break the chapter's
            # calibration) and is reported by its own count, per year, with an alarm at NEW_CATEGORY_ALARM events
            years = np.asarray(out.years) // (100 if tm.data.grain == "month" else 1)
            per_year = {c: {int(yr): float(ev[:, years == yr].sum()) for yr in np.unique(years)} for c, ev in unseen.items()}
            out.extras["new_category"] = {c: v for c, v in per_year.items() if sum(v.values()) > 0}
            out.extras["new_category_alarm"] = [(c, yr, n) for c, v in per_year.items() for yr, n in v.items()
                                                if n >= NEW_CATEGORY_ALARM]
        return out

    def _surprise_across(self, f: fields.Field, tier: str) -> Surprise:
        """A field whose leaves lie in several blocks (a list item, ARCHITECTURE §3.3 and §8.6): each block's part from
        its own fit, summed. The blocks are fitted independently, so the expectations and their extra-Poisson
        variances add, Σ_b Σμ²/φ_b, carried at φ = 1. The population's uncertainty is one source for every block, so
        its standard deviations add, not its variances. B2's refit runs on the sum. Laplace draws are per block and
        are not combined here."""
        if self.laplace:
            raise NotImplementedError("Laplace draws across blocks: a field across blocks is read at the MAP")
        y = mu = mu2 = ev_sd = None
        m0 = None
        phis: dict[str, float] = {}
        for b in self.registry.blocks(f.node):
            m = self.model(b)
            leaves = np.array([m.data.leaves.index(c) for c in self.registry.leaves(f.node) if c in m.data.leaves])
            if len(leaves) == 0:
                continue
            if m0 is None:
                m0 = m
            elif not np.array_equal(m.data.places, m0.data.places) or not np.array_equal(m.data.periods(), m0.data.periods()):
                raise ValueError(f"{f.id}: blocks {m0.data.block} and {b} do not share places and periods")
            mb, mb2 = m.expected(leaves, spatial=SPATIAL[tier])
            first = mb
            if tier == "B0":
                mb, mb2 = _relevel_b0(m, leaves, mb, mb2)
            ex2 = mb2 / m.phi if np.isfinite(m.phi) else np.zeros_like(mb2)
            ev = self._exposure(m, leaves, SPATIAL[tier])
            sd = None if ev is None else np.sqrt(ev) * np.divide(mb, first, out=np.ones_like(mb), where=first > 0)
            yb = m.observed(leaves)
            phis[b] = float(m.phi)
            y, mu, mu2 = (yb, mb, ex2) if y is None else (y + yb, mu + mb, mu2 + ex2)
            ev_sd = sd if ev_sd is None else (ev_sd + sd if sd is not None else ev_sd)
        if m0 is None:
            raise LookupError(f"{f.id}: none of its leaves is in a fitted block")
        extras: dict = {}
        mu_point = mu
        if tier == "B2":
            axis = m0.data.years if m0.data.grain == "year" else np.arange(y.shape[1], dtype=float)
            mu, extras = refit_place_trend(y, mu, mu2, 1.0, axis)
        elif tier == "B2s":
            mu, extras = refit_place_season(y, mu, mu2, 1.0, m0.data.month_of_year)
        if tier in ("B2", "B2s"):
            mu2 = mu2 * np.divide(mu, mu_point, out=np.ones_like(mu), where=mu_point > 0) ** 2
        extras.pop("eta_var", None)
        var = None if ev_sd is None else (ev_sd * np.divide(mu, mu_point, out=np.ones_like(mu), where=mu_point > 0)) ** 2
        out = _assemble(f, tier, m0, y, mu, mu2, 1.0, self.macroregions(m0.data.places), var=var)
        if out.calibration.get("phi_source") == "block":
            # φ = 1 is the carrier of the summed Σμ²/φ_b, not a dispersion: report each block's
            out.calibration["phi"] = None
            out.calibration["phi_by_block"] = phis
        out.extras = {**extras, "blocks": self.registry.blocks(f.node)}
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
        if "+" in f.block or self.registry.level.get(f.node) == "list":
            return self._surprise_across(f, tier)
        m = self.model(f.block)
        if tier == "B2s" and m.data.grain != "month":
            raise NotImplementedError("B2s needs a sub-annual grain; this block is annual")
        key = {**m.key(), "field": f.id, "tier": tier, "surprise": 2}
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
        mu_first = mu
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
        ev = self._exposure(m, leaves, SPATIAL[tier])
        if ev is not None:
            # the exposure's variance moves with the tier's mean (B0 re-levelled, B2 refit): by the square of the ratio
            ev = ev * np.divide(mu, mu_first, out=np.ones_like(mu), where=mu_first > 0) ** 2
            var = ev if var is None else var + ev
        out = _assemble(f, tier, m, y, mu, mu2, m.phi, self.macroregions(m.data.places), var=var)
        if tier != "B1":
            # the noise structure is stage B's, the B1 predictive's (ADR-0029): a reference (B0 without the place
            # effects, B2 with a refitted course per place) is measured against, never re-estimated on. B2's own
            # residuals hide the persistence a trend must be judged against (SIH trends: 25 findings per shifted world
            # with B2's ρ)
            mu_b1 = m.expected(leaves, spatial=True)[0]
            # the tier's φ came out of _assemble divided by the tier's own κ: undone here, then B1's applied
            phi_b1 = np.broadcast_to(np.asarray(out.phi, dtype=float), mu_b1.shape) * out.calibration["noise"]["kappa"]
            nz = noise_structure(y, mu_b1, phi_b1)
            out.calibration["noise"] = {"kappa": nz.kappa, "rho": nz.rho}
            out.phi, out.u, out.z, out.w, out.noise = with_noise(y, out.mu, phi_b1, nz,
                                                                 config.seed(f.id, tier, "pit", m.key()))
        out.extras = extras
        if cache:
            store.put_table("surprise", key, out.table(), {"calibration": out.calibration,
                                                            **{k: v.tolist() for k, v in extras.items()}})
        return out


def _relevel_b0(m: monolith.Monolith, leaves: np.ndarray, mu: np.ndarray, mu2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """B0's re-levelling to the national total of each year (see `Expectations.surprise`)."""
    ref, _ = m.expected(leaves, spatial=True)
    c = ref.sum(0) / np.maximum(mu.sum(0), 1e-300)
    return mu * c, mu2 * c ** 2


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
    extra = place_year_phi(y, mu, cells, *_dispersion_levels(m.data.places, macro))
    extra_cells = np.asarray(extra)[:, None] if np.ndim(extra) else extra
    attempts = [("block", phi_block, cells), ("field", extra, 1.0 / (1.0 / cells + 1.0 / extra_cells))]
    for source, phi, phi_agg in attempts:
        u, z = randomised_pit(y, mu, phi_agg, seed)
        cal = calibration(u, mu, macro)
        cal["phi_source"] = source
        cal["phi"] = float(np.median(phi)) if np.ndim(phi) else float(phi)
        if np.ndim(phi):
            cal["phi_by_macroregion"] = {str(r): float(np.median(phi[macro == r])) for r in np.unique(macro)}
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
    noise = noise_structure(y, mu, phi_agg)
    cal["noise"] = {"kappa": noise.kappa, "rho": noise.rho}
    phi_agg, u, z, w, noise = with_noise(y, mu, phi_agg, noise, seed)
    return Surprise(f, tier, m.data.places, m.data.periods(), y, mu, phi_agg, u, z, w, flags, cal, noise=noise)


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


def _dispersion_levels(places: np.ndarray, macro: np.ndarray) -> list[np.ndarray]:
    """The grouping labels of ``DISPERSION_LEVELS``, coarse to fine, one per place."""
    labels = {"macro": np.asarray(macro).astype(str), "state": (np.asarray(places) // 10000).astype(str)}
    return [labels[k] for k in DISPERSION_LEVELS]


def lift(s: Surprise, scale, extra_phi: float | np.ndarray | None = None) -> Surprise:
    """A Surprise at a coarser scale (`scans.scales.Scale`: immediate region, state): Σy and Σμ per unit and period,
    the dispersion of a sum of independent cells (M² / Σ μ²/φ), with an optional unit-period variance component
    1/φ_extra on top (`place_year_phi` on the training years), then a fresh randomised PIT. A rare outcome is tested
    here: at the municipality its cells are mostly zero and their surprises noise (dengue → microcephaly)."""
    y, mu = scale.sum(s.y), scale.sum(s.mu)
    v = scale.sum(np.where(np.isfinite(s.phi), s.mu ** 2 / np.where(np.isfinite(s.phi), s.phi, 1.0), 0.0))
    phi = np.divide(mu ** 2, v, out=np.full(mu.shape, np.inf), where=v > 0)
    if extra_phi is not None:
        phi = 1.0 / (1.0 / phi + 1.0 / extra_phi)
    # one random stream per field and scale: shared draws would correlate fields
    u, z = randomised_pit(y, mu, phi, config.seed(s.field.id, s.tier, "lift", scale.name, scale.n))
    w = np.where(np.isinf(phi), mu, mu / (1 + mu / phi))
    units = np.asarray(scale.units)
    units = units.astype(np.int64) if all(str(k).isdigit() for k in units) else units   # IBGE codes stay integers
    return Surprise(s.field, s.tier, units, s.years, y, mu, phi, u, z, w,
                    np.zeros(y.shape, dtype=np.int8), {}, {"scale": scale.name}, noise=s.noise)


def place_year_phi(y: np.ndarray, mu: np.ndarray, phi_cells: np.ndarray, *levels: np.ndarray) -> float | np.ndarray:
    """The field's place-year variance component, by maximum likelihood on its aggregate cells:
    Var(Y) = μ + μ²/φ_cells + μ²/φ_extra, i.e. NB with 1/φ = 1/φ_cells + 1/φ_extra. Cells
    within a place-year share variation the expectation does not model; summing them adds it
    coherently, which the independent-cell φ_cells misses (a U-shaped PIT, chapter IX B1).

    With no ``levels`` one value for the field. With grouping labels per place, coarse to fine
    (macro-region, then state), the component varies by group: each group's log(1/φ_extra) is
    estimated by maximum likelihood on its own cells, then shrunk toward its parent's value by
    the between-group variance τ² the groups themselves show (a random-effects moment estimate
    on the observed information, so a group with little information keeps its parent's value).
    Returns φ_extra per place."""
    ok = mu > 1e-9
    inv_c = np.where(np.isfinite(phi_cells), 1.0 / phi_cells, 0.0)
    lo, hi = -np.log(1e7), -np.log(1e-2)         # bounds of log κ, κ = 1/φ_extra

    def fit(sel: np.ndarray) -> tuple[float, float]:
        yy, mm, ic = y[sel], mu[sel], inv_c[sel]
        pos = yy > 0           # a zero count adds only φ log(φ/(φ+μ)): the gamma terms are needed where y > 0 (sparse fields: few)
        yp, mp, ip = yy[pos], mm[pos], ic[pos]

        def nll(log_k: float) -> float:
            k = np.exp(log_k)
            phi = 1.0 / (ic + k)
            phi_p = 1.0 / (ip + k)
            return -float(np.sum(phi * np.log(phi / (phi + mm)))
                          + np.sum(special.gammaln(yp + phi_p) - special.gammaln(phi_p) + yp * np.log(mp / (phi_p + mp))))

        res = optimize.minimize_scalar(nll, bounds=(lo, hi), method="bounded")
        h = 0.25
        info = (nll(res.x + h) - 2 * nll(res.x) + nll(res.x - h)) / h ** 2     # observed information in log κ
        return float(res.x), max(info, 1e-9)

    def to_phi(log_k):
        return np.where(np.asarray(log_k) < lo + 0.01, np.inf, np.exp(-np.asarray(log_k)))

    top, _ = fit(ok)
    if not levels:
        return float(to_phi(top))
    cur = np.full(mu.shape[0], top)
    for lab in levels:
        new = cur.copy()
        found = []
        for g in np.unique(lab):
            rows = lab == g
            sel = ok & rows[:, None]
            if sel.sum() >= MIN_DISPERSION_CELLS:
                est, info = fit(sel)
                found.append((rows, est - cur[rows][0], 1.0 / info))
        if found:
            d = np.array([f[1] for f in found])
            v = np.array([f[2] for f in found])
            w = 1.0 / v
            tau2 = max(0.0, (float(np.sum(w * d ** 2)) - len(d)) / float(np.sum(w)))      # E Σ w d² = τ² Σ w + n
            for rows, dg, vg in found:
                new[rows] = cur[rows][0] + dg * tau2 / (tau2 + vg)
        cur = new
    return to_phi(cur)


# ---------------------------------------------------------------------- N1: the predictive's noise structure

def _detrend_projection(T: int) -> np.ndarray:
    """M = I − X(XᵀX)⁻¹Xᵀ for X = [1, t]: the residual maker of a place's own level and linear trend."""
    X = np.column_stack([np.ones(T), np.arange(T) - (T - 1) / 2])
    return np.eye(T) - X @ np.linalg.solve(X.T @ X, X.T)


def noise_structure(y: np.ndarray, mu: np.ndarray, phi: np.ndarray, min_expected: float = 0.2, lags: int = 2) -> Noise:
    """ARCHITECTURE §6.1, N1 (ADR-0029): the predictive's noise structure over periods (`Noise`), by the bias-corrected
    moments of regression residuals. Each place's standardised residual series z = (y − μ)/√V loses its own level and
    linear trend (e = Mz, `_detrend_projection`); then E[Σ_t e_t e_{t+k}] = tr(L_k M Σ_u M), with
    Σ_u = p_u I + κ f_u R(ρ), p_u and f_u the place's Poisson and frailty shares of V, and R(ρ) the AR(1) correlation
    (the copula's latent correlation stands for the frailties' own: exact as κ/φ → 0, and the frailty shares of the
    fields measured are a few per cent).
    (κ, ρ) match the pooled lag 0..``lags`` sums by least squares. The places with at least ``min_expected`` events a
    period enter.

    Why the detrending (measured 2026-10-06, `data/probes/noise_structure.json`): B1's residual covariances fall from
    +0.8σ² at lag 1 to −2.8σ² at lag 9 on stroke deaths, the signature of place-specific trends B1 does not hold.
    Those are departures from the reference, what the trend lens exists to find; fitted as noise they read as a
    persistent component or ρ → 1, and would hide the signal they are. Lags 0..2 only: a place's slower nonlinear
    wander survives the linear detrending (ρ → 0.95 on SINASC with lags to 4), and is the departure models' to judge
    against their empirical nulls (stage C), not B's noise."""
    U, T = y.shape
    if T < 5:
        return Noise()
    keep = mu.mean(1) >= min_expected
    if keep.sum() < 10:
        return Noise()
    m, r = mu[keep], (y - mu)[keep]
    ph = phi[keep] if np.ndim(phi) else np.full(m.shape, phi)
    s2 = Noise().frailty_variance(ph)
    v = m + m ** 2 * s2
    p_u = (m / v).mean(1)
    f_u = (m ** 2 * s2 / v).mean(1)                       # the frailty's share of each cell's variance
    P, F = float(p_u.sum()), float(f_u.sum())
    if F <= 0:
        return Noise()
    M = _detrend_projection(T)
    e = (r / np.sqrt(v)) @ M
    K = min(lags, T - 3)
    obs = np.array([float((e[:, :T - k] * e[:, k:]).sum()) for k in range(K + 1)])
    tk = np.arange(T)
    trLM = np.array([np.trace(M, offset=k) for k in range(K + 1)])  # tr(L_k M): L_k picks the entries (t, t + k)

    def expected(par: np.ndarray) -> np.ndarray:
        kap, rh = par
        MRM = M @ (rh ** np.abs(tk[:, None] - tk[None, :])) @ M
        return P * trLM + kap * F * np.array([np.trace(MRM, offset=k) for k in range(K + 1)])

    scale = float(np.abs(obs).max()) or 1.0
    fit = optimize.least_squares(lambda par: (expected(par) - obs) / scale, x0=[1.0, 0.2],
                                 bounds=([0.0, -0.5], [1e3, 0.95]))
    kap, rh = (float(x) for x in fit.x)
    return Noise(round(kap, 4), round(rh, 4))


def lag_covariance(mu: np.ndarray, phi: np.ndarray, noise: Noise, k: int) -> np.ndarray:
    """[U, T − k] Cov(y_t, y_{t+k}) of a place's cells under the predictive's noise structure (`Noise`; the copula's
    correlation taken as the frailties')."""
    s2 = noise.frailty_variance(np.broadcast_to(np.asarray(phi, dtype=float), mu.shape))
    return mu[:, :-k] * mu[:, k:] * noise.rho ** k * np.sqrt(s2[:, :-k] * s2[:, k:])


def cell_variance(mu: np.ndarray, phi: np.ndarray, noise: Noise) -> np.ndarray:
    """Var(y) of each cell under the predictive with its noise structure: μ + μ²κ/φ."""
    return mu + mu ** 2 * noise.frailty_variance(np.broadcast_to(np.asarray(phi, dtype=float), mu.shape))


def suffix_variance(mu: np.ndarray, phi: np.ndarray, noise: Noise, scale: float = 1.0, tol: float = 1e-4) -> np.ndarray:
    """[U, T] Var(Σ_{s ≥ t} y_s) per place under the predictive, the means scaled by ``scale`` (a null boundary θ0·μ):
    the cells' variances plus twice their covariances over periods, lags truncated where ρ^k < ``tol``."""
    m = scale * mu
    phi_ = np.broadcast_to(np.asarray(phi, dtype=float), mu.shape)
    row = np.zeros(mu.shape)                                      # Σ_k Cov(y_t, y_{t+k}): cell t's forward covariances
    k = 1
    while noise.rho > 0 and k < mu.shape[1] and noise.rho ** k >= tol:
        row[:, :-k] += lag_covariance(m, phi_, noise, k)
        k += 1
    return np.cumsum((cell_variance(m, phi_, noise) + 2 * row)[:, ::-1], 1)[:, ::-1]


def copula_normals(shape: tuple, rho: float, rng: np.random.Generator) -> np.ndarray:
    """Standard normals [..., T] with an AR(1) correlation ρ over the last axis: the copula's latent field."""
    eps = np.empty(shape)
    eps[..., 0] = rng.standard_normal(shape[:-1])
    innov = np.sqrt(max(1.0 - rho ** 2, 0.0))
    for t in range(1, shape[-1]):
        eps[..., t] = rho * eps[..., t - 1] + innov * rng.standard_normal(shape[:-1])
    return eps


def gamma_frailty(eps: np.ndarray, phi: np.ndarray, noise: Noise) -> np.ndarray:
    """The gamma frailty (mean 1, variance κ/φ) at the copula's normals ``eps``: G⁻¹(Φ(ε)) (1 where φ is infinite)."""
    s2 = noise.frailty_variance(np.broadcast_to(np.asarray(phi, dtype=float), eps.shape[-2:]))
    s2 = np.broadcast_to(s2, eps.shape)
    out = np.ones(eps.shape)
    pos = s2 > 0
    shape = 1.0 / s2[pos]
    out[pos] = stats.gamma.ppf(special.ndtr(eps[pos]), shape, scale=1.0 / shape)
    return out


def frailty(phi: np.ndarray, noise: Noise, rng: np.random.Generator) -> np.ndarray:
    """A draw of the predictive's frailty [U, T] (`Noise`): gamma marginals joined by the AR(1) Gaussian copula."""
    phi_ = np.asarray(phi, dtype=float)
    return gamma_frailty(copula_normals(phi_.shape, noise.rho, rng), phi_, noise)


def replicate_correlated(mu: np.ndarray, phi: np.ndarray, noise: Noise, rng: np.random.Generator) -> np.ndarray:
    """Counts y* [U, T] from the predictive with its noise structure: Poisson(μ · `frailty`), NB(μ, φ/κ) marginally."""
    phi_ = np.broadcast_to(np.asarray(phi, dtype=float), mu.shape)
    return rng.poisson(mu * frailty(phi_, noise, rng)).astype(float)


def with_noise(y: np.ndarray, mu: np.ndarray, phi: np.ndarray, noise: Noise, seed: int
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Noise]:
    """The predictive with its estimated noise structure folded in: φ/κ, the PIT u and z under it, the cells' weights,
    and the noise left to carry (κ = 1, ρ)."""
    phi_eff = np.broadcast_to(np.asarray(phi, dtype=float), mu.shape) / max(noise.kappa, 1e-12)
    u, z = randomised_pit(y, mu, phi_eff, seed)
    w = np.where(np.isinf(phi_eff), mu, mu / (1 + mu / phi_eff))
    return phi_eff, u, z, w, Noise(1.0, noise.rho)


def trend_inflation(rho_count: np.ndarray | float) -> np.ndarray | float:
    """The factor on a slope's variance when its series' errors are AR(1) with lag-1 correlation ``rho_count``
    ((1 + ρ)/(1 − ρ), the large-sample inflation of a least-squares trend; Bence 1995)."""
    r = np.clip(rho_count, 0.0, 0.95)
    return (1 + r) / (1 - r)


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
                outer: int = 20, tau: np.ndarray | None = None, variance: bool = False,
                X_new: np.ndarray | None = None) -> tuple:
    """Per place u, log μ'_ut = log μ_ut + X_t·b_u with b_u ~ N(0, diag(1/τ)): exact p×p Newton per
    place under NB working weights, the τ's by Fellner–Schall. Returns (μ', b, posterior sd, τ);
    with ``variance`` also Var(X_t·b_u) per cell, and with ``X_new`` (the design at later periods) the
    course's forecast X_new·b_u and its variance X_new H⁻¹ X_newᵀ, both [places, periods]."""
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
        out = (mu * np.exp(b @ X.T), b, sd, tau, np.einsum("ti,uij,tj->ut", X, Hinv, X))
        if X_new is not None:
            out += (b @ X_new.T, np.einsum("ti,uij,tj->ut", X_new, Hinv, X_new))
        return out
    return mu * np.exp(b @ X.T), b, sd, tau


def _from_table(f: fields.Field, tier: str, t: pa.Table, meta: dict | None) -> Surprise:
    places = np.unique(t.column("u").to_numpy())
    years = np.unique(t.column("year").to_numpy())
    shape = (len(places), len(years))
    col = lambda c: t.column(c).to_numpy().reshape(shape)  # noqa: E731
    meta = meta or {}
    extras = {k: np.asarray(meta[k]) for k in ("alpha", "beta", "alpha_sd", "beta_sd", "tau") if k in meta}
    return Surprise(f, tier, places, years, col("y"), col("mu"), col("phi"), col("pit"), col("z"), col("w"),
                    col("flags"), meta.get("calibration", {}), extras,
                    noise=Noise(**meta.get("calibration", {}).get("noise", {})))
