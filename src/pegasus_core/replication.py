"""Replication from independent units (ARCHITECTURE §8.3, ADR-0015).

A lead is replicated only by units that took no part in selecting it. Splitting a cell's own events cannot do
that: the sides are thinned from one cell and share its frailty, so under extra-Poisson variation the
excursion that selected the cell on one side shows on the other (a marginal test on the second side called 0.28 to
1.00 of the null cells replicated, and the test conditional on the first was nearly powerless; ADR-0007,
withdrawn). The independent units are

* **later years** (`test_prospective`): the lead is selected on the years up to t, the model is fitted without the
  later ones (BP, `Expectations.prospective`), and the same locus is tested on them, re-levelled to the state's
  course of each year so a shock that touches every place does not count (COVID-19 in 2020-21). A departure
  that persists or recurs replicates; a one-off event does not, by nature.
* **other places** (`spatial_split`, `test_spatial`): for a claim about a predeclared unit (a state, a region)
  the lens is run on one random half of its municipalities and tested on the other, the halves drawn by immediate
  region and separated by a buffer of the graph's neighbours (ADR-0005: places that touch share their shocks).
* **another record system** (`corroborate.py`): the same place and years in S2iD, SINAN or SIH.

The event sides survive for one thing: the *size* of an effect after selection. Given a cell's rate its sides
are independent Poisson counts, so the effect read on side E is unbiased for that rate whatever side A selected
(`honest_effect`). It includes the cell's own frailty; it is not evidence that the effect recurs.

The simulations at the end (`simulate_*`) measure each tier's size and power on negative-binomial worlds.
"""

from __future__ import annotations

import dataclasses
import types
from typing import Any

import numpy as np
from scipy import stats

from . import config, control, graphs, leads, monolith, store, surprise
from .scans import explain, lenses

# ---------------------------------------------------------------------- the sides of a block (effect sizes)


def _sides_key(dataset: str, event: str, block: str, years: list[int]) -> dict[str, Any]:
    return {"dataset": dataset, "event": event, "block": block, "years": list(years), "data": config.data_version(),
            "sides": control.SIDES}


def deal(dataset: str, event: str, block: str, years: list[int]) -> tuple[monolith.BlockData, dict[str, np.ndarray]]:
    """A block's cell rows and every side's events on them, dealt once (fixed seed) and stored."""
    key = _sides_key(dataset, event, block, years)
    arr = store.get_arrays("split_sides", key)
    meta = store.manifest("split_sides", key)
    if arr is not None and meta is not None:
        sides = {k: arr[f"y_{k}"].astype(float) for k in control.SIDES}
        return monolith.BlockData(dataset, event, block, arr["years"], arr["places"], meta["leaves"], meta["groups"],
                                  arr["leaf_group"], arr["N"], arr["e"], arr["u"], arr["t"], arr["g"], sum(sides.values()),
                                  meta.get("unallocated", {}), meta["key"]), sides
    full = monolith.assemble(dataset, event, block, years)
    sides = {k: v.astype(float) for k, v in
             control.event_sides(full.y, f"event-sides-v1|{dataset}|{event}|{block}|{list(years)}").items()}
    store.put_arrays("split_sides", key,
                     {"years": full.years, "places": full.places, "leaf_group": full.leaf_group, "N": full.N, "e": full.e,
                      "u": full.u, "t": full.t, "g": full.g, **{f"y_{k}": v.astype(np.int32) for k, v in sides.items()}},
                     {"leaves": full.leaves, "groups": full.groups, "unallocated": full.unallocated, "key": full.key})
    return full, sides


def _a_model(full: monolith.BlockData, y_a: np.ndarray, graph: str, device: str = "cpu") -> monolith.Monolith:
    k = y_a > 0
    data = dataclasses.replace(full, e=full.e[k], u=full.u[k], t=full.t[k], g=full.g[k], y=y_a[k].astype(float),
                               key={**full.key, "split": "A"})
    return monolith.Monolith(data, graphs.graph(data.places, graph), graph, device=device)


def prepare(dataset: str, event: str, block: str, years: list[int], graph: str = "contiguity",
            device: str = "cpu", log=print) -> monolith.Monolith:
    """Deal a block's events to the sides, fit the block on side A alone and store the fit. Without it side A reads
    the fit on all the events, scaled (`load_base`): its expectation then carries a little of side E's events."""
    full, sides = deal(dataset, event, block, years)
    model = _a_model(full, sides["A"], graph, device)
    model.fit(outer=40, warm="auto", mean_tol=1.0, log=log)    # side A starts from the fit on all the events
    model.save()
    return model


def load_base(dataset: str, event: str, block: str, years: list[int], graph: str = "contiguity", device: str = "cpu"
              ) -> tuple[monolith.Monolith, monolith.BlockData, dict[str, np.ndarray], float]:
    """The fit the sides read: side A's own (if `prepare` ran for the block), else the fit on all the events.
    Returns it, the cell rows, every side's events, and the fraction of the events the fit saw."""
    import torch

    full, sides = deal(dataset, event, block, years)
    model = _a_model(full, sides["A"], graph, device)
    arrays = store.get_arrays("monolith", model.key())
    meta = store.manifest("monolith", model.key())
    if arrays is None or meta is None:
        return monolith.Monolith.load(dataset, event, block, years, graph, device=device), full, sides, 1.0
    with torch.no_grad():
        for k, v in arrays.items():
            model.params[k].copy_(torch.as_tensor(v))
    for k, tau in meta["taus"].items():
        model.components[k].tau = float(tau)
    model.phi = float(meta["phi"]) if meta.get("phi") is not None else float("nan")
    model._restore(meta)
    model.history = [{"seconds": meta.get("fit_seconds")}]
    return model, full, sides, control.SIDES["A"]


class SideModel:
    """One side's view of a fit: its own observed counts, the fit's expectation times the side's fraction over the
    fraction of the events the fit saw."""

    def __init__(self, base: monolith.Monolith, full: monolith.BlockData, y_side: np.ndarray, ratio: float):
        self._base, self._ratio = base, ratio
        self.data = dataclasses.replace(full, y=y_side)
        # admission reads all the events: the same fields are scanned on every side
        self.full_counts = (full.e, full.u, full.y)

    def __getattr__(self, name: str):
        return getattr(self._base, name)

    def observed(self, leaves: np.ndarray) -> np.ndarray:
        return monolith.Monolith.observed(self, leaves)

    def observed_by_group(self, leaves: np.ndarray) -> np.ndarray:
        return monolith.Monolith.observed_by_group(self, leaves)

    def expected(self, leaves: np.ndarray, spatial: bool = True, x=None) -> tuple[np.ndarray, np.ndarray]:
        mu, mu2 = self._base.expected(leaves, spatial, x)
        return mu * self._ratio, mu2 * self._ratio ** 2

    def expected_by_group(self, leaves: np.ndarray, spatial: bool = True) -> np.ndarray:
        return self._base.expected_by_group(leaves, spatial) * self._ratio


class SideExpectations(surprise.Expectations):
    """`surprise.Expectations` over one side of the events: the registry and the settings of ``base``, models from the A fit."""

    def __init__(self, base: surprise.Expectations, side: str):
        self.__dict__.update(base.__dict__)
        self._models = {}
        self.side = side

    def model(self, block: str):
        if block not in self._models:
            base, full, sides, seen = load_base(self.dataset, self.event, block, self.years, self.graph, self.device)
            self._models[block] = SideModel(base, full, sides[self.side], control.SIDES[self.side] / seen)
        return self._models[block]


# ---------------------------------------------------------------------- what a lead claims

THETA = {"outbreak": lenses.RATE_RATIO, "change_point": lenses.RATE_RATIO, "space_time": lenses.RATE_RATIO,
         "spatial_cluster": lenses.SPATIAL_RATE_RATIO, "trend_divergence": lenses.RATE_RATIO}


def span_direction(x: leads.Lead) -> tuple[list[int] | None, int]:
    """A lead's years (first, last) and its direction: +1 up, -1 down, 0 a pattern."""
    span = x.locus.get("years")
    if x.estimand == "group_disparity":
        return span, 0
    if x.estimand == "space_time":
        return span, 1 if x.locus.get("direction") == "up" else -1
    size = np.log(max(x.effect, 1e-12)) if x.scale == "rate_ratio" else x.effect
    return span, int(np.sign(size))


def match(x: leads.Lead, candidates: list[leads.Lead]) -> list[leads.Lead]:
    """The candidates that are the same finding as ``x``: the same direction, a place in common and, for a
    window, a year in common."""
    _, d = span_direction(x)
    px = set(x.locus.get("places", []))
    yx = x.locus.get("years")
    out = []
    for c in candidates:
        if span_direction(c)[1] != d or not px & set(c.locus.get("places", [])):
            continue
        yc = c.locus.get("years")
        if yx and yc and (yc[-1] < yx[0] or yc[0] > yx[-1]):
            continue
        out.append(c)
    return out


# ---------------------------------------------------------------------- the size after selection (side E)


def honest_effect(s: surprise.Surprise, x: leads.Lead, conf: float = 0.90) -> dict[str, Any]:
    """The lead's rate ratio on a side that did not select it (``s`` is side E's surprise): (Y + ½) / (M + ½) over
    the lead's places and years, with the exact Poisson interval of Y. Given each cell's rate the sides are
    independent Poisson counts, so the interval covers the realised rate ratio of the locus (its own frailty
    included, not the model's persistent rate) at its nominal level whatever side A selected. Leads without a
    rate-ratio window (a trend's slope, a pattern) have no such size."""
    span, direction = span_direction(x)
    if direction == 0 or x.estimand == "trend_divergence":
        return {"sized": False, "reason": "no rate-ratio window"}
    rows = np.nonzero(np.isin(s.places, x.locus.get("places", [])))[0]
    if rows.size == 0:
        return {"sized": False, "reason": "locus outside the grid"}
    cols = (s.years >= span[0]) & (s.years <= span[-1]) if span else np.ones(len(s.years), dtype=bool)
    sub = np.ix_(rows, np.nonzero(cols)[0])
    Y, M = float(s.y[sub].sum()), float(s.mu[sub].sum())
    a = (1 - conf) / 2
    lo = stats.chi2.ppf(a, 2 * Y) / 2 if Y > 0 else 0.0
    hi = stats.chi2.ppf(1 - a, 2 * Y + 2) / 2
    return {"sized": True, "effect": (Y + 0.5) / (M + 0.5), "interval": [lo / max(M, 1e-12), hi / max(M, 1e-12)],
            "observed": Y, "expected": M, "selected_effect": float(x.effect)}


# ---------------------------------------------------------------------- later years (BP)


def relevel(s: surprise.Surprise, exclude: np.ndarray, level: str = "state") -> surprise.Surprise:
    """The surprise with its expectation re-levelled to the observed course of each year: by state (or the nation)
    and year, the ratio of the observed to the expected counts of the places outside ``exclude`` (the locus, which
    must not set its own level). The held-out years carry shocks the fit could not know (COVID-19 in 2020-21): what
    a lead claims is a departure of its places from the course of their surroundings, so that course is estimated
    on the held-out years themselves. A group too small to level (fewer than 100 expected events in the year) uses
    the nation's ratio."""
    U = len(s.places)
    outside = np.ones(U, dtype=bool)
    outside[exclude] = False
    key = np.zeros(U, dtype=int) if level == "nation" else (s.places // 10000).astype(int)
    _, g = np.unique(key, return_inverse=True)
    G = int(g.max()) + 1
    sy, sm = np.zeros((G, s.y.shape[1])), np.zeros((G, s.y.shape[1]))
    np.add.at(sy, g[outside], s.y[outside])
    np.add.at(sm, g[outside], s.mu[outside])
    nation = sy.sum(0) / np.maximum(sm.sum(0), 1e-300)
    ratio = np.where(sm >= 100, sy / np.maximum(sm, 1e-300), nation[None, :])
    return dataclasses.replace(s, mu=s.mu * ratio[g])


def test_prospective(sp: surprise.Surprise, estimand: str, locus: dict[str, Any], direction: int, level: str = "state"
                     ) -> dict[str, Any]:
    """A fixed locus tested on the years a fit did not see (``sp`` is the BP surprise of the node: expectation from the fit
    up to the last training year, the place's own course not carried forward). One-sided, in the lead's direction,
    against the lens's own minimum effect, on the places' counts summed over all the later years (a recurrence in
    any one of them shows; no choice of year is made). Re-levelled by state and year (`relevel`). The effect
    is a size on data that selected nothing."""
    if direction == 0:
        return {"tested": False, "reason": "no direction"}
    rows = np.nonzero(np.isin(sp.places, locus.get("places", [])))[0]
    if rows.size == 0:
        return {"tested": False, "reason": "locus outside the grid"}
    s = relevel(sp, rows, level)
    theta = THETA.get(estimand, lenses.RATE_RATIO)
    scale = theta if direction > 0 else 1 / theta
    Y, M = float(s.y[rows].sum()), float(s.mu[rows].sum())
    if M <= 0:
        return {"tested": False, "reason": "no expectation"}
    p = explain.tail_p(Y, s.mu[rows] * scale, s.phi[rows], up=direction > 0)
    return {"tested": True, "p": p, "effect": (Y + 0.5) / (M + 0.5), "observed": Y, "expected": M,
            "years": [int(s.years[0]), int(s.years[-1])], "train": sp.extras.get("train")}


# ---------------------------------------------------------------------- other places


def spatial_split(unit: np.ndarray, region_of: dict[int, str], edges: np.ndarray, places: np.ndarray, seed_text: str
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Two disjoint sets of a unit's places for selecting and for testing: the unit's immediate regions halved at
    random (`control.spatial_halves`), then every place of either half that touches a place of the other removed
    (``edges``: pairs of indices into ``places``). Places that touch share their shocks; with the buffer the halves
    share what the graph's neighbourhoods share only through the unit as a whole, which is the claim."""
    h1, h2 = control.spatial_halves(unit, region_of, f"spatial-halves-v1|{seed_text}")
    index = {int(u): i for i, u in enumerate(places)}
    side = np.zeros(len(places), dtype=np.int8)
    side[[index[int(u)] for u in h1]] = 1
    side[[index[int(u)] for u in h2]] = 2
    a, b = edges[:, 0], edges[:, 1]
    touch = np.zeros(len(places), dtype=bool)
    cross = (side[a] > 0) & (side[b] > 0) & (side[a] != side[b])
    touch[a[cross]] = True
    touch[b[cross]] = True
    keep = ~touch
    return (np.array([u for u in h1 if keep[index[int(u)]]], dtype=h1.dtype),
            np.array([u for u in h2 if keep[index[int(u)]]], dtype=h2.dtype))


def test_trend_unit(s: surprise.Surprise, locus: dict[str, Any], direction: int) -> dict[str, Any]:
    """A trend lead at an aggregate scale (region, state) against the national course on the surprise ``s``: the
    places of ``locus`` as one NB series, `lenses.unit_trends`' estimator (vague prior, dispersion from a cubic
    course), one-sided against the scale's minimum divergence delta (Student t on T - 4 df)."""
    if direction == 0:
        return {"tested": False, "reason": "no direction"}
    rows = np.nonzero(np.isin(s.places, locus.get("places", [])))[0]
    if rows.size == 0:
        return {"tested": False, "reason": "locus outside the grid"}
    x = (s.years - s.years.mean()) / max(float(s.years.std()), 1e-9)
    delta = lenses._trend_delta(s, locus["scale"])
    off = lenses._offset(s)[rows]
    phi = s.phi[rows]
    fin = np.isfinite(phi) & (phi > 0)
    o = off.sum(0)
    inv = np.where(fin, off ** 2 / np.where(fin, phi, 1.0), 0.0).sum(0)
    phi_u = np.divide(o ** 2, inv, out=np.full(o.shape, np.inf), where=inv > 0)
    y = s.y[rows].sum(0)
    vague = lambda j: np.full(j, 1e-6)  # noqa: E731
    _, b, sd, _ = surprise.refit_place(y[None], o[None], phi_u[None], np.stack([np.ones_like(x), x], 1), tau=vague(2))
    fit, *_ = surprise.refit_place(y[None], o[None], phi_u[None], np.stack([x ** j for j in range(4)], 1), tau=vague(4))
    var = fit + np.where(np.isfinite(phi_u), fit ** 2 / np.where(np.isfinite(phi_u), phi_u, 1.0), 0.0)
    kappa = max(float(np.divide((y - fit[0]) ** 2, var[0], out=np.zeros_like(y), where=var[0] > 0).sum()
                      / max(len(x) - 4, 1)), 1.0)
    se = float(sd[0, 1]) * np.sqrt(kappa)
    if not se > 0:
        return {"tested": False, "reason": "no information"}
    z = (direction * float(b[0, 1]) - delta) / se
    return {"tested": True, "p": float(stats.t.sf(z, max(len(x) - 4, 1))), "effect": float(direction * b[0, 1] / delta),
            "beta": float(b[0, 1]), "se": se, "dispersion": kappa, "observed": float(y.sum())}


def test_spatial(s: surprise.Surprise, x: leads.Lead, select: np.ndarray, test: np.ndarray, alpha: float = 0.05
                 ) -> dict[str, Any]:
    """A claim about a unit (a state's or region's trend) on two disjoint sets of its places: the lens's statistic on
    ``select`` must reach ``alpha`` (the claim is carried by that half), and the p-value reported is the same
    statistic on ``test``, which took no part in it. Only a unit claim has places to split: a cluster or a
    municipality was itself chosen among the places."""
    _, direction = span_direction(x)
    a = test_trend_unit(s, {**x.locus, "places": [int(u) for u in select]}, direction)
    b = test_trend_unit(s, {**x.locus, "places": [int(u) for u in test]}, direction)
    if not (a["tested"] and b["tested"]):
        return {"tested": False, "reason": a.get("reason") or b.get("reason")}
    return {"tested": True, "p": b["p"], "p_select": a["p"], "selected": bool(a["p"] < alpha),
            "effect": b["effect"], "effect_select": a["effect"], "n_select": int(len(select)), "n_test": int(len(test))}


def test_lead(sp: surprise.Surprise, x: leads.Lead, level: str = "state") -> dict[str, Any]:
    """A lead tested on the later years of ``sp``."""
    _, direction = span_direction(x)
    return test_prospective(sp, x.estimand, {"places": x.locus.get("places", [])}, direction, level)


# ---------------------------------------------------------------------- size and power on negative-binomial worlds


def _tail(y, m, k, up=True):
    """P(Y >= y) (or <=) for NB(mean m, size k); Poisson where k is infinite."""
    if np.isfinite(k):
        n = k / (k + m)
        return stats.nbinom.sf(y - 1, k, n) if up else stats.nbinom.cdf(y, k, n)
    return stats.poisson.sf(y - 1, m) if up else stats.poisson.cdf(y, m)


def _world(rng, mu: np.ndarray, size: float, rho: float = 0.0) -> np.ndarray:
    """Counts [cells, years] with the cell's rate mu times a frailty of mean 1 and squared CV 1/size: independent
    gamma over years (rho = 0, exactly negative binomial), or log-normal AR(1) in time with correlation rho."""
    if not np.isfinite(size):
        return rng.poisson(mu).astype(float)
    if rho == 0:
        return rng.poisson(rng.gamma(size, mu / size)).astype(float)
    sig2 = np.log1p(1 / size)
    z = np.empty(mu.shape)
    z[:, 0] = rng.standard_normal(mu.shape[0])
    for t in range(1, mu.shape[1]):
        z[:, t] = rho * z[:, t - 1] + np.sqrt(1 - rho ** 2) * rng.standard_normal(mu.shape[0])
    return rng.poisson(mu * np.exp(np.sqrt(sig2) * z - sig2 / 2)).astype(float)


def simulate_temporal(level: float, size: float, theta: float = 1.0, kind: str = "null", rho: float = 0.0,
                      known: bool = False, cells: int = 20000, train: int = 10, held: int = 4, alpha_sel: float = 1e-3,
                      theta0: float = lenses.RATE_RATIO, seed_text: str = "temporal-sim-v1") -> dict[str, float]:
    """The later-years tier on worlds: cells of mean ``level`` per year, NB size ``size`` (frailty AR(1) in time with
    correlation ``rho``), ``train`` years to select on and ``held`` after. Selection is a scan of the windows of
    one to three years of the training years against ``theta0`` times the true mean, a cell selected when its best
    window reaches ``alpha_sel``; the test is `test_prospective`'s on the held years against ``theta0`` times
    the expectation (the true mean, or with ``known`` False the cell's own training mean, which absorbs part of
    the excursion that selected it). ``kind``: ``null``; ``persistent`` (x theta from year 4 on); ``recurring``
    (x theta in years 3, 6, 9, 12 ...); ``oneoff`` (x theta in year 4 only). Returns the cells selected and the
    share of them replicated at 0.05 (the size under ``null``, the power otherwise)."""
    rng = np.random.default_rng(config.seed(seed_text, level, size, theta, kind, rho))
    T = train + held
    boost = np.ones(T)
    if kind == "persistent":
        boost[3:] = theta
    elif kind == "recurring":
        boost[[2, 5, 8, 11][: max(1, (T - 1) // 3)]] = theta
    elif kind == "oneoff":
        boost[3] = theta
    mu = np.full((cells, T), float(level)) * boost[None, :]
    y = _world(rng, mu, size, rho)
    ytr = y[:, :train]
    c = np.concatenate([np.zeros((cells, 1)), np.cumsum(ytr, 1)], 1)
    best = np.ones(cells)
    for w in (1, 2, 3):
        Y = c[:, w:] - c[:, :-w]
        n = w * size if np.isfinite(size) else size
        p = _tail(Y, w * level * theta0, n)
        best = np.minimum(best, p.min(1))
    sel = best < alpha_sel
    if not sel.any():
        return {"selected": 0, "replicated": float("nan")}
    Yh = y[sel, train:].sum(1)
    base = np.full(sel.sum(), held * level) if known else ytr[sel].mean(1) * held
    n = held * size if np.isfinite(size) else size
    p = _tail(Yh, np.maximum(base * theta0, 1e-9), n)
    return {"selected": int(sel.sum()), "replicated": float((p < 0.05).mean())}


def simulate_sizes(level: float, size: float, cells: int = 200000, alpha_sel: float = 1e-3,
                   seed_text: str = "sizes-sim-v1") -> dict[str, float]:
    """The size after selection: cells NB(level, size), events dealt 50/50 to A and E, selected when side A's count
    reaches ``alpha_sel`` against A's expectation. The mean rate ratio of the selected cells on all the events, on
    side A, on side E, and the mean realised rate ratio (the cell's rate over its mean; 1 would be no selection)."""
    rng = np.random.default_rng(config.seed(seed_text, level, size))
    lam = rng.gamma(size, level / size, cells) if np.isfinite(size) else np.full(cells, float(level))
    y = rng.poisson(lam)
    ya = rng.binomial(y, 0.5)
    ye = y - ya
    sel = _tail(ya, np.full(cells, level / 2), size) < alpha_sel
    if not sel.any():
        return {"selected": 0}
    return {"selected": int(sel.sum()), "all_events": float(y[sel].mean() / level), "side_A": float(ya[sel].mean() / (level / 2)),
            "side_E": float(ye[sel].mean() / (level / 2)), "realised": float(lam[sel].mean() / level)}


def simulate_spatial(side: int = 14, size: float = 10.0, level: float = 200.0, shock: float = 0.0, range_: int = 0,
                     trend: float = 0.0, buffer: bool = True, units: int = 300, select: float = 0.05, years: int = 14,
                     slope_sd: float = 0.0, seed_text: str = "spatial-sim-v1") -> dict[str, float]:
    """The other-places tier on worlds: a unit of ``side`` x ``side`` municipalities on a lattice (rook neighbours;
    regions of 3 x 3), NB size ``size``, ``level`` events per cell-year, a log-linear course whose total change over
    the period is ``trend`` times the scale's minimum divergence (0: the null), and a year-by-year shock of sd
    ``shock`` (log scale) smooth over ``range_`` steps of the graph, so neighbours share it; ``slope_sd`` (in units of the divergence delta) adds a random log-linear slope per municipality that is smooth in the same way (neighbours share a trend). The unit is selected when its trend on
    one random half of the regions (buffered or not) reaches ``select``; the share of the selected units that
    replicate on the other half at 0.05 is reported."""
    rng = np.random.default_rng(config.seed(seed_text, side, size, level, shock, range_, trend, buffer, slope_sd))
    n = side * side
    ij = np.stack(np.meshgrid(np.arange(side), np.arange(side), indexing="ij"), -1).reshape(-1, 2)
    idx = np.arange(n).reshape(side, side)
    edges = np.concatenate([np.stack([idx[:, :-1].ravel(), idx[:, 1:].ravel()], 1),
                            np.stack([idx[:-1, :].ravel(), idx[1:, :].ravel()], 1)])
    region = (ij[:, 0] // 3) * 100 + ij[:, 1] // 3
    yrs = np.arange(2010, 2010 + years)
    x = (yrs - yrs.mean()) / yrs.std()
    delta = lenses._trend_delta(types.SimpleNamespace(years=yrs), "state")
    A = np.zeros((n, n))
    A[edges[:, 0], edges[:, 1]] = A[edges[:, 1], edges[:, 0]] = 1
    smooth = (A + np.eye(n)) / (A.sum(1) + 1)[:, None]
    smooth = np.linalg.matrix_power(smooth, range_) if range_ else np.eye(n)
    scale_sd = np.sqrt((smooth ** 2).sum(1))
    sel = hit = 0
    for _ in range(units):
        shocks = shock * (smooth @ rng.standard_normal((n, years))) / scale_sd[:, None] if shock else 0.0
        slopes = (slope_sd * delta * (smooth @ rng.standard_normal(n)) / scale_sd)[:, None] * x[None, :] if slope_sd else 0.0
        mu = np.broadcast_to(level * np.exp(trend * delta * x)[None, :], (n, years)) * np.exp(shocks + slopes)
        y = _world(rng, mu, size)
        s = types.SimpleNamespace(places=np.arange(n), years=yrs, y=y, phi=np.full((n, years), size),
                                  extras={"offset": np.full((n, years), float(level))})
        regs = sorted(set(region))
        pick = set(rng.permutation(len(regs))[: (len(regs) + 1) // 2].tolist())
        in1 = np.array([regs.index(r) in pick for r in region])
        if buffer:
            touch = np.zeros(n, dtype=bool)
            cross = in1[edges[:, 0]] != in1[edges[:, 1]]
            touch[edges[cross, 0]] = touch[edges[cross, 1]] = True
        else:
            touch = np.zeros(n, dtype=bool)
        h1, h2 = np.nonzero(in1 & ~touch)[0], np.nonzero(~in1 & ~touch)[0]
        d = 1 if trend >= 0 else -1
        a = test_trend_unit(s, {"places": h1, "scale": "state"}, d)
        if not a["tested"] or a["p"] >= select:
            continue
        sel += 1
        hit += test_trend_unit(s, {"places": h2, "scale": "state"}, d)["p"] < 0.05
    return {"selected": sel, "replicated": hit / sel if sel else float("nan")}


__all__ = ["SideExpectations", "SideModel", "deal", "honest_effect", "load_base", "match", "prepare", "relevel",
           "simulate_sizes", "simulate_spatial", "simulate_temporal", "span_direction", "spatial_split",
           "test_lead", "test_prospective", "test_spatial", "test_trend_unit"]
