"""Honest sample splitting (ARCHITECTURE §8.3): select on one part of the events, test on another.

Every cell's events are dealt by a fixed seed to three sides (`control.SIDES`): **A** (50%) fits the
expectation, explores and selects; **B** (30%) is the scheduled survey's one test of what A selected;
**R** (20%) is the confirmation reserve, spent by claims under LOND (`control.Reserve`). Side A's model is
a refit on A's events alone, so nothing B or R holds has touched the expectation or the selection; a
side's expected count is the A fit's times the ratio of the sides' fractions, and the negative-binomial
sizes carry over unchanged (thinning keeps them).

The sides share each cell's rate. Under a negative binomial the extra-Poisson variation of that rate is part
of the null, and it is seen in both sides: a cell selected on A for a chance excursion of its rate shows the
excursion in B too (a marginal test on B called every null cell at mu >= 100, size 10 "replicated").
The test on B is therefore conditional on A: given A's count the rate has a gamma posterior, and B's count is
the negative binomial of `conditional_p`, which is uniform under the null for any size and any selection on A.
What it asks is whether B exceeds what A's count and the model's own heterogeneity predict.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
from scipy import stats

from . import config, control, graphs, leads, monolith, store, surprise
from .scans import explain, lenses

RATIO = {"B": control.SIDES["B"] / control.SIDES["A"], "R": control.SIDES["R"] / control.SIDES["A"]}


# ---------------------------------------------------------------------- the sides of a block


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
    """Deal a block's events to the sides, fit the block on side A alone and store the fit. Without it the sides
    read the fit on all the events, scaled (`load_base`): the expectation of A then carries a little of B and R."""
    full, sides = deal(dataset, event, block, years)
    model = _a_model(full, sides["A"], graph, device)
    model.fit(outer=40, log=log)
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


# ---------------------------------------------------------------------- testing a lead on a side

THETA = {"outbreak": lenses.RATE_RATIO, "change_point": lenses.RATE_RATIO, "space_time": lenses.RATE_RATIO,
         "spatial_cluster": lenses.SPATIAL_RATE_RATIO}


def span_direction(x: leads.Lead) -> tuple[list[int] | None, int]:
    """A lead's years (first, last) and its direction: +1 up, -1 down, 0 a pattern."""
    span = x.locus.get("years")
    if x.estimand == "group_disparity":
        return span, 0
    if x.estimand == "space_time":
        return span, 1 if x.locus.get("direction") == "up" else -1
    size = np.log(max(x.effect, 1e-12)) if x.scale == "rate_ratio" else x.effect
    return span, int(np.sign(size))


def conditional_p(y_test: float, y_a: np.ndarray, mu0_a: np.ndarray, size: np.ndarray, ratio: float, up: bool = True
                  ) -> float:
    """P(Y_test >= y_test) (or <=) given the A counts of the same cells, under the null that a cell's rate is
    gamma(size, mean mu0) around the boundary mean ``mu0_a`` (on A's scale): the rate's posterior given y_a is
    gamma(size + y_a, size/mu0 + 1) in A's units, so the test side's count is a negative binomial of size
    size + y_a and mean ratio * (size + y_a) * mu0 / (size + mu0). Poisson cells (size infinite) are independent
    of A. The cells are summed by moment matching (`explain.tail_p`)."""
    fin = np.isfinite(size)
    k = np.where(fin, size, 1.0)
    n = np.where(fin, size + y_a, np.inf)
    m = ratio * np.where(fin, (k + y_a) * mu0_a / (k + mu0_a), mu0_a)
    return explain.tail_p(y_test, m, n, up=up)


def test_locus(s: surprise.Surprise, estimand: str, locus: dict[str, Any], direction: int, edges: np.ndarray | None = None,
               cache: dict | None = None, given: surprise.Surprise | None = None, ratio: float | None = None
               ) -> dict[str, Any]:
    """A fixed locus, tested on the events of the surprise's side: one-sided, against the lens's own minimum
    effect, the negative binomial of the cells given side A's counts (``given`` is A's surprise of the field,
    ``ratio`` the fraction of this side over A's; without ``given`` the test is marginal, and anti-conservative
    wherever the extra-Poisson variation matters). A trend is tested by the lens's own divergence statistic.
    ``{"tested": False}`` for a pattern without a direction."""
    if direction == 0:
        return {"tested": False, "reason": "no direction"}
    rows = np.nonzero(np.isin(s.places, locus.get("places", [])))[0]
    if rows.size == 0:
        return {"tested": False, "reason": "locus outside the grid"}
    if estimand == "trend_divergence":
        cache = cache if cache is not None else {}
        if "trend" not in cache:
            cache["trend"] = lenses.trend_scores(s, edges)
        diff, sd, delta, has = cache["trend"]
        r = int(rows[0])
        if not has[r] or sd[r] <= 0:
            return {"tested": False, "reason": "no neighbours"}
        z = (direction * diff[r] - delta) / sd[r]
        return {"tested": True, "p": float(stats.norm.sf(z)), "effect": float(direction * diff[r] / max(delta, 1e-12)),
                "divergence": float(diff[r])}
    span = locus.get("years") or [int(s.years[0]), int(s.years[-1])]
    cols = (s.years >= span[0]) & (s.years <= span[-1])
    sub = np.ix_(rows, np.nonzero(cols)[0])
    theta = THETA[estimand]
    scale = theta if direction > 0 else 1 / theta
    Y, M = float(s.y[sub].sum()), float(s.mu[sub].sum())
    if given is None:
        p = explain.tail_p(Y, s.mu[sub] * scale, s.phi[sub], up=direction > 0)
    else:
        p = conditional_p(Y, given.y[sub], given.mu[sub] * scale, given.phi[sub], ratio, up=direction > 0)
    return {"tested": True, "p": p, "effect": float((Y + 0.5) / (M + 0.5)), "observed": Y, "expected": M}


def test_lead(s: surprise.Surprise, x: leads.Lead, edges: np.ndarray | None = None, cache: dict | None = None,
              given: surprise.Surprise | None = None, ratio: float | None = None) -> dict[str, Any]:
    if x.estimand == "trend_divergence" and (leads.trend_reference(x) != "neighbours" or x.locus.get("scale")):
        return {"tested": False, "reason": "the trend test reads a municipality's contrast with its neighbours"}
    return test_locus(s, x.estimand, x.locus, span_direction(x)[1], edges, cache, given, ratio)


def match(x: leads.Lead, candidates: list[leads.Lead]) -> list[leads.Lead]:
    """The side-A leads that are the same finding as ``x``: the same direction, a place in common and, for a
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


def control_inflation(mu: np.ndarray, size: np.ndarray, alpha_a: float = 0.001, alpha_b: float = 0.05,
                      seed_text: str = "split-null-v1", draws: int = 20) -> dict[str, float]:
    """The false-replication rate of the test on B under the negative-binomial null: simulate cells NB(mu, size),
    deal them to A and B (the fractions of `control.SIDES`), select the cells whose A count is significant at
    ``alpha_a`` against A's expectation, and report the share whose B count is significant at ``alpha_b``,
    marginally and given A (`conditional_p`). Nominal: ``alpha_b``."""
    rng = np.random.default_rng(config.seed(seed_text))
    fa, fb = control.SIDES["A"], control.SIDES["B"]
    ratio = fb / fa
    sel = marginal = conditional = 0
    fin = np.isfinite(size)
    k = np.where(fin, size, 1.0)
    for _ in range(draws):
        gam = np.where(fin, rng.gamma(k, mu / k), mu)
        y = rng.poisson(gam)
        ya = rng.binomial(y, fa)
        yb = rng.binomial(y - ya, fb / (1 - fa))
        pa = np.where(fin, stats.nbinom.sf(ya - 1, k, k / (k + mu * fa)), stats.poisson.sf(ya - 1, mu * fa))
        pb = np.where(fin, stats.nbinom.sf(yb - 1, k, k / (k + mu * fb)), stats.poisson.sf(yb - 1, mu * fb))
        chosen = np.nonzero(pa < alpha_a)[0]
        sel += chosen.size
        marginal += int((pb[chosen] < alpha_b).sum())
        n = np.where(fin, k + ya, 1.0)[chosen]
        m = ratio * np.where(fin, (k + ya) * mu * fa / (k + mu * fa), mu * fa)[chosen]
        pc = np.where(fin[chosen], stats.nbinom.sf(yb[chosen] - 1, n, n / (n + m)), stats.poisson.sf(yb[chosen] - 1, m))
        conditional += int((pc < alpha_b).sum())
    return {"selected": sel, "marginal": marginal / sel if sel else float("nan"),
            "conditional": conditional / sel if sel else float("nan"), "nominal": alpha_b}


__all__ = ["SideExpectations", "SideModel", "conditional_p", "control_inflation", "deal", "load_base", "match", "prepare",
           "test_lead", "test_locus"]
