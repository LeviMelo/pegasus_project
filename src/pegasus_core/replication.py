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
* **other places** (`jurisdiction`, ADR-0019): for a claim about a predeclared unit, the other *jurisdictions*: a state
  claim must hold in other states (else its scope is one jurisdiction and it is not confirmed), a region claim in a random
  half of its states and without its most influential one, a municipality claim not be carried by its state. ADR-0015
  halved the unit's own municipalities, which share a coding regime, and so confirmed regimes as readily as mortality.
* **another record system** (`corroborate.py`): the same place and years in S2iD, SINAN or SIH.

The event sides survive for one thing: the *size* of an effect after selection. Given a cell's rate its sides
are independent Poisson counts, so the effect read on side E is unbiased for that rate whatever side A selected
(`honest_effect`). It includes the cell's own frailty; it is not evidence that the effect recurs.

`audit` reads a unit claim against how deaths are recorded and grades every recording explanation it raises
(`explain.GRADES`): only a ``tested`` one downgrades a claim. The simulations (`simulate_*`) measure each tier's and each
test's size and power on negative-binomial worlds.
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
        # the deal is a stored snapshot (its sides are the honest split's: re-dealing would mix A and E), so its cells
        # and carriers are read back with it, the sex restriction's groups included where the deal carries them
        return monolith.BlockData(dataset, event, block, arr["years"], arr["places"], meta["leaves"], meta["groups"],
                                  arr["leaf_group"], arr["N"], arr["e"], arr["u"], arr["t"], arr["g"], sum(sides.values()),
                                  meta.get("unallocated", {}), meta["key"], group_cells=arr.get("group_cells")), sides
    full = monolith.assemble(dataset, event, block, years)
    sides = {k: v.astype(float) for k, v in
             control.event_sides(full.y, f"event-sides-v1|{dataset}|{event}|{block}|{list(years)}").items()}
    store.put_arrays("split_sides", key,
                     {"years": full.years, "places": full.places, "leaf_group": full.leaf_group, "N": full.N, "e": full.e,
                      "u": full.u, "t": full.t, "g": full.g, **{f"y_{k}": v.astype(np.int32) for k, v in sides.items()},
                      **({} if full.group_cells is None else {"group_cells": full.group_cells})},
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
        for k, v in monolith._legacy_centring(arrays, meta).items():
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


def test_lead(sp: surprise.Surprise, x: leads.Lead, level: str = "state") -> dict[str, Any]:
    """A lead tested on the later years of ``sp``."""
    _, direction = span_direction(x)
    return test_prospective(sp, x.estimand, {"places": x.locus.get("places", [])}, direction, level)


# ---------------------------------------------------------------------- a unit claim, read against how deaths are recorded (ADR-0019)
#
# A unit claim (a state's or region's trend against the national course) replicates in later years and in the unit's
# other municipalities by the nature of a coding regime: a certifier's practice persists and serves the whole
# jurisdiction. `audit` therefore reads a claim against five things the tiers above cannot see, on direct
# standardisation (the year's observed national rate by sex x age, not the model's course), and **grades** every
# recording explanation it raises (`explain.GRADES`): only a ``tested`` one downgrades the claim.

CHAPTER_R = ("R00", "R99")
INTENT = ("Y10", "Y34")              # events of undetermined intent
WIDE_BLOCKS = (("V01", "V99"), ("W00", "W19"), ("W75", "W84"))   # blocks the ICD family holds too wide for siblings
AGE_CUTS = (0, 15, 30, 45, 60, 75)   # coarse ages of the profile cells
#: ICD-10 gives the intent chapters one mechanism list: an assault X85-Y09 and an event of undetermined intent
#: Y10-Y34 are the same mechanism at the same position (X93-X95 firearm / Y22-Y24, X99 sharp object / Y28 ...).
MECHANISMS = ((("X85", "X90"), ("Y10", "Y19")), (("X91", "X91"), ("Y20", "Y20")), (("X92", "X92"), ("Y21", "Y21")),
              (("X93", "X95"), ("Y22", "Y24")), (("X96", "X96"), ("Y25", "Y25")), (("X97", "X97"), ("Y26", "Y26")),
              (("X98", "X98"), ("Y27", "Y27")), (("X99", "X99"), ("Y28", "Y28")), (("Y00", "Y00"), ("Y29", "Y29")),
              (("Y01", "Y01"), ("Y30", "Y30")), (("Y02", "Y02"), ("Y31", "Y31")), (("Y03", "Y03"), ("Y32", "Y32")),
              (("Y04", "Y09"), ("Y33", "Y34")))
PLACES = {"0": 0, "4": 2, "8": 3, "9": 3, "": 3}      # fourth character of an external-cause code: home, street, other; the rest -> 1


def code_range(lo: str, hi: str, known) -> list[str]:
    return [c for c in known if lo <= c <= hi]


def node_codes(node: str, known) -> list[str]:
    """The 3-character categories a field covers (a node is a category or a range ``A00-A09``)."""
    if "-" in node:
        lo, hi = node.split("-")
        return code_range(lo, hi, known)
    return [node] if node in set(known) else []


def block_of(node: str, known, tree=None) -> list[str]:
    """The ICD-10 block that holds the node's siblings: V, W00-W19 and W75-W84 by `WIDE_BLOCKS`, else the node's
    family (`leads.family`: the outermost group below the chapter; the tree nests groups since 2026-10-06, and
    its parent would narrow the pool)."""
    first = (node_codes(node, known) or [node])[0]
    for lo, hi in WIDE_BLOCKS:
        if lo <= first <= hi:
            return code_range(lo, hi, known)
    from . import leads
    p = leads.family(node) if tree is None or node in tree.index else None
    return node_codes(p, known) if isinstance(p, str) and "-" in p and p != node else []


class Strata:
    """Deaths (or any event) by municipality, year, sex, age band and 4-character code, and the person-years by
    municipality, year, sex and band: everything direct standardisation and the profile of a set of deaths need.
    The expectation of a set of codes in a set of places is the year's national rate of each sex x age stratum, times the
    places' person-years there (`series`); it moves with the nation's course and with nothing else."""

    def __init__(self, events, pop, age_edges):
        import pandas as pd

        pop = pd.DataFrame(pop)
        ev = pd.DataFrame(events)
        self.places = np.sort(pop["u"].unique())
        self.years = np.sort(pop["year"].unique())
        sexes, bands = np.sort(pop["sex"].unique()), np.sort(pop["band"].unique())
        self.sexes, self.bands = sexes, bands
        U, T, S, B = len(self.places), len(self.years), len(sexes), len(bands)
        self.shape = (U, T, S, B)
        self.N = np.zeros(self.shape)
        np.add.at(self.N, (np.searchsorted(self.places, pop["u"].to_numpy()), np.searchsorted(self.years, pop["year"].to_numpy()),
                           np.searchsorted(sexes, pop["sex"].to_numpy()), np.searchsorted(bands, pop["band"].to_numpy())),
                  pop["n"].to_numpy(float))
        ev = ev[ev["u"].isin(self.places) & ev["year"].isin(self.years)]
        self.u = np.searchsorted(self.places, ev["u"].to_numpy()).astype(np.int32)
        self.t = np.searchsorted(self.years, ev["year"].to_numpy()).astype(np.int16)
        self.s = np.searchsorted(sexes, ev["sex"].to_numpy()).astype(np.int8)
        self.b = np.searchsorted(bands, ev["band"].to_numpy()).astype(np.int8)
        self.y = ev["y"].to_numpy(float)
        codes = ev["code"].astype(str)
        self.c3s = np.array(sorted(codes.str[:3].unique()))
        self.c3 = np.searchsorted(self.c3s, codes.str[:3].to_numpy()).astype(np.int16)
        self.place = codes.str[3:4].map(PLACES).fillna(1).to_numpy().astype(np.int8)    # place of occurrence of an external cause
        self.coarse_of_band = np.searchsorted(AGE_CUTS, bands, side="right") - 1
        self.age = self.coarse_of_band[self.b]
        self._rate: dict[tuple, np.ndarray] = {}

    @classmethod
    def from_gateway(cls, dataset: str, event: str, years: list[int], source: str = "popsvs", log=print) -> Strata:
        """Events and person-years from the gateway: bands are the population source's own age edges."""
        import duckdb
        import pandas as pd

        from . import gateway

        edges = np.array(gateway.age_edges(source))
        rows = []
        for y in years:
            con = duckdb.connect()
            con.register("c", gateway.event_counts(dataset, event, y).counts)
            rows.append(con.execute(f"""select u, year, sex, (select max(e) from unnest({edges.tolist()}) t(e)
                where e <= least(greatest(age, 0), 120))::smallint band, code, sum(y)::int y from c group by all""").fetchdf())
        con = duckdb.connect()
        con.register("p", gateway.population(list(years), source=source))
        pop = con.execute(f"""select u, year, sex, (select max(e) from unnest({edges.tolist()}) t(e)
            where e <= greatest(age, 0))::smallint band, sum(n) n from p group by all""").fetchdf()
        log(f"strata {dataset}.{event} {years[0]}-{years[-1]}: {sum(len(r) for r in rows)} event rows")
        return cls(pd.concat(rows), pop, edges)

    # ---- direct standardisation
    def _mask(self, c3set) -> np.ndarray:
        idx = np.searchsorted(self.c3s, sorted(c3set))
        idx = idx[(idx < len(self.c3s))]
        keep = np.isin(self.c3s[idx], list(c3set))
        return np.isin(self.c3, idx[keep])

    def national_rate(self, c3set) -> np.ndarray:
        """The year's national rate by sex x band of the codes: [T, S, B]."""
        key = tuple(sorted(c3set))
        if key not in self._rate:
            m = self._mask(c3set)
            nat = np.zeros(self.shape[1:])
            np.add.at(nat, (self.t[m], self.s[m], self.b[m]), self.y[m])
            self._rate[key] = nat / np.maximum(self.N.sum(0), 1e-300)
        return self._rate[key]

    def series_groups(self, group: np.ndarray, c3set, n_groups: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Observed and expected deaths [G, T] of the codes for groups of municipalities (``group``: a group index per
        municipality of `places`, -1 for none), the expectation from the year's national rates of each stratum."""
        G = int(group.max()) + 1 if n_groups is None else n_groups
        rate = self.national_rate(c3set)
        m = self._mask(c3set) & (group[self.u] >= 0)
        T = self.shape[1]
        Obs = np.bincount(group[self.u[m]].astype(np.int64) * T + self.t[m], weights=self.y[m], minlength=G * T).reshape(G, T)
        E = np.zeros((G, T))
        for g in range(G):
            E[g] = (self.N[group == g].sum(0) * rate).sum((1, 2))
        return Obs, E

    def series_codes(self, places, codes) -> tuple[np.ndarray, np.ndarray]:
        """Observed and expected deaths [C, T] of each 3-character category of ``codes`` in a set of places."""
        sel = np.isin(self.places, places)
        T = self.shape[1]
        idx = np.searchsorted(self.c3s, codes)
        pos = np.full(len(self.c3s), -1)
        pos[idx] = np.arange(len(codes))
        m = (pos[self.c3] >= 0) & sel[self.u]
        Obs = np.bincount(pos[self.c3[m]].astype(np.int64) * T + self.t[m], weights=self.y[m], minlength=len(codes) * T).reshape(len(codes), T)
        nat = np.zeros((len(codes), T, self.shape[2], self.shape[3]))
        mn = pos[self.c3] >= 0
        np.add.at(nat, (pos[self.c3[mn]], self.t[mn], self.s[mn], self.b[mn]), self.y[mn])
        rate = nat / np.maximum(self.N.sum(0), 1e-300)[None]
        E = (self.N[sel].sum(0)[None] * rate).sum((2, 3))
        return Obs, E

    def series(self, places, c3set) -> tuple[np.ndarray, np.ndarray]:
        """Observed and expected deaths over the years of the codes in a set of places."""
        group = np.where(np.isin(self.places, places), 0, -1)
        Obs, E = self.series_groups(group, c3set, 1)
        return Obs[0], E[0]

    # ---- cells of a profile
    def cells(self, places, c3set, dims: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
        """Observed and expected deaths [T, C] by cell: sex, coarse age and, as ``dims`` asks, the place of occurrence
        (the code's fourth character) and the mechanism (`MECHANISMS`). The expectation of a cell is the nation's rate
        there times the places' person-years of the sex and coarse age."""
        S, A = self.shape[2], len(AGE_CUTS)
        P = 4 if "place" in dims else 1
        M = len(MECHANISMS) + 1 if "mech" in dims else 1
        mech_of = np.full(len(self.c3s), M - 1)
        for i, (assault, undet) in enumerate(MECHANISMS):
            for lo, hi in (assault, undet):
                mech_of[(self.c3s >= lo) & (self.c3s <= hi)] = i
        place_of = self.place.astype(np.int64) if "place" in dims else 0
        cell = ((self.s.astype(np.int64) * A + self.age) * P + place_of) * M + (mech_of[self.c3] if "mech" in dims else 0)
        C = S * A * P * M
        m = self._mask(c3set)
        T = self.shape[1]
        nat = np.bincount(self.t[m].astype(np.int64) * C + cell[m], weights=self.y[m], minlength=T * C).reshape(T, C)
        inside = m & np.isin(self.u, np.nonzero(np.isin(self.places, places))[0])
        obs = np.bincount(self.t[inside].astype(np.int64) * C + cell[inside], weights=self.y[inside], minlength=T * C).reshape(T, C)
        pop_nat = np.zeros((T, S, A))
        pop_in = np.zeros((T, S, A))
        sel = np.isin(self.places, places)
        for b, a in enumerate(self.coarse_of_band):
            pop_nat[:, :, a] += self.N[:, :, :, b].sum(0)
            pop_in[:, :, a] += self.N[sel][:, :, :, b].sum(0)
        s_of = np.repeat(np.arange(S), A * P * M)
        a_of = np.tile(np.repeat(np.arange(A), P * M), S)
        exp = pop_in[:, s_of, a_of] * nat / np.maximum(pop_nat[:, s_of, a_of], 1e-300)
        return obs, exp


def _delta(scale: str, years) -> float:
    return lenses._trend_delta(types.SimpleNamespace(years=np.asarray(years)), scale)


def jurisdiction(st: Strata, places, scale: str, c3set, direction: int, years, seed_text: str = "jurisdiction-v1",
                 alpha: float = 0.05) -> dict[str, Any]:
    """The other places of a claim, halved by the unit that sets the coding regime (ADR-0019). A coding regime is a
    jurisdiction's practice: one certifier serves a state, so the state's own municipalities share it, and halving
    them (ADR-0015's spatial tier) confirms the regime as readily as a mortality change. The independent places are
    the other jurisdictions:

    * **state** claim: the same divergence from the nation's course, on the same codes, in the other states (direct
      standardisation, the lens's minimum divergence); it holds if more of them diverge the same way than chance
      allows (binomial at ``alpha`` over the states with 30 or more events). It is then not one state's: the claim is
      **re-scoped** to the states where it holds. If not, its scope is *one jurisdiction* and it gets no spatial
      confirmation: a coding regime, a real local change and a model misfit cannot be told apart by that unit.
    * **region** claim: the region's states halved at random (the claim must reach ``alpha`` on one half and replicate
      on the other) and the claim without its most influential state (it must keep half its slope), else re-scoped to that state.
    * **municipality** claim (read against its neighbours): the regime is its state's, so the state's other
      municipalities must not carry the divergence (same direction, half the slope, ``alpha``), else re-scoped to the state.
    """
    yrs = np.asarray(years)
    ok_years = np.isin(st.years, yrs)
    state_of = (st.places // 10000).astype(int)
    states = np.unique(state_of)
    own = np.unique(np.asarray(places, int) // 10000)
    dof = len(yrs) - 2

    def beta_of(group, n=None):
        Obs, E = st.series_groups(group, c3set, n)
        Obs, E = Obs[:, ok_years], E[:, ok_years]
        b, se = explain.loglinear(Obs, E, yrs)
        return Obs, b, se

    if scale == "state":
        group = np.searchsorted(states, state_of)
        Obs, b, se = beta_of(group)
        d = _delta("state", yrs)
        p = explain.slope_p(b, se, direction, d, dof)
        others = np.array([s not in own for s in states]) & (Obs.sum(1) >= 30) & np.isfinite(p)
        hit = others & (p < alpha) & (np.sign(b) == direction)
        n, k = int(others.sum()), int(hit.sum())
        pb = float(stats.binom.sf(k - 1, n, alpha)) if n else 1.0
        multi = bool(k >= 2 and pb < alpha)
        return {"unit": "state", "scope": "multi-state" if multi else "one jurisdiction", "ok": multi, "states_tested": n,
                "states_holding": [int(s) for s in states[hit]], "p_binomial": pb}
    if scale == "region":
        mine = np.array([s for s in states if s in set(own.tolist()) or s in set((np.asarray(places, int) // 10000).tolist())])
        if len(mine) < 4:
            return {"unit": "region", "scope": "region", "ok": False, "reason": "fewer than four states to halve"}
        rng = np.random.default_rng(config.seed(seed_text, *map(int, mine)))
        order = rng.permutation(len(mine))
        a, c = mine[order[: len(mine) // 2]], mine[order[len(mine) // 2:]]
        d = _delta("region", yrs)
        res = {}
        for name, half in (("select", a), ("test", c)):
            group = np.where(np.isin(state_of, half) & np.isin(st.places, places), 0, -1)
            _, b, se = beta_of(group, 1)
            res[name] = (float(b[0]), float(explain.slope_p(b, se, direction, d, dof)[0]))
        full_group = np.where(np.isin(st.places, places), 0, -1)
        _, bf, _ = beta_of(full_group, 1)
        worst, drop = 1.0, None
        for s in mine:
            group = np.where(np.isin(st.places, places) & (state_of != s), 0, -1)
            _, b, _ = beta_of(group, 1)
            kept = float(direction * b[0] / max(direction * bf[0], 1e-12))
            if kept < worst:
                worst, drop = kept, int(s)
        ok = bool(res["select"][1] < alpha and res["test"][1] < alpha and worst >= 0.5)
        return {"unit": "region", "scope": "region" if ok else (f"state {drop}" if worst < 0.5 else "region (not replicated)"),
                "ok": ok, "p_select": res["select"][1], "p_test": res["test"][1], "kept_without_top_state": worst, "top_state": drop}
    # municipality: the state's other municipalities
    st_of = np.unique(np.asarray(places, int) // 10000)
    group = np.where(np.isin(state_of, st_of) & ~np.isin(st.places, places), 0, -1)
    _, b, se = beta_of(group, 1)
    _, bm, _ = beta_of(np.where(np.isin(st.places, places), 0, -1), 1)
    p = float(explain.slope_p(b, se, direction, _delta("municipality", yrs), dof)[0])
    carried = bool(p < alpha and direction * b[0] >= 0.5 * direction * bm[0])
    return {"unit": "municipality", "scope": "state" if carried else "municipality", "ok": not carried, "p_state_rest": p,
            "state_rest_beta": float(b[0]), "beta": float(bm[0])}


def conserved_level(st: Strata, places, scale: str, node_set, codes, name: str, years, later_years=None,
                    seed_text: str = "rescope-v1") -> dict[str, Any]:
    """The claim lifted to the level where the total is conserved (the node and the pool that took its change: its ICD
    block, R00-R99, undetermined intent), re-tested with the full statistics of a unit claim: the slope of the pooled
    O/E on the observed national rate against the scale's minimum divergence (one-sided in the pooled direction, Student t),
    its size over the period, the later years' observed over expected, and the other jurisdictions
    (`jurisdiction`). The code-level shift stays reported beside it: a change of certification, informative on its own."""
    yrs = np.asarray(years)
    union = sorted(set(node_set) | set(codes))
    ok_years = np.isin(st.years, yrs)
    Obs, E = (a[ok_years] for a in st.series(places, union))
    b, se = explain.loglinear(Obs, E, yrs)
    d = int(np.sign(b[0])) or 1
    p = float(explain.slope_p(b, se, d, _delta(scale, yrs), len(yrs) - 2)[0])
    span = (yrs.max() - yrs.min()) / yrs.std()
    node_o = st.series(places, list(node_set))[0][ok_years].sum()
    out = {"level": name, "categories": len(union), "node_share_of_deaths": float(node_o / max(Obs.sum(), 1.0)), "beta": float(b[0]), "se": float(se[0]), "direction": d, "p": p,
           "ratio_over_period": float(np.exp(b[0] * span)), "ok": bool(p < 0.05)}
    if later_years is not None:
        Ol, El = st.series(places, union)
        late = np.isin(st.years, np.asarray(later_years))
        out["obs_exp_later"] = float(Ol[late].sum() / max(El[late].sum(), 1e-300))
    out["jurisdiction"] = jurisdiction(st, places, scale, union, d, yrs, seed_text)
    return out


def pool_exchange(node: tuple[np.ndarray, np.ndarray], Oc: np.ndarray, Ec: np.ndarray, years) -> tuple[dict[str, Any], np.ndarray]:
    """Does a pool (rows ``Oc``, ``Ec``: its codes) move against the node? Two readings, either of which counts: the pool's
    total (`explain.exchange`; a diffuse transfer) and the codes that move against the node (`explain.partners`; a transfer
    between a few codes, whose signal the rest of a large pool only dilutes). Returns the record (``moves``, ``via``,
    ``share``, ``bound``, ``pooled_beta``) and the mask of partner codes."""
    Obs, E = node
    whole = explain.exchange(node, (Oc.sum(0), Ec.sum(0)), years)
    bn = whole["node_per_year"]
    pick = explain.partners(bn, Oc, Ec, years)
    part = explain.exchange(node, (Oc[pick].sum(0), Ec[pick].sum(0)), years) if pick.any() else None
    use, via = (part, "partners") if part is not None and part["moves"] else (whole, "pool")
    return {**use, "moves": bool(use["moves"]), "via": via, "pool_share": whole["share"], "pool_z": whole["rest_z"],
            "pooled_beta": float(explain.loglinear(Obs + Oc.sum(0), E + Ec.sum(0), years)[0][0])}, pick


def audit(st: Strata, places, node: str, scale: str, beta_claim: float, direction: int, train_years, tree=None,
          seed_text: str = "audit-v1", later_years=None) -> dict[str, Any]:
    """A unit claim read against how deaths are recorded, every explanation graded (`explain.GRADES`).

    1. **National rate.** The slope of the node's Obs/E on the standardised years with the expectation from the year's
       *observed* national rate of each sex x age stratum (direct standardisation) must itself reach the lens's minimum
       divergence, in the claim's direction, with at least half the claim's size (`control.replicates`); the claim was
       selected against the model's national course, which a code whose national rate moves fast misses. A claim that
       fails is ``not_replicated``.
    2. **All-cause slope**, the mandatory column: the unit's all-cause slope (direct) and the share of the claim's slope it
       carries. A share of half or more is a completeness or denominator co-movement, graded ``bound``.
    3. **Conservation** inside an ICD family: the node pooled with the rest of its ICD block, with R00-R99 and (an
       external cause) with undetermined intent Y10-Y34, and with all of those. If a pool's rest moves the other way by at
       least half the node's change in excess deaths (`explain.exchange`) the totals are conserved: the claim may be a
       transfer between codes. That is a ``bound`` (at most that share, if every death the pool lost were the node's).
       It becomes ``tested`` when the displaced deaths are compared with the node's and the pool's own deaths in sex, age,
       place of occurrence and, between the intent chapters, mechanism (`explain.profile_test`): resembling the node's
       and not the pool's, it supports the recoding; resembling the pool's and not the node's, it excludes it.
    4. **Shape.** An abrupt one-year step against a gradual course (`explain.shape_test`): a step is classed
       administrative (``consistent``: a level shift is what a change of practice looks like, and a real shock too).
    5. **Jurisdiction** (`jurisdiction`): the unit that sets the regime, not the unit's own municipalities; its ``ok`` is
       the spatial confirmation of ADR-0019.

    6. **Re-scope** (`conserved_level`): where a pool took the change (not excluded by a test) the claim is lifted to the
       level where the total is conserved and re-tested there with the full statistics of a unit claim; the code-level shift
       stays reported beside it.

    The verdict: ``not_replicated``; ``rescoped`` (a tested explanation accounts for at least half the claim at the code
    level, and a conserved level stands: the family's epidemiology and the code's certification are both reported);
    ``explained`` (nothing remains at any conserved level); ``open`` (explanations remain, none tested against);
    ``survives`` (every explanation raised was excluded by a test, or none was raised). A lead is dropped only by
    ``not_replicated`` or ``explained``."""
    yrs = np.asarray(train_years)
    known = list(st.c3s)
    node_set = node_codes(node, known)
    out: dict[str, Any] = {"node": node, "scale": scale, "years": [int(yrs[0]), int(yrs[-1])]}
    ok_years = np.isin(st.years, yrs)
    Obs, E = (a[ok_years] for a in st.series(places, node_set))
    delta = _delta(scale, yrs)
    b, se = explain.loglinear(Obs, E, yrs)
    p = float(explain.slope_p(b, se, direction, delta, len(yrs) - 2)[0])
    out["national"] = {"beta": float(b[0]), "se": float(se[0]), "p": p, "claim_beta": float(beta_claim),
                       "attenuation": float(b[0] / beta_claim) if beta_claim else None,
                       "ok": bool(control.replicates(float(beta_claim), float(b[0]), p))}
    if later_years is not None:
        Ol, El = st.series(places, node_set)
        late = np.isin(st.years, np.asarray(later_years))
        out["national"]["obs_exp_later"] = float(Ol[late].sum() / max(El[late].sum(), 1e-300))
    Oa, Ea = (a[ok_years] for a in st.series(places, known))
    ba, sea = explain.loglinear(Oa, Ea, yrs)
    share = float(max(0.0, ba[0] / b[0])) if b[0] * ba[0] > 0 else 0.0
    out["all_cause"] = {"beta": float(ba[0]), "se": float(sea[0]), "share_of_claim": share}
    expl: list[dict[str, Any]] = []
    if share >= 0.5:
        expl.append({"kind": "completeness or denominator co-movement", "grade": explain.BOUND, "bound": min(1.0, share),
                     "assumption": "the unit's all-cause drift applies to the node in proportion", "outcome": "open"})
    sh = explain.shape_test(Obs, E, yrs)
    out["shape"] = {"shape": str(sh["shape"][0]), "gap": float(sh["gap"][0]), "year": int(sh["year"][0]), "jump": float(sh["jump"][0])}
    if out["shape"]["shape"] == "step":
        expl.append({"kind": "administrative step", "grade": explain.CONSISTENT, "bound": None,
                     "assumption": f"a level shift of x{out['shape']['jump']:.2g} between {out['shape']['year'] - 1} and "
                                   f"{out['shape']['year']} is what a change of practice looks like; a real shock too", "outcome": "open"})
    if node_set and CHAPTER_R[0] <= node_set[0] <= CHAPTER_R[1]:
        expl.append({"kind": "certification (the claim's subject is the ill-defined chapter)", "grade": explain.CONSISTENT,
                     "bound": None, "assumption": "a change in an R code is a change of what is certified as ill-defined", "outcome": "open"})
    # conservation
    block = [c for c in block_of(node, known, tree) if c not in node_set]
    rest_r = [c for c in code_range(*CHAPTER_R, known) if c not in node_set]
    external = bool(node_set) and "V" <= node_set[0][0] <= "Y" and not node_set[0].startswith("V")
    rest_y = [c for c in code_range(*INTENT, known) if c not in node_set] if external else []
    pools = {"block": block, "R00-R99": rest_r, "undetermined intent": rest_y}
    pools = {k: v for k, v in pools.items() if v}
    if len(pools) > 1:
        pools["all"] = sorted(set().union(*pools.values()))
    early, late_ = np.nonzero(ok_years)[0][:3], np.nonzero(ok_years)[0][-3:]
    cons = {}
    for name, rest in pools.items():
        if name == "all" and any(v["moves"] for v in cons.values()):
            continue                    # the union only looks for what no single pool showed
        Oc, Ec = (a[:, ok_years] for a in st.series_codes(places, rest))
        ex, pick = pool_exchange((Obs, E), Oc, Ec, yrs)
        if ex["moves"]:
            codes = [rest[i] for i in np.nonzero(pick)[0]] if ex["via"] == "partners" else rest
            use = ex
            ex["partners"] = {"codes": [rest[i] for i in np.nonzero(pick)[0]]}
            external_pair = external and name in ("undetermined intent", "all", "block")
            dims = (("place",) + (("mech",) if external_pair else ())) if external else ()
            node_o, node_e = st.cells(places, node_set, dims)
            rest_o, rest_e = st.cells(places, codes, dims)
            d_node = (node_o - node_e)[late_].sum(0) - (node_o - node_e)[early].sum(0)
            d_rest = (rest_o - rest_e)[late_].sum(0) - (rest_o - rest_e)[early].sum(0)
            moved = np.maximum(0.0, -np.sign(d_node.sum()) * d_rest)
            p_node = node_o[ok_years].sum(0) + 0.1
            p_rest = rest_o[early].sum(0) + 0.1
            pt = explain.profile_test(moved, p_node / p_node.sum(), p_rest / p_rest.sum(),
                                      config.seed(seed_text, node, name) % (2 ** 31))
            ex["profile"] = pt
            grade = explain.TESTED if pt["result"] in ("supports", "excluded") else explain.BOUND
            expl.append({"kind": f"transfer with {name}", "grade": grade, "bound": use["bound"],
                         "assumption": "every death the pool lost (gained) was a death of the node's",
                         "via": ex["via"], "outcome": {"supports": "supports", "excluded": "excluded"}.get(pt["result"], "open"),
                         "profile": pt["result"]})
        cons[name] = ex
    out["conservation"] = cons
    out["explanations"] = expl
    out["jurisdiction"] = jurisdiction(st, places, scale, node_set, direction, yrs, seed_text)
    # re-scope, never dissolve: where a pool took the change, the claim is lifted to the level where the total is conserved
    lifted = [(name, pools[name]) for name, ex in cons.items() if ex["moves"]
              and not any(e["kind"] == f"transfer with {name}" and e["outcome"] == "excluded" for e in expl)]
    if len(lifted) > 1:
        lifted.append(("all lifted pools", sorted(set().union(*(c for _, c in lifted)))))
    out["rescope"] = [conserved_level(st, places, scale, node_set, c, f"node + {n}", yrs, later_years, seed_text) for n, c in lifted]
    if not out["national"]["ok"]:
        verdict = "not_replicated"
    elif any(e["grade"] == explain.TESTED and e["outcome"] == "supports" and (e["bound"] or 1.0) >= 0.5 for e in expl):
        verdict = "rescoped" if any(r["ok"] for r in out["rescope"]) else "explained"
    elif any(e["outcome"] == "open" for e in expl):
        verdict = "open"
    else:
        verdict = "survives"
    out["verdict"] = verdict
    return out


# ---------------------------------------------------------------------- the artefact-aware tests on worlds


def _series_world(rng, level, size, kind, n, years=10, effect=0.3):
    """n series of ``years`` yearly counts around an expectation of ``level``: NB(size) frailty over a course ``kind``
    (``null``, ``linear``: log-linear with ``effect`` per standard deviation of the years, ``accelerating``: a quadratic log
    course with the same end-to-end change, ``step``: a one-year level shift of the same end-to-end change at a random year)."""
    t = np.arange(years)
    x = (t - t.mean()) / t.std()
    total = effect * (x[-1] - x[0])
    if kind == "null":
        course = np.zeros(years)
    elif kind == "linear":
        course = effect * x
    elif kind == "accelerating":
        course = total * (t / (years - 1)) ** 2
    else:
        course = np.zeros(years)
    mu = np.full((n, years), float(level)) * np.exp(course)[None, :]
    if kind == "step":
        k = rng.integers(3, years - 2, n)
        mu = mu * np.exp(total * (t[None, :] >= k[:, None]))
    return _world(rng, mu, size), np.full((n, years), float(level))


def simulate_shape(level: float = 200.0, size: float = 50.0, effect: float = 0.3, n: int = 400,
                   delta: float | None = None, seed_text: str = "shape-sim-v1") -> dict[str, dict[str, float]]:
    """The shape test on worlds: for each course (null, linear, accelerating, step) the shares of series called step,
    gradual and indeterminate. A gradual real trend must not be called a step (size), a step must (power)."""
    rng = np.random.default_rng(config.seed(seed_text, level, size, effect))
    yrs = np.arange(2010, 2020)
    out = {}
    for kind in ("null", "linear", "accelerating", "step"):
        Obs, E = _series_world(rng, level, size, kind, n, effect=effect)
        r = explain.shape_test(Obs, E, yrs, delta)["shape"]
        out[kind] = {c: float(np.mean(r == c)) for c in ("step", "gradual", "indeterminate")}
    return out


def simulate_exchange(level: float = 200.0, rest_level: float = 3000.0, size: float = 50.0, effect: float = 0.3,
                      codes: int = 10, n: int = 300, seed_text: str = "exchange-sim-v2") -> dict[str, float]:
    """Conservation on worlds: a node with a real log-linear course among a pool of ``codes`` stable codes (a real
    change: `pool_exchange` must not call a transfer, the size) and among a pool whose first two codes lose the node's
    gain death for death (a transfer: it must, the power)."""
    rng = np.random.default_rng(config.seed(seed_text, level, rest_level, size, effect, codes))
    yrs = np.arange(2010, 2020)
    Ob, E = _series_world(rng, level, size, "linear", n, effect=effect)
    gain = Ob - E
    false = found = 0
    for i in range(n):
        Rs, Re = _series_world(rng, rest_level / codes, size, "null", codes)
        Rt = Rs.copy()
        for c in range(min(2, codes)):
            Rt[c] = np.maximum(rng.poisson(np.maximum(Re[c] - gain[i] / min(2, codes), 1.0)).astype(float), 0.0)
        false += pool_exchange((Ob[i], E[i]), Rs, Re, yrs)[0]["moves"]
        found += pool_exchange((Ob[i], E[i]), Rt, Re, yrs)[0]["moves"]
    return {"false_transfer": false / n, "transfer_found": found / n}


def simulate_profile(cells: int = 24, n: int = 200, concentration: float = 0.5, draws: int = 300,
                     seed_text: str = "profile-sim-v1") -> dict[str, float]:
    """`explain.profile_test` on worlds: random node and pool profiles over ``cells`` cells (Dirichlet of
    ``concentration``); displaced deaths drawn from the node's profile (a recoding) or from the pool's (independent
    changes). The shares called ``supports``, ``excluded`` and ``open`` for each."""
    rng = np.random.default_rng(config.seed(seed_text, cells, n, concentration))
    res = {"recoding": [], "independent": []}
    for i in range(draws):
        pn, pr = rng.dirichlet(np.full(cells, concentration)) * 0.98 + 0.02 / cells, rng.dirichlet(np.full(cells, concentration)) * 0.98 + 0.02 / cells
        for kind, p in (("recoding", pn), ("independent", pr)):
            res[kind].append(explain.profile_test(rng.multinomial(n, p).astype(float), pn, pr, i, 1000)["result"])
    return {f"{k}_{r}": float(np.mean([x == r for x in v])) for k, v in res.items() for r in ("supports", "excluded", "open")}


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


__all__ = ["SideExpectations", "SideModel", "Strata", "audit", "block_of", "conserved_level", "deal", "honest_effect", "jurisdiction", "load_base",
           "match", "node_codes", "prepare", "relevel", "simulate_exchange", "simulate_profile", "simulate_shape",
           "simulate_sizes", "simulate_temporal", "span_direction", "test_lead", "test_prospective"]
