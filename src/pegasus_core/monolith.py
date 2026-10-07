"""The monolith: one hierarchical model of event intensities (ARCHITECTURE §4–§5).

For a block (one chapter of a classifier tree), leaves e (ICD categories),
places u, years t and groups g = sex × age band:

    y[e,u,t,g] ~ NegBin(μ, φ),   μ = N[u,t,g] · exp(η)
    η = b0 + θ_grp[p(e)] + θ_cat[e]                      levels along the tree
          + f_all[g] + f_grp[p(e), g]                     age–sex profiles (RW2 over age, per sex)
          + h_all[t] + h_grp[p(e), t]                     history (RW2 over years)
          + s_all[u] + v_all[u] + s_grp[p(e),u] + v_grp[p(e),u]   geography (scaled ICAR + iid: BYM)
          + Σ_r ψ[r,e] ω[r,u] τ[r,t]                      low-rank place × time interaction (``rank`` R > 0; §4.2, ADR-0021)

p(e) is the leaf's ICD group (the profile and geography level). Every effect
is centred along its structure; every strength τ is learned by Fellner–Schall
updates (Wood & Fasiolo 2017) with a block-diagonal Hessian. The mean is fitted
by penalised Poisson likelihood through the factorised sum (§5.1): no empty
cell is ever formed. φ is estimated afterwards by moments (§5.2).
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import hashlib
import inspect
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import scipy.sparse as sp
import torch
from scipy import optimize, special

from . import config, control, gateway, store, structures

AGE_EDGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]  # 18 bands; last is 80+
N_BANDS = len(AGE_EDGES)
TAU_BOUNDS = (1e-8, 1e8)
IX_SHARE = 1e-3                                # a leaf carries the interaction when it holds this share of the block's events
IX = ("ix_psi", "ix_os", "ix_ov", "ix_t")     # the interaction's parameters: ψ[R,E], ω = ix_os + ix_ov [R,U], τ [R,T]
HS = ("th_grp", "th_cat")    # the tree levels a horseshoe prior scales node by node (ARCHITECTURE §4.3)
# the parametrisation's centring, stored with every fit: 2 since 2026-10-06 (the age–sex profile over both sexes, the iid
# place effects uncentred); a fit stored without it is read through `_legacy_centring`
CENTRING = 2
SHRUNK = 1e3                 # a τ above this leaves its effect at a negligible size on a log-rate or logit scale (sd < 0.03;
                             # 1e5 until 2026-10-06); a model on another scale sets its own (`Monolith.shrunk`)


def age_band(age: np.ndarray, edges: list[int] | None = None) -> np.ndarray:
    return np.searchsorted(AGE_EDGES if edges is None else edges, age, side="right") - 1


# ---------------------------------------------------------------------- data


@dataclass
class BlockData:
    """Everything one block's fit needs, as dense arrays no larger than the population tensor."""

    dataset: str
    event: str
    block: str
    years: np.ndarray
    places: np.ndarray
    leaves: list[str]
    groups: list[str]
    leaf_group: np.ndarray            # index into groups, per leaf
    N: np.ndarray                     # [U, T, G] person-years, G = 2 sexes × bands (18 for POPSVS, 17 for the account)
    e: np.ndarray                     # non-empty cells: leaf, place, year, group, count
    u: np.ndarray
    t: np.ndarray
    g: np.ndarray
    y: np.ndarray
    unallocated: dict[str, int] = field(default_factory=dict)
    key: dict = field(default_factory=dict)
    n: np.ndarray | None = None       # marks: events per cell (y is then the mean of log m)
    l2: np.ndarray | None = None      # marks: Σ (log m)² per cell
    grain: str = "year"               # "year" | "month": the time axis t indexes years or months
    month_of_year: np.ndarray | None = None   # monthly grain: t -> 0..11
    S: np.ndarray | None = None       # [U, T, G] sd of log N where the population carries uncertainty (the account)
    population: str = "popsvs"
    group_cells: np.ndarray | None = None  # [groups, G] the age–sex cells each group can occur in (`_admissible`)
    group_outer: np.ndarray | None = None  # per group: its geography carrier (`assemble(geography=)`); None: itself
    outer_groups: list[str] | None = None  # the geography carriers' names

    def periods(self) -> np.ndarray:
        """The time axis as period codes: the years, or YYYYMM at the monthly grain."""
        if self.grain == "month":
            return (np.repeat(self.years, 12) * 100 + np.tile(np.arange(1, 13), len(self.years))).astype(np.int64)
        return self.years


# the readers of marks: each cell's accumulator states, the one whose mean is y, and (last) the second moment kept in l2
CELL_VALUES = {"mark": ("n", "l1", "l2"), "count": ("n", "s1", "s2"), "share": ("n", "k")}
CELL_MEAN = {"mark": "l1", "count": "s1", "share": "k"}
ASSEMBLY = 1    # bumped when what `_assemble` returns for the same inputs changes in a way the source hash cannot see
NEWBORN_SHARE = 0.5
# geography carriers holding less than this share of a block's events are pooled into one (`assemble(geo_pool=)`):
# held out on SIM 2022-23, I gained 0.47 per death and ran 2.3x faster, IV and XX lost under 0.001 (2026-10-06)
GEO_POOL = 0.01     # a field is a newborn-exposure field when at least this share of its events are at age 0


def _icd10_tree() -> tuple[dict, dict]:
    tree = gateway.code_structure("ICD10")
    code, parent, level = (tree.column(c).to_pylist() for c in ("code", "parent", "level"))
    return dict(zip(code, parent, strict=True)), dict(zip(code, level, strict=True))


@lru_cache(maxsize=64)
def _age0_share(dataset: str, event: str, block: str, years: tuple, data: str) -> float:
    """The share of the block's events (years given) recorded at age 0, from the gateway's cached counts."""
    parent_of, level_of = ({"*": None}, {"*": "category"}) if block == "*" else _icd10_tree()
    at0 = total = 0.0
    for year in years:
        tab = gateway.event_counts(dataset, event, int(year)).counts
        enc = pc.dictionary_encode(pc.utf8_slice_codeunits(tab.column("code").combine_chunks(), 0, 3)
                                   if block != "*" else tab.column("code").combine_chunks())
        ok = np.array([block == "*" or (level_of.get(c) == "category" and _chapter(c, parent_of) == block)
                       for c in enc.dictionary.to_pylist()], dtype=bool)
        keep = ok[enc.indices.to_numpy(zero_copy_only=False)]
        y, age = tab.column("y").to_numpy()[keep], tab.column("age").to_numpy()[keep]
        at0, total = at0 + float(y[age < 1].sum()), total + float(y.sum())
    return at0 / total if total else 0.0


def default_population(dataset: str, event: str, block: str, years: list[int], source: str = "events", race: str | None = None,
                       **_) -> str:
    """The exposure a field reads when none is named (and ``PEGASUS_POPULATION`` is unset): ``hybrid`` (POPSVS and
    the account's age 0) for a newborn-exposure field, defined by its data as a block of which at least
    ``NEWBORN_SHARE`` of the events are at age 0 (SIM chapter XVI: 0.9; chapter IX: 0.002), else ``popsvs``
    (ADR-0010 amended). Only event counts are classified; code-list and mark readers keep POPSVS."""
    if race is not None:      # a race group: the account's race slice; a death's recorded race through the infant matrix (ADR-0020)
        return "account-3+confusion" if dataset == "SIM.DO" else "account-3"
    if source != "events":
        return "popsvs"
    return "hybrid" if _age0_share(dataset, event, block, tuple(years), config.data_version()) >= NEWBORN_SHARE else "popsvs"


def assemble(dataset: str, event: str, block: str, years: range | list[int], profile: str = "block",
             source: str = "events", grain: str = "year", population: str | None = None, cache: bool = True,
             geography: str | None = "group", geo_pool: float = GEO_POOL, **source_args) -> BlockData:
    """One block's cells and populations, from the gateway, memoised in the store (kind ``blockdata``).

    The 10.7 M cells of SIH chapter X monthly took 467 s to assemble, and every variant of a fit (train and
    full, a rolling origin, a split, another exposure) re-read them. The entry is addressed by everything the
    assembly reads: its arguments, the data version, the population's key *and its content hash*, the
    assembly code (the hash of `_assemble`'s and `gateway`'s source, and `ASSEMBLY`), so a changed input or
    a changed reader is a different address and a stale entry is never served. The confirmation reserve is
    checked before the cache is read. ``cache=False`` assembles afresh and stores nothing."""
    control.check_reserved(dataset, years)
    if block == "*":
        profile, geography = "group", None          # no classifier tree: one leaf, nothing to carry
    if not cache:
        return _assemble(dataset, event, block, years, profile, source, grain, population, geography, geo_pool,
                         **source_args)
    ys = np.array(sorted(set(years)))
    population = population or config.population_pinned() or default_population(
        dataset, event, block, ys.tolist(), source, **source_args)
    pop = gateway.population(ys.tolist(), source=population, dataset=dataset, race=source_args.get("race"))
    h = hashlib.sha256()
    for name in pop.column_names:
        h.update(np.ascontiguousarray(pop.column(name).to_numpy()).tobytes())
    key = {"what": "blockdata", "dataset": dataset, "event": event, "block": block, "years": ys.tolist(),
           "profile": profile, "geography": geography, **({"geo_pool": geo_pool} if geo_pool else {}),
           "source": source, "grain": grain, "args": source_args,
           "data": config.data_version(),
           **gateway.population_key(population), "population_hash": h.hexdigest()[:16], "assembly": _assembly_code(),
           **({} if block == "*" else {"tree": config.resource_version("code_trees.parquet"),
                                       "attributes": config.resource_version("code_attributes.parquet")})}
    arrays, meta = store.get_arrays("blockdata", key), store.manifest("blockdata", key)
    if arrays is not None and meta is not None:
        return _blockdata_from(arrays, meta)
    data = _assemble(dataset, event, block, years, profile, source, grain, population, geography, geo_pool, **source_args)
    store.put_arrays("blockdata", key, *_blockdata_to(data))
    return data


@functools.cache
def _assembly_code() -> str:
    """The hash of the code a BlockData is a function of: the assembly and the gateway's readers."""
    h = hashlib.sha256(str(ASSEMBLY).encode())
    for fn in (_assemble, _index_of, age_band, _chapter, _carrier, _admissible):
        h.update(inspect.getsource(fn).encode())
    h.update(Path(gateway.__file__).read_bytes())
    return h.hexdigest()[:16]


def _blockdata_to(d: BlockData) -> tuple[dict[str, np.ndarray], dict]:
    month = d.grain == "month"
    arrays = {"years": d.years, "places": d.places, "leaf_group": d.leaf_group, "y": d.y,
              "N": d.N[:, ::12] if month else d.N,       # the monthly grain repeats each year's twelfth 12 times
              "e": d.e.astype(np.int32), "u": d.u.astype(np.int32), "t": d.t.astype(np.int32), "g": d.g.astype(np.int16)}
    if d.S is not None:
        arrays["S"] = d.S[:, ::12] if month else d.S
    if d.n is not None:
        arrays["n"], arrays["l2"] = d.n, d.l2
    if d.group_cells is not None:
        arrays["group_cells"] = d.group_cells
    if d.group_outer is not None:
        arrays["group_outer"] = d.group_outer
    meta = {"dataset": d.dataset, "event": d.event, "block": d.block, "leaves": d.leaves, "groups": d.groups,
            "unallocated": d.unallocated, "data_key": d.key, "grain": d.grain, "population": d.population,
            **({} if d.outer_groups is None else {"outer_groups": d.outer_groups})}
    return arrays, meta


def _blockdata_from(a: dict[str, np.ndarray], m: dict) -> BlockData:
    month = m["grain"] == "month"
    N, S = a["N"], a.get("S")
    if month:
        N = np.repeat(N, 12, axis=1)
        S = None if S is None else np.repeat(S, 12, axis=1)
    d = BlockData(m["dataset"], m["event"], m["block"], a["years"], a["places"], m["leaves"], m["groups"],
                  a["leaf_group"], N, a["e"].astype(np.int64), a["u"].astype(np.int64), a["t"].astype(np.int64),
                  a["g"].astype(np.int64), a["y"], m["unallocated"], m["data_key"], S=S, population=m["population"])
    if "n" in a:
        d.n, d.l2 = a["n"], a["l2"]
    if "group_cells" in a:
        d.group_cells = a["group_cells"].astype(bool)
    if "group_outer" in a:
        d.group_outer, d.outer_groups = a["group_outer"], m["outer_groups"]
    if month:
        d.grain = "month"
        d.month_of_year = np.tile(np.arange(12), len(d.years))
    return d


def _assemble(dataset: str, event: str, block: str, years: range | list[int], profile: str = "block",
              source: str = "events", grain: str = "year", population: str | None = None, geography: str | None = "group",
              geo_pool: float = GEO_POOL, **source_args) -> BlockData:
    """One block's cells and populations, from the gateway.

    ``block`` is an ICD-10 chapter, or ``*`` for an event type without a classifier tree.
    ``profile`` is the tree level that carries the levels and the age–sex profiles: ``group`` (the outermost ICD group
    under the chapter, pooling its categories: C00-C97, all malignant neoplasms), ``block`` (the innermost group,
    C51-C58: ICD-10 groups nest, pegasus_data's tree since 2026-10-06) or ``category`` (each category its own).
    ``geography`` is the level that carries history and the place effects (h, s, v and season by group), a level at
    or above ``profile`` (None: the same; ``chapter``: one for the block): each profile carrier lies in one.
    ``geo_pool`` > 0 pools the geography carriers holding less than that share of the block's events into one (their
    place effects are shrunk to nothing, and each costs two unknowns at every place).
    ``source`` chooses the gateway reader, each giving cells of (u, year, sex, age, code):

        events       counts of the event type (y)
        code_list    counts of events under each category of a code-list column, e.g.
                     SINASC's CODANOMAL (``column=``); the exposure is still the population
        mark         accumulator states of a numeric mark (``mark=``, ``bounds=``,
                     ``classifier=``, ``casemix=``, ``facility_effects=``): n, l1 = Σ log m, l2 = Σ (log m)²; y is l1/n
        count        the same reader, a count-valued mark: n, s1 = Σ m, s2 = Σ m²; y is s1/n
        share        a binary mark (``indicator=``, ``success=``, ``classifier=``): n, k; y is k/n, l2 is k
    """
    control.check_reserved(dataset, years)      # the confirmation reserve is read by claims only (ARCHITECTURE §8.3)
    years = np.array(sorted(set(years)))
    population = population or config.population_pinned() or default_population(
        dataset, event, block, years.tolist(), source, **source_args)
    edges = gateway.age_edges(population)   # the population source fixes the age bands (never padded or split)
    nB = len(edges)
    pop = gateway.population(years.tolist(), source=population, dataset=dataset, race=source_args.get("race"))
    places = np.array(sorted(pop.column("u").unique().to_pylist()))
    tidx = {int(y): i for i, y in enumerate(years)}
    N = np.zeros((len(places), len(years), 2 * nB))
    pu = _index_of(places, pop.column("u").to_numpy())
    pt = _index_of(years, pop.column("year").to_numpy())
    pg = (pop.column("sex").to_numpy().astype(int) - 1) * nB + age_band(pop.column("age").to_numpy(), edges)
    np.add.at(N, (pu, pt, pg), pop.column("n").to_numpy())
    S = None
    if "s" in pop.column_names:
        S = np.zeros_like(N)
        S[pu, pt, pg] = pop.column("s").to_numpy()

    strata = gateway._strata(dataset)
    if strata["sex"] is None:
        # the subject has one sex by definition (a mother): the other sex is not exposed
        N[:, :, (2 - strata["implied_sex"]) * nB:(3 - strata["implied_sex"]) * nB] = 0.0

    if block == "*":
        # an event type without a classifier tree: one leaf, every event in it
        parent_of, level_of = {"*": None}, {"*": "category"}
    else:
        parent_of, level_of = _icd10_tree()
    categories = (["*"] if block == "*" else
                  sorted(c for c, lv in level_of.items() if lv == "category" and _chapter(c, parent_of) == block))
    if profile not in ("group", "block", "category"):
        raise ValueError(f"profile {profile!r}: group, block or category")
    carrier = {c: _carrier(c, profile, parent_of, level_of) for c in categories}
    # admissibility (ARCHITECTURE §3.3): a category occurs only in the age–sex cells its sex restriction and its absolute
    # age limits allow (`_admissible`). Its carrier's profile would otherwise give it the carrier's sex ratio and ages
    # (the group-profile fit of II expected 53 % of cervical-cancer deaths in men, 2026-10-06): a carrier whose
    # categories differ in admissibility is split by it, and each group's exposure is zero outside its cells
    # (`Monolith._prof`). For an underlying cause, the codes that cannot be one are not leaves at all
    underlying = dataset == "SIM.DO" and source == "events"
    # the restrictions are on the coded person's sex and age: they apply only where the population's strata are that
    # person's. SINASC's strata are the mother's (her sex implied by pegasus_data's roles) while CODANOMAL codes the
    # birth: applied there, male-only anomaly classes had no exposure and the fit's start was NaN (2026-10-06)
    own_strata = gateway.strata(dataset)["implied_sex"] is None
    adm, never = ({}, set()) if block == "*" or not own_strata else _admissible(edges, underlying)
    never = never & set(categories)
    every = (np.ones(2 * nB, dtype=bool), "")
    cls = {c: adm.get(c, every) for c in categories}
    categories = [c for c in categories if c not in never]
    carrier = {c: carrier[c] for c in categories}
    mixed = {k for k in set(carrier.values()) if len({cls[c][0].tobytes() for c in categories if carrier[c] == k}) > 1}
    carrier = {c: (f"{k}|{cls[c][1]}" if k in mixed and cls[c][1] else k) for c, k in carrier.items()}
    groups = sorted(set(carrier.values()))
    group_cells = np.array([next(cls[c][0] for c in categories if carrier[c] == k) for k in groups])
    exposed = N.sum(axis=(0, 1)) > 0                                     # the age–sex cells the population holds
    empty = [g for g, cells in zip(groups, group_cells, strict=True) if not (cells & exposed).any()]
    if empty:
        raise ValueError(f"{dataset} {block}: groups {empty} have no admissible cell the population holds "
                         "(a restriction applied to the wrong person, or a population without the group's sex or ages)")
    group_outer = outer_groups = None
    if geography is not None and geography != profile:
        if geography not in ("chapter", "group", "block", "category"):
            raise ValueError(f"geography {geography!r}: chapter, group, block or category")
        outer_of = {}
        for c in categories:
            o = block if geography == "chapter" else _carrier(c, geography, parent_of, level_of)
            if outer_of.setdefault(carrier[c], o) != o:
                raise ValueError(f"geography {geography!r} is finer than profile {profile!r}: {carrier[c]} spans two")
        outer_groups = sorted(set(outer_of.values()))
        group_outer = np.array([outer_groups.index(outer_of[k]) for k in groups], dtype=np.int64)
    gidx = {g: i for i, g in enumerate(groups)}
    eidx = {c: i for i, c in enumerate(categories)}
    values = CELL_VALUES.get(source, ("y",))
    weight = "n" if source in CELL_VALUES else "y"
    readers = {"events": gateway.event_counts, "code_list": gateway.code_list_counts, "mark": gateway.mark_moments,
               "count": gateway.mark_moments, "share": gateway.share_moments}
    if grain == "month":
        if source not in ("events", "code_list"):
            raise NotImplementedError("the monthly grain reads event counts and code-list counts")
        readers["events"] = gateway.monthly_counts
        # a code-list column (SINASC's CODANOMAL) by month: each event once under each category it carries
        readers["code_list"] = lambda ds, ev, year, places=None, column=None: gateway.monthly_counts(
            ds, ev, year, classifier=column, places=places, code_list=True)
        # person-months: each month carries a twelfth of the year's person-years
        N = np.repeat(N, 12, axis=1) / 12.0
        S = None if S is None else np.repeat(S, 12, axis=1)
    T = N.shape[1]

    parts, unallocated = [], {}
    for year in years:
        ec = readers[source](dataset, event, int(year), places=pa.array(places, pa.int32()), **source_args)
        tab = ec.counts
        # the codes are few and the rows many: decide once per distinct code, then index
        enc = pc.dictionary_encode(tab.column("code").combine_chunks() if block == "*" else
                                   pc.utf8_slice_codeunits(tab.column("code").combine_chunks(), 0, 3))
        cats = enc.dictionary.to_pylist()
        row_code = enc.indices.to_numpy(zero_copy_only=False)
        in_block = np.array([c in eidx for c in cats], dtype=bool)[row_code]
        other = ~in_block & np.array([level_of.get(c) is None for c in cats], dtype=bool)[row_code]
        if never:
            # a code that cannot be an underlying cause (an asterisk code; the release's rule): counted, not modelled
            bad = np.array([c in never for c in cats], dtype=bool)[row_code]
            unallocated["not an underlying cause"] = unallocated.get("not an underlying cause", 0) + int(
                tab.column(weight).to_numpy()[bad].sum())
        unallocated["code not in ICD-10 tree"] = unallocated.get("code not in ICD-10 tree", 0) + int(
            tab.column(weight).to_numpy()[other].sum())
        for r in ec.unallocated.to_pylist():
            if block == "*" or _chapter(str(r["code"] or "")[:3], parent_of) == block:
                unallocated[r["reason"]] = unallocated.get(r["reason"], 0) + int(r["y"])
        if grain == "month":
            # the event's own (year, month), which may fall outside the publication year
            ym = (tab.column("year").to_numpy().astype(np.int64) - int(years[0])) * 12 \
                + tab.column("month").to_numpy().astype(np.int64) - 1
            inside = (ym >= 0) & (ym < T)
            unallocated["date outside the period"] = unallocated.get("date outside the period", 0) + int(
                tab.column(weight).to_numpy()[in_block & ~inside].sum())
            in_block = in_block & inside
        sub = tab.filter(pa.array(in_block))
        time_index = (ym[in_block] if grain == "month" else np.full(sub.num_rows, tidx[int(year)], dtype=np.int64))
        parts.append((np.array([eidx.get(c, -1) for c in cats], dtype=np.int64)[row_code[in_block]],
                      _index_of(places, sub.column("u").to_numpy()),
                      time_index.astype(np.int64),
                      ((sub.column("sex").to_numpy().astype(np.int64) - 1) * nB
                       + age_band(sub.column("age").to_numpy(), edges)).astype(np.int64),
                      *(sub.column(v).to_numpy().astype(np.float64) for v in values)))
    e, u, t, g, *vals = (np.concatenate(z) for z in zip(*parts, strict=True))
    if len(e) == 0:
        raise LookupError(f"{dataset} {event}: block {block} has no events in {years[0]}–{years[-1]} "
                          f"(unallocated: {unallocated})")
    # several subcategories share a category, several ages a band: sum them into one cell
    flat = ((e * len(places) + u) * T + t) * (2 * nB) + g
    uniq, inv = np.unique(flat, return_inverse=True)
    sums = {v: np.bincount(inv, weights=x) for v, x in zip(values, vals, strict=True)}
    g = uniq % (2 * nB)
    rest = uniq // (2 * nB)
    t, rest = rest % T, rest // T
    u, e = rest % len(places), rest // len(places)
    key = {"dataset": dataset, "event": event, "block": block, "years": years.tolist(),
           "data": config.data_version(), **gateway.population_key(population),
           **({} if profile == "group" else {"profile": profile}),
           **({} if source == "events" else {"source": source, **source_args}),
           **({} if grain == "year" else {"grain": grain}),
           **({"admissible": 2} if not group_cells.all() or never else {}),
           **({} if group_outer is None else {"geography": geography})}
    y = sums[CELL_MEAN[source]] / sums["n"] if source in CELL_VALUES else sums["y"]
    lg = np.array([gidx[carrier[c]] for c in categories])
    excluded = ~group_cells[lg[e], g]
    if excluded.any():
        # records in a cell the code excludes (a man's cervical cancer, a newborn's senility): impossible as recorded,
        # so not modelled, and counted by reason, never dropped silently (ARCHITECTURE §3.3)
        w = (sums["n"] if source in CELL_VALUES else y)
        sex_ok = group_cells.reshape(len(groups), 2, nB).any(axis=2)[lg[e], g // nB]
        for reason, sel in (("sex the code excludes", excluded & ~sex_ok), ("age the code excludes", excluded & sex_ok)):
            if sel.any():
                unallocated[reason] = unallocated.get(reason, 0) + int(w[sel].sum())
        keep = ~excluded
        e, u, t, g, y = e[keep], u[keep], t[keep], g[keep], y[keep]
        sums = {v: x[keep] for v, x in sums.items()}
    live = N[u, t, g] > 0
    if not live.all():
        # events in a cell the population holds nobody in (the account's interval-free zeros: 1 death in 14 years of IX):
        # no rate exists there, so they are counted as unallocated, never given a guessed denominator
        w = (sums["n"] if source in CELL_VALUES else y)[~live]
        unallocated["no population in the cell"] = unallocated.get("no population in the cell", 0) + int(w.sum())
        e, u, t, g, y = e[live], u[live], t[live], g[live], y[live]
        sums = {v: x[live] for v, x in sums.items()}
    if geo_pool and group_outer is not None:
        w = sums["n"] if source in CELL_VALUES else y
        lg_e = np.array([gidx[carrier[c]] for c in categories])[e]
        share = np.bincount(group_outer[lg_e], weights=w, minlength=len(outer_groups)) / max(float(w.sum()), 1e-300)
        small = share < geo_pool
        if small.sum() >= 2:
            keep_o = [o for o in range(len(outer_groups)) if not small[o]]
            remap = {o: i for i, o in enumerate(keep_o)}
            pooled = len(keep_o)
            group_outer = np.array([remap.get(int(o), pooled) for o in group_outer], dtype=np.int64)
            outer_groups = [outer_groups[o] for o in keep_o] + ["(pooled)"]
            key = {**key, "geo_pool": geo_pool}            # only where pooling happens: other blocks keep their keys
    data = BlockData(dataset, event, block, years, places, categories, groups,
                     np.array([gidx[carrier[c]] for c in categories]), N, e, u, t, g, y, unallocated, key,
                     S=S, population=population, group_cells=None if group_cells.all() else group_cells,
                     group_outer=group_outer, outer_groups=outer_groups)
    if source in CELL_VALUES:
        data.n, data.l2 = sums["n"], sums[CELL_VALUES[source][-1]]   # share: l2 is k, the successes (y is k/n)
    if grain == "month":
        data.grain = "month"
        data.month_of_year = np.tile(np.arange(12), len(years))
    return data


def _index_of(sorted_values: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Position of each value in a sorted array of distinct values; a value the array lacks raises."""
    values = np.asarray(values).astype(sorted_values.dtype, copy=False)
    pos = np.searchsorted(sorted_values, values)
    if len(values) and (pos.max() >= len(sorted_values) or (sorted_values[pos] != values).any()):
        raise KeyError(f"{int((sorted_values[np.minimum(pos, len(sorted_values) - 1)] != values).sum())} values "
                       "outside the index")
    return pos.astype(np.int64)


def _admissible(edges: list[int], underlying: bool) -> tuple[dict[str, tuple[np.ndarray, str]], set[str]]:
    """The age–sex cells each ICD-10 category can occur in, from pegasus_data's `code_attributes`: its sex restriction
    (the release's RESTRSEXO, or NCHS Part 11 Table G's absolute sex edit; the two never contradict) and Table G's
    absolute age limits. A band is excluded only when it lies wholly outside the allowed ages (``edges``: the bands'
    lower edges, the last open). Conditional edits (highly improbable, not impossible) are not zeros. Returns
    {category: (allowed cells [2·bands], a short tag)} for the restricted ones and, for an underlying cause
    (``underlying``), the categories that cannot be one (the release's rule: asterisk codes, chapters XIX and XXI)."""
    a = gateway.code_attributes("ICD10")
    cols = {c: a.column(c).to_pylist() for c in ("code", "level", "sex", "nchs_sex", "nchs_sex_edit", "nchs_age_from",
                                                 "nchs_age_to", "nchs_age_edit", "underlying_cause")}
    lo = np.asarray(edges, dtype=float)
    hi = np.r_[lo[1:], np.inf]
    nB = len(lo)
    out, never = {}, set()
    for i, code in enumerate(cols["code"]):
        if cols["level"][i] != "category":
            continue
        if underlying and not cols["underlying_cause"][i]:
            never.add(code)
            continue
        sex = cols["sex"][i] or (cols["nchs_sex"][i] if cols["nchs_sex_edit"][i] == "absolute" else None)
        cell = np.ones(2 * nB, dtype=bool)
        tag = sex or ""
        if sex == "M":
            cell[nB:] = False
        elif sex == "F":
            cell[:nB] = False
        if cols["nchs_age_edit"][i] == "absolute":
            a0 = cols["nchs_age_from"][i] or 0.0
            a1 = cols["nchs_age_to"][i] if cols["nchs_age_to"][i] is not None else np.inf
            ok = (hi > a0) & (lo < a1)
            if not ok.all():
                cell &= np.tile(ok, 2)
                tag += f"{lo[ok][0]:g}-{hi[ok][-1]:g}".replace("-inf", "+")
        if not cell.all():
            out[code] = (cell, tag)
    return out, never


def _carrier(code: str, profile: str, parent_of: dict[str, str | None], level_of: dict[str, str]) -> str:
    """The node that carries a category's profile: itself (``category``), its innermost group (``block``), or the
    outermost group below its chapter (``group``)."""
    node = parent_of.get(code)
    if profile == "category" or node is None or level_of.get(node) != "group":
        return code
    while profile == "group" and level_of.get(parent_of.get(node)) == "group":
        node = parent_of[node]
    return node


def _chapter(code: str, parent_of: dict[str, str | None]) -> str | None:
    """The root (chapter) above a code, or None for a code the tree does not hold."""
    if code not in parent_of:
        return None
    node = code
    while parent_of.get(node) is not None:
        node = parent_of[node]  # type: ignore[assignment]
    return node


# ---------------------------------------------------------------------- model


@dataclass
class Component:
    name: str
    shape: structures.Shape     # precision along the structured (last) axis
    batch: int                  # leading dimension (1 when shared by the block)
    tau: float = 1.0
    free: float = 1.0           # share of the batch's dimensions left free by constraints across rows
    fixed: bool = False         # τ identifies the model and is not learned (the interaction's ψ and τ(t))

    @property
    def rank(self) -> float:
        """The effective rank: the shape's rank per row, less the dimensions that centring
        across rows removes (across groups: 1/nGrp of them; within groups: nGrp/nE)."""
        return self.shape.rank * self.batch * self.free


class Monolith:
    shrunk = SHRUNK              # the strength past which an effect has shrunk away (on this model's linear predictor)
    """One block's fitted model."""

    def __init__(self, data: BlockData, graph: tuple[np.ndarray, np.ndarray], graph_kind: str,
                 device: str = "cpu", rank: int = 0, prior: str = "gaussian", likelihood: str = "poisson"):
        if prior not in ("gaussian", "horseshoe"):
            raise ValueError(f"tree prior {prior!r}: gaussian or horseshoe")
        if likelihood not in ("poisson", "nb"):
            raise ValueError(f"likelihood {likelihood!r}: poisson or nb")
        if likelihood == "nb" and rank:
            raise NotImplementedError("the negative binomial mean fit does not carry the low-rank interaction")
        # the mean's likelihood: Poisson quasi-likelihood (consistent for μ, φ estimated after; ARCHITECTURE §5.2) or the
        # negative binomial itself, φ re-estimated every outer (`phi_fit`), so the strengths' LAML reads the
        # overdispersion as such and not as place variation (OPEN_QUESTIONS 8)
        self.likelihood = likelihood
        self.phi_fit = float("inf")
        self.hc: torch.Tensor | None = None     # each category's own time course [E, T], `fit_category_courses`
        self.off: torch.Tensor | None = None    # N2: each leaf-place-period's log offset v/2 [E, U, T], `laplace.marginal`
        self.data = data
        self.prior = prior          # the tree levels' prior: iid Gaussian per level, or the horseshoe (`_update_horseshoe`)
        self.rank = int(rank)       # R, the components of the place × time interaction (0: none); `_enable_interaction` adds them
        self.ix_on = False
        self.graph_kind = graph_kind
        self.graph = graph
        self.device = torch.device(device)
        self.dtype = torch.float64
        nU, nT, nG = data.N.shape
        nE, nGrp = len(data.leaves), len(data.groups)
        icar = self._icar = _cached_icar(graph[0], graph[1], nU)
        self.nB = nG // 2                      # age bands per sex (the population source's)
        rw_age = structures.random_walk(self.nB, order=2)
        rw_t = structures.random_walk(nT, order=2 if nT >= 4 else 1)
        # age–sex cells with no exposure anywhere in the block (a mother's male cells) carry no profile: fixed at zero,
        # and the profiles centred over the exposed cells only. Centred over both sexes, the unexposed sex's level was
        # a flat direction tied to b0 (the births' solve read b0 to 4 %, 2026-10-06)
        # a group's admissible cells (`BlockData.group_cells`): its exposure is zero outside them (`_emask`). Its
        # profile is fixed at zero only on a whole sex it cannot occur in (`_smask`); excluded ages inside an allowed
        # sex keep their profile entries, which no data reach and the RW2 extends smoothly, so the penalty neither
        # bends the allowed ages toward a forced zero nor changes rank
        cells = np.ones((nGrp, nG), dtype=bool) if data.group_cells is None else np.asarray(data.group_cells, dtype=bool)
        rows_k = cells.reshape(nGrp, 2, self.nB).any(axis=2)
        smask = np.repeat(rows_k, self.nB, axis=1).astype(float)
        exposed = (data.N.sum(axis=(0, 1)) > 0) & smask.any(axis=0)
        smask = smask * exposed[None, :]
        emask = cells * exposed[None, :]
        self._gmask = torch.as_tensor(exposed, dtype=self.dtype, device=self.device)
        self._smask = torch.as_tensor(smask, dtype=self.dtype, device=self.device) if not rows_k.all() else None
        self._emask = torch.as_tensor(emask, dtype=self.dtype, device=self.device) if not cells.all() else None
        rows = float(exposed.reshape(2, -1).any(axis=1).sum()) / 2
        f_free = (nGrp - 1) / nGrp * rows
        self._fproj = None
        if self._emask is not None:
            # f_grp's centring on an incomplete groups × cells table: the residual of the additive (group + cell) fit
            # over the admissible cells, the orthogonal projection onto profiles centred within each group and across
            # the groups at each cell (on a complete table, the double centring below). The excluded ages of an allowed
            # sex are left as they are (`fidx`): no data and no constraint reach them, the RW2 alone. Centred over the
            # whole sex rows instead, the zeros there were read as data and shifted every group's profile at those
            # ages (SIM IV started at 2.7 times its optimum, 2026-10-06)
            idx = np.flatnonzero(emask.reshape(-1))
            fidx = np.flatnonzero((smask > 0).reshape(-1) & ~(emask > 0).reshape(-1))
            kk, gg = np.divmod(idx, nG)
            A = np.zeros((len(idx), nGrp + nG))
            A[np.arange(len(idx)), kk] = 1.0
            A[np.arange(len(idx)), nGrp + gg] = 1.0
            P = np.eye(len(idx)) - A @ np.linalg.pinv(A)
            self._fproj = (torch.as_tensor(idx, device=self.device), torch.as_tensor(P, dtype=self.dtype, device=self.device),
                           torch.as_tensor(fidx, device=self.device))
            sex_rows = smask.reshape(nGrp, 2, self.nB).any(axis=2)
            f_free = float(sex_rows.sum() - sex_rows.any(axis=0).sum()) / (2 * nGrp)
        # history and the place effects by geography carrier (`BlockData.group_outer`), the profile and levels by group
        outer = np.arange(nGrp) if data.group_outer is None else np.asarray(data.group_outer, dtype=np.int64)
        nOut = int(outer.max()) + 1
        self.outer = torch.as_tensor(outer, device=self.device)
        self.components = {
            "th_grp": Component("th_grp", structures.iid(nGrp), 1),
            "th_cat": Component("th_cat", _within_groups(data.leaf_group, nE), 1),
            "f_all": Component("f_all", rw_age, 2, free=rows),
            "f_grp": Component("f_grp", rw_age, nGrp * 2, free=f_free),
            "h_all": Component("h_all", rw_t, 1),
            "h_grp": Component("h_grp", rw_t, nOut, free=(nOut - 1) / nOut),
            "s_all": Component("s_all", icar, 1),
            "v_all": Component("v_all", structures.iid(nU, centred=False), 1),
            "s_grp": Component("s_grp", icar, nOut, free=(nOut - 1) / nOut),
            "v_grp": Component("v_grp", structures.iid(nU, centred=False), nOut, free=(nOut - 1) / nOut),
            "v_cat": Component("v_cat", structures.iid(nU, centred=False), nE, free=(nE - nGrp) / nE),
        }
        if data.grain == "month":
            season = structures.random_walk(12, order=2, cyclic=True)
            self.components["c_all"] = Component("c_all", season, 1)
            self.components["c_grp"] = Component("c_grp", season, nOut, free=(nOut - 1) / nOut)
        self.params = {"b0": torch.zeros(1, dtype=self.dtype, device=self.device, requires_grad=True)}
        for c in self.components.values():
            self.params[c.name] = torch.zeros((c.batch, c.shape.Q.shape[0]), dtype=self.dtype,
                                              device=self.device, requires_grad=True)
        self._Q = {c.name: _torch_sparse(c.shape.Q, self.dtype, self.device) for c in self.components.values()}
        self._labels = {c.name: torch.as_tensor(c.shape.components if c.shape.components is not None
                                                else np.zeros(c.shape.Q.shape[0], dtype=int), device=self.device)
                        for c in self.components.values()}
        t = lambda a, dt=torch.int64: torch.as_tensor(a, dtype=dt, device=self.device)  # noqa: E731
        self.N = t(data.N, self.dtype)
        self.logN_nnz = torch.log(t(data.N[data.u, data.t, data.g], self.dtype))
        self.e, self.u, self.tt, self.g = t(data.e), t(data.u), t(data.t), t(data.g)
        self.y = t(data.y, self.dtype)
        self.grp = t(data.leaf_group)
        cells_g = np.count_nonzero(data.N > 0, axis=(0, 1))
        self.n_cells = float(nE * cells_g.sum() if self._emask is None else (emask[data.leaf_group] @ cells_g).sum())
        self.phi: float = float("inf")
        self.forcing = 0.5               # the largest relative residual CG stops at (Eisenstat–Walker cap)
        self.newton_log: list[tuple] = []   # per Newton step: objective, gradient norm, CG iterations, step length, decrease
        self.supply: np.ndarray | None = None   # [U, T] facility-supply multiplier of the expectation (facility.attach_supply)
        self.history: list[dict] = []
        self.trace_log: list[tuple] = []
        self.p_e = self.grp[self.e]
        self.moy = torch.as_tensor(data.month_of_year if data.grain == "month" else np.zeros(nT, dtype=np.int64),
                                   dtype=torch.int64, device=self.device)
        self.scale = float(data.y.sum())
        self._sufficient_statistics()

    def _sufficient_statistics(self) -> None:
        """η is linear in the effects, so Σ_c y_c η_c = Σ_effects ⟨x, Y_x⟩ with Y_x the counts summed
        over each effect's index. Computed once, the Poisson log-likelihood never touches the
        non-empty cells again: an evaluation costs the factorised total only (ARCHITECTURE §5.1)."""
        d = self.data
        nE, nGrp, (nU, nT, nG) = len(d.leaves), len(d.groups), d.N.shape
        pe = d.leaf_group[d.e]
        po = self.outer.cpu().numpy()[pe]
        nOut = int(self.outer.max()) + 1
        y = d.y

        def acc(shape: tuple[int, ...], *index: np.ndarray) -> torch.Tensor:
            out = np.zeros(shape)
            np.add.at(out, index, y)
            return torch.as_tensor(out, dtype=self.dtype, device=self.device)

        zero = np.zeros(len(y), dtype=np.int64)
        self.Y = {
            "b0": torch.as_tensor([float(y.sum())], dtype=self.dtype, device=self.device),
            "th_grp": acc((1, nGrp), zero, pe), "th_cat": acc((1, nE), zero, d.e),
            "f_all": acc((1, nG), zero, d.g), "f_grp": acc((nGrp, nG), pe, d.g),
            "h_all": acc((1, nT), zero, d.t), "h_grp": acc((nOut, nT), po, d.t),
            "s_all": acc((1, nU), zero, d.u), "v_all": acc((1, nU), zero, d.u),
            "s_grp": acc((nOut, nU), po, d.u), "v_grp": acc((nOut, nU), po, d.u),
            "v_cat": acc((nE, nU), d.e, d.u),
        }
        if d.grain == "month":
            moy = d.month_of_year[d.t]
            self.Y["c_all"] = acc((1, 12), zero, moy)
            self.Y["c_grp"] = acc((nOut, 12), po, moy)
        self.y_offset = float(np.sum(y * np.log(d.N[d.u, d.t, d.g])))   # Σ y log N, constant

    # ---- the low-rank interaction (ARCHITECTURE §4.2, ADR-0021) ------------------

    def _enable_interaction(self, active: np.ndarray | None = None) -> None:
        """Add the R components of Σ_r ψ[r,e] ω[r,u] τ[r,t] to the parameters (all zero: `_init_interaction` or a warm
        start sets them). The interaction acts on the *active* leaves, those holding at least ``IX_SHARE`` of the
        block's events (``active``: a given set, for a model over other years that must read a fit's parameters);
        the others have ψ = 0, which keeps the cube at |E_active|·U·T cells. The identifiability is by the priors and
        two constraints: ψ (the leaf loadings, N(0, 1)) is centred within each group's active leaves, so the
        interaction is orthogonal to the effects they share (level, the group's place and history effects); ω is a
        scaled ICAR plus an iid part, both centred over the places, with learned strengths (the amplitude lives
        there); τ is a random walk of order 1 scaled like the other shapes plus a unit prior on its level, with a
        fixed strength. A fixed ψ and τ leave ω the one free scale of each product, so the three factors' scales are
        not a ridge of the likelihood."""
        if self.ix_on:
            return
        d = self.data
        if d.grain == "month":
            raise NotImplementedError("the low-rank interaction is built for the annual grain")
        nU, nT, _ = d.N.shape
        nE, R = len(d.leaves), self.rank
        if active is None:
            totals = np.bincount(d.e, weights=d.y, minlength=nE)
            active = np.nonzero(totals >= IX_SHARE * totals.sum())[0]
        self.ixl = torch.as_tensor(np.asarray(active, dtype=np.int64), device=self.device)
        pos = np.full(nE, -1, dtype=np.int64)
        pos[np.asarray(active)] = np.arange(len(active))
        self.ixpos = torch.as_tensor(pos, device=self.device)
        self.ixp = self.ixpos[self.e]                                  # per non-empty cell: its leaf's position, -1 if inactive
        # ψ is centred within each geography carrier's active leaves: the place and history effects the term must be
        # orthogonal to are the carrier's
        groups = np.unique(self.outer.cpu().numpy()[d.leaf_group[np.asarray(active)]], return_inverse=True)[1]
        rw = structures.random_walk(nT, order=1)
        level = structures.Shape("rw1+level", (rw.Q + sp.csr_matrix(np.ones((nT, nT)) / nT)).tocsr(), nT, centred=False)
        self.components.update({
            "ix_psi": Component("ix_psi", _within_groups(groups, len(active)), R, fixed=True),
            "ix_os": Component("ix_os", self._icar, R),
            "ix_ov": Component("ix_ov", structures.iid(nU), R),
            "ix_t": Component("ix_t", level, R, fixed=True),
        })
        for name in IX:
            c = self.components[name]
            self.params[name] = torch.zeros((c.batch, c.shape.Q.shape[0]), dtype=self.dtype, device=self.device,
                                            requires_grad=True)
            self._Q[name] = _torch_sparse(c.shape.Q, self.dtype, self.device)
            self._labels[name] = torch.as_tensor(c.shape.components if c.shape.components is not None
                                                 else np.zeros(c.shape.Q.shape[0], dtype=int), device=self.device)
        self.ix_on = True

    @property
    def Y3(self) -> torch.Tensor:
        """[E_active, U, T] events of the active leaves summed over the groups: the interaction's sufficient
        statistic (Σ y·I = ⟨Y3, I⟩)."""
        if getattr(self, "_Y3", None) is None:
            d = self.data
            out = np.zeros((len(self.ixl), *d.N.shape[:2]))
            pos = self.ixpos.cpu().numpy()[d.e]
            keep = pos >= 0
            np.add.at(out, (pos[keep], d.u[keep], d.t[keep]), d.y[keep])
            self._Y3 = torch.as_tensor(out, dtype=self.dtype, device=self.device)
        return self._Y3

    @staticmethod
    def _om(x: dict[str, torch.Tensor]) -> torch.Tensor:
        return x["ix_os"] + x["ix_ov"]

    def _I(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[E_active, U, T]: the interaction Σ_r ψ[r,e] ω[r,u] τ[r,t] in η of the active leaves."""
        return self._product(x["ix_psi"], self._om(x), x["ix_t"])

    @staticmethod
    def _product(psi: torch.Tensor, om: torch.Tensor, tm: torch.Tensor) -> torch.Tensor:
        """Σ_r ψ[r,e] ω[r,u] τ[r,t] as one matrix product, [E, U, T]."""
        R, U, T = psi.shape[0], om.shape[1], tm.shape[1]
        return (psi.T @ (om[:, :, None] * tm[:, None, :]).reshape(R, U * T)).reshape(psi.shape[1], U, T)

    def _I_of(self, x: dict[str, torch.Tensor], leaves: torch.Tensor) -> torch.Tensor:
        """[|leaves|, U, T]: the interaction of any leaves (zero for an inactive one)."""
        pos = self.ixpos[leaves]
        act = pos >= 0
        out = torch.zeros((len(leaves), self.N.shape[0], self.N.shape[1]), dtype=self.dtype, device=self.device)
        if bool(act.any()):
            out[act] = self._product(x["ix_psi"][:, pos[act]], self._om(x), x["ix_t"])
        return out

    def _cells(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[E_active, U, T] expected events μ of the active leaves summed over the groups (the factorisation of §5.1
        with the leaf's own slab: O(E_active·U·T·R))."""
        pt = self._place_time(x)                                          # [K, U, T]
        return self._leaf_place(x)[self.ixl][:, :, None] * torch.exp(self._I(x)) * pt[self.grp[self.ixl]]

    def _offset(self, sel=None) -> torch.Tensor | None:
        """[n, U, T] the log factor the leaves ``sel`` (None: all; an int: one leaf, [U, T]) carry beyond the effects:
        the category courses (`fit_category_courses`, over periods) and N2's variance correction (`laplace.marginal`,
        per leaf-place-period). None when neither is set."""
        if self.hc is None and self.off is None:
            return None
        U, T = self.N.shape[:2]
        pick = (lambda a: a) if sel is None else (lambda a: a[sel])
        out = pick(self.off) if self.off is not None else None
        if self.hc is not None:
            h = pick(self.hc)
            h = h[None, :] if h.dim() == 1 else h[:, None, :]
            out = h.expand(*((U, T) if h.dim() == 2 else (h.shape[0], U, T))) if out is None else out + h
        return out

    @contextlib.contextmanager
    def without_offset(self):
        """The model with N2's offset removed, for evaluating a posterior draw of the effects: a draw η carries its
        own uncertainty, and its mean is e^η, not e^(η + v/2)."""
        saved, self.off = self.off, None
        try:
            yield self
        finally:
            self.off = saved

    def leaf_factor(self, x: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor] | None:
        """The leaves whose place-time factor is their own, and its log [A, U, T]: the interaction's active leaves
        (I) and, when the category courses are set (`fit_category_courses`), every leaf (its h_cat over periods).
        None when neither is on. The solver's active-leaf path and Λ read this one factor."""
        if not self.ix_on and self.hc is None and self.off is None:
            return None
        if self.hc is None and self.off is None:
            return self.ixl, self._I(x)
        act = torch.arange(len(self.data.leaves), device=self.device)
        logf = self._offset().clone()
        if self.ix_on:
            logf[self.ixl] = logf[self.ixl] + self._I(x)
        return act, logf

    def _ix_correction(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """Λ's change from the leaf-specific factors (`leaf_factor`): Σ over their leaves' cells of μ₀ (e^F − 1)."""
        lf = self.leaf_factor(x)
        if lf is None:
            return torch.zeros((), dtype=self.dtype, device=self.device)
        act, logf = lf
        pt = self._place_time(x)
        return (self._leaf_place(x)[act][:, :, None] * torch.expm1(logf) * pt[self.grp[act]]).sum()

    def _init_interaction(self, ridge: float = 1.0, sweeps: int = 12) -> None:
        """Starting values of the interaction from the base fit's residual cube (a zero start is a saddle).
        Each component is a rank-one fit of (Y3 − S) by weighted least squares with weights S (the Poisson
        working residual (y − μ)/μ weighted by μ, so no cell is divided by a tiny μ), by alternating
        closed-form updates with the unit ridge of ψ's prior, deflated component by component; ψ is
        centred within groups, ω over the places, and ω carries the amplitude."""
        with torch.no_grad():
            x = self.effects()
            S = self._cells({**x, **{k: torch.zeros_like(v) for k, v in x.items() if k.startswith("ix_")}})
            num = self.Y3 - S
            gen = torch.Generator().manual_seed(config.seed("ix_init", self.data.block, self.rank))
            nE, nU, nT = S.shape
            places = torch.zeros(nU, dtype=torch.int64, device=self.device)
            for r in range(self.rank):
                om = _centre(torch.randn((1, nU), generator=gen, dtype=self.dtype).to(self.device), places)[0]
                tm = torch.randn(nT, generator=gen, dtype=self.dtype).to(self.device)
                for _ in range(sweeps):
                    psi = _centre((torch.einsum("eut,u,t->e", num, om, tm)
                                   / (torch.einsum("eut,u,t->e", S, om ** 2, tm ** 2) + ridge))[None], self._labels["ix_psi"])[0]
                    psi = psi / psi.pow(2).mean().sqrt().clamp_min(1e-12)
                    om = _centre((torch.einsum("eut,e,t->u", num, psi, tm)
                                  / (torch.einsum("eut,e,t->u", S, psi ** 2, tm ** 2) + ridge))[None], places)[0]
                    tm = torch.einsum("eut,e,u->t", num, psi, om) / (torch.einsum("eut,e,u->t", S, psi ** 2, om ** 2) + ridge)
                    tm = tm / tm.pow(2).mean().sqrt().clamp_min(1e-12)
                self.params["ix_psi"][r].copy_(psi)
                self.params["ix_t"][r].copy_(tm)
                # the component's scale by the model's own objective (ω carries it; the term is linear in ω): the least
                # squares' ratio (y − μ)/μ is unbounded where μ is tiny, and on a sparse block (XIII) it gave ω = 32 and
                # an interaction of 438 on the log scale, whose Hessian (10²⁰⁶) no factorisation survives (2026-10-06)
                best, best_a = float("inf"), 0.0
                for a in (0.0, 0.01, 0.03, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0):
                    self.params["ix_ov"][r].copy_(a * om)
                    obj = float(self.objective())
                    if np.isfinite(obj) and obj < best:
                        best, best_a = obj, a
                om = best_a * om
                self.params["ix_ov"][r].copy_(om)
                num = num - S * psi[:, None, None] * om[None, :, None] * tm[None, None, :]

    # ---- effects (centred) -------------------------------------------------

    def effects(self, params: dict[str, torch.Tensor] | None = None) -> dict[str, torch.Tensor]:
        """The centred effects of ``params`` (default: the fitted ones). The map is linear (the interaction's
        factors apart), which the Laplace approximation uses (``laplace.py``)."""
        params = self.params if params is None else params
        out = {"b0": params["b0"]}
        for name in self.components:
            out[name] = self._centred(name, params[name])
        nGrp = len(self.data.groups)
        out["f_all"] = out["f_all"].reshape(1, 2 * self.nB)
        out["f_grp"] = out["f_grp"].reshape(nGrp, 2 * self.nB)
        return out

    def _centred(self, name: str, raw: torch.Tensor) -> torch.Tensor:
        """One component's centring (linear): along its structure's components, then group deviations summing to zero
        across groups and a leaf's place effect centred within its group. `effects` and the v1 solver's projectors
        (`solver.StructuredNewton`) both read it."""
        if name == "f_all":
            # the age profile is centred over both sexes together, not within each: the sex difference is a direction
            # of the RW2's null space the data inform. Centred within each sex, no component carried it, and IX's
            # youngest bands were fitted 0.57-0.77x and 1.4-3.0x observed in the two sexes (2026-10-06)
            mask = self._gmask.reshape(raw.shape)
            return (raw - (raw * mask).sum() / mask.sum()) * mask
        if name == "f_grp" and self._fproj is not None:
            idx, P, fidx = self._fproj
            out = torch.zeros(raw.numel(), dtype=raw.dtype, device=raw.device)
            out = out.index_put((idx,), P @ raw.reshape(-1)[idx]).index_put((fidx,), raw.reshape(-1)[fidx])
            return out.reshape(raw.shape)
        if name == "f_grp":
            mask = self._gmask[None, :]
            v = raw.reshape(-1, 2 * self.nB)
            v = (v - (v * mask).sum(dim=1, keepdim=True) / mask.sum()) * mask    # each group over the exposed age–sex cells
            return (v - v.mean(dim=0, keepdim=True)).reshape(raw.shape)  # across groups (f_all's)
        v = _centre(raw, self._labels[name]) if self.components[name].shape.centred else raw
        if name in ("h_grp", "s_grp", "v_grp", "c_grp"):
            v = v - v.mean(dim=0, keepdim=True)
        elif name == "v_cat":
            v = _centre(v.T.contiguous(), self.grp).T
        return v

    def _prof(self, x: dict[str, torch.Tensor], power: float = 1.0) -> torch.Tensor:
        """[groups, G] exp(f_all + f_grp)^power, zero in the cells a sex-restricted group has no exposure in."""
        p = torch.exp(power * (x["f_all"] + x["f_grp"]))
        return p if self._emask is None else p * self._emask

    def _place_time(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """[groups, U, T] of exp(h + g) · M: the factor every leaf of a group shares."""
        M = torch.einsum("utg,kg->kut", self.N, self._prof(x))
        lin = self._time(x)[:, None, :]
        if spatial:
            lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + self._grp_place(x)[:, :, None]
        return torch.exp(lin) * M

    def _time(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[groups, T]: history (h), plus season (c) at monthly grain, by group."""
        lin = x["h_all"][0][None, :] + x["h_grp"][self.outer]
        if "c_all" in x:
            lin = lin + x["c_all"][0][self.moy][None, :] + x["c_grp"][self.outer][:, self.moy]
        return lin

    def _to_outer(self, a: np.ndarray, mean: bool = False) -> np.ndarray:
        """Rows by group summed (or averaged) into rows by geography carrier."""
        o = self.outer.cpu().numpy()
        out = np.zeros((int(o.max()) + 1, *a.shape[1:]))
        np.add.at(out, o, a)
        return out / np.bincount(o).reshape(-1, *([1] * (a.ndim - 1))) if mean else out

    def _grp_place(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[groups, U]: s + v of each group's geography carrier."""
        return (x["s_grp"] + x["v_grp"])[self.outer]

    def _leaf_place(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """[E, U] exp(b0 + θ_grp + θ_cat + v_cat): the leaf's level and its own place deviation."""
        lin = (x["b0"][0] + x["th_grp"][0][self.grp] + x["th_cat"][0])[:, None]
        return torch.exp(lin + x["v_cat"]) if spatial else torch.exp(lin).expand(-1, self.N.shape[0])

    def _level(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[E] exp(b0 + θ_grp + θ_cat)."""
        return torch.exp(x["b0"][0] + x["th_grp"][0][self.grp] + x["th_cat"][0])

    def eta_nnz(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        p = self.p_e
        eta = (x["b0"][0] + x["th_grp"][0][p] + x["th_cat"][0][self.e] + x["f_all"][0][self.g] + x["f_grp"][p, self.g]
               + self._time(x)[p, self.tt] + self.logN_nnz)
        if spatial:
            eta = (eta + x["s_all"][0][self.u] + x["v_all"][0][self.u] + x["s_grp"][self.outer[p], self.u] + x["v_grp"][self.outer[p], self.u]
                   + x["v_cat"][self.e, self.u])
            if self.ix_on:
                psi = x["ix_psi"][:, self.ixp.clamp_min(0)] * (self.ixp >= 0)
                eta = eta + (psi * self._om(x)[:, self.u] * x["ix_t"][:, self.tt]).sum(0)
        if self.hc is not None:
            eta = eta + self.hc[self.e, self.tt]
        if self.off is not None and spatial:
            eta = eta + self.off[self.e, self.u, self.tt]
        return eta

    def total(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """Λ = Σ over every cell of μ, through the factorisation."""
        leaf_place = self._leaf_place(x, spatial)                                   # [E, U]
        per_group = torch.zeros((len(self.data.groups), self.N.shape[0]), dtype=self.dtype,
                                device=self.device).index_add_(0, self.grp, leaf_place)  # [K, U]
        total = (per_group[:, :, None] * self._place_time(x, spatial)).sum()
        leafwise = self.ix_on or self.hc is not None or self.off is not None
        return total + self._ix_correction(x) if leafwise and spatial else total

    def penalty(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        out = torch.zeros((), dtype=self.dtype, device=self.device)
        for name, c in self.components.items():
            v = x[name].reshape(c.batch, -1)
            if c.shape.name.startswith("iid"):   # Q = I: no sparse product
                out = out + 0.5 * c.tau * (v * v).sum()
            else:
                out = out + 0.5 * c.tau * (v * torch.sparse.mm(self._Q[name], v.T).T).sum()
        return out

    def objective(self) -> torch.Tensor:
        """−log L + penalty, divided by the number of events so gradients are of order one.
        Σ y·η comes from the sufficient statistics; only Λ is computed per evaluation. With the negative binomial
        likelihood (and a finite φ) the log-likelihood is `nb_loglik`'s, streamed over every cell."""
        x = self.effects()
        if self.likelihood == "nb" and np.isfinite(self.phi_fit):
            return (-torch.as_tensor(self.nb_loglik(self.phi_fit, x), dtype=self.dtype) + self.penalty(x)) / self.scale
        linear = sum((x[k] * self.Y[k]).sum() for k in self.Y) + self.y_offset
        if self.ix_on:
            linear = linear + (self._I(x) * self.Y3).sum()
        loglik = linear - self.total(x)
        return (-loglik + self.penalty(x)) / self.scale

    # ---- fitting ----------------------------------------------------------------

    def fit(self, outer: int = 25, inner: int = 30, tol: float = 0.02, log=print, warm: str | dict | None = None,
            mean_tol: float = 0.0, **_retired) -> Monolith:
        """The outer loop: the mean at fixed strengths (`_mean`), then the strengths' update (`_update_taus`), until no
        strength moves by more than ``tol`` (a log-ratio). ``warm`` ("auto", or a stored fit's key) starts from a
        related fit (`warm_start`). ``mean_tol`` floors the outers' inner tolerance (log-likelihood units of predicted
        decrease; at least 1,000 there, below), and the mean after the loop converges fully. v0's ``accelerate`` and
        ``move_tol`` are retired with it (2026-10-06) and ignored."""
        start = time.time()
        self._laml_prev = self.laml = self._tau_radius = self._tau_sign = None
        self._initialise()
        self.warm_info = self.warm_start(warm) if warm else None
        changes = [0.0] if self.warm_info else [np.inf]
        if self.rank and not self.ix_on:
            # the base model first (a zero interaction is a saddle), then the interaction from its residuals (ADR-0021)
            self._loop(outer, inner, tol, log, changes, mean_tol, start)
            self._enable_interaction()
            self._init_interaction()
            self._laml_prev = self._ix_omega = None          # the LAML changes with the model: no step is compared across
            changes = [np.inf]
            log(f"interaction rank {self.rank} started from the base fit's residuals; {time.time() - start:.0f}s")
        self._loop(outer, inner, tol, log, changes, mean_tol, start)
        # the closing mean to the fit's own tolerance (``mean_tol`` log-likelihood units of predicted decrease): at
        # 0.001 it took 7.4 of IX's 38.6 s for a decrease no figure reads (2026-10-06)
        self._mean(inner, loglik_tol=mean_tol)
        self.phi = self._dispersion()
        log(f"φ = {self.phi:.3f}; {time.time() - start:.0f}s; {'converged' if self.converged else 'NOT CONVERGED'}: {self.stop_reason}")
        return self

    def _loop(self, outer: int, inner: int, tol: float, log, changes: list[float], mean_tol: float, start: float) -> None:
        """The outer iterations of `fit`: the mean at fixed strengths, then the strengths' update."""
        self.converged, self.stop_reason = False, f"outer cap {outer}"
        for it in range(outer):
            # the mean need not be precise while the τ's still move: a few Newton steps until they settle
            t0 = time.time()
            # the first outer's strengths step is clipped far from the optimum anyway: its mean needs few steps (4 against
            # 10 saved 12 s on IX cold, 2026-10-06)
            # the outers stop their Newton steps below 1,000 log-likelihood units of predicted decrease, so most end
            # on one full step and the strengths read its factor, one step back (IX 67 → 59 s, XV 54 → 50 s, held-out
            # unchanged; IX's s_all ends 7 % off along the flat BYM ridge; 2026-10-06); the mean after the loop
            # converges fully
            steps = self._mean(inner if max(changes) < 0.1 else (4 if np.isinf(max(changes)) else 10),
                               loglik_tol=max(mean_tol, float(os.environ.get("PEGASUS_OUTER_TOL_FRAC", "inf")) * self.scale
                                              if "PEGASUS_OUTER_TOL_FRAC" in os.environ else max(mean_tol, 1000.0)))
            t1 = time.time()
            changes = self._update_taus()
            if self.likelihood == "nb":
                old = self.phi_fit
                self.phi_fit = self._dispersion()
                if np.isfinite(old) and np.isfinite(self.phi_fit):
                    changes = list(changes) + [abs(float(np.log(self.phi_fit / old)))]
                elif np.isfinite(self.phi_fit):
                    changes = list(changes) + [np.inf]
            move = max(self.refit_decrement, 0.0) * self._objective_norm()   # log-likelihood units the last τ update moved the MAP by
            self.history.append({"iteration": it, "objective": float(self.objective()) * self.scale, "newton": steps,
                                 "change": max(changes), "move": move, "mean_seconds": t1 - t0, "tau_seconds": time.time() - t1,
                                 "taus": {k: c.tau for k, c in self.components.items()}, "seconds": time.time() - start})
            taus = " ".join(f"{k}={c.tau:.3g}" for k, c in self.components.items())
            laml = f", LAML {self.laml:.1f} (gain {self.laml_gain:.2g})" if getattr(self, "laml", None) is not None else ""
            log(f"outer {it}: objective {self.history[-1]['objective']:.1f}, max τ change {max(changes):.3f}{laml}, "
                f"{time.time() - start:.0f}s | {taus}")
            if max(changes) < tol:
                self.converged, self.stop_reason = True, f"max τ change {max(changes):.3f} < {tol}"
                break

    def warm_start(self, source: str | dict = "auto") -> dict | None:
        """Overwrite the starting values with those of a related fitted block of the store: the same dataset,
        event, block, graph, profile, source and grain, for other years, another exposure or a split
        (``"auto"`` picks the best: the same exposure, then the most periods in common; a dict is a stored
        fit's key). Parameters are carried where their shape agrees; the histories (h) by the periods the two
        fits share, the rest held at the nearest carried value; every τ is carried. A start is only a start:
        the fit runs to its own convergence, so the optimum does not depend on it beyond the tolerance. Returns
        what was carried, or None when nothing relates."""
        mine = self.key()
        if isinstance(source, dict):
            cand = store.manifest("monolith", source)
        else:
            family = _family(mine)
            scored = []
            for m in store.manifests("monolith"):
                k = m["key"]
                if k == mine or _family(k) != family or "taus" not in m:
                    continue
                span = lambda key: set(_periods_of(key))   # noqa: E731
                shared = len(span(k) & span(mine))
                if shared == 0:
                    continue
                scored.append((k.get("rank", 0) == mine.get("rank", 0),
                               k.get("population", "popsvs") == mine.get("population", "popsvs"),
                               k.get("split") == mine.get("split"), shared / max(len(span(k) | span(mine)), 1),
                               k.get("through") == mine.get("through"), m))
            cand = max(scored, key=lambda s: s[:5])[5] if scored else None
        arrays = store.get_arrays("monolith", cand["key"]) if cand else None
        if cand is None or arrays is None:
            return None
        arrays = _legacy_centring(arrays, cand)
        carried, partial = [], []
        grain = self.data.grain
        my_first, theirs_first = _periods_of(mine)[0], _periods_of(cand["key"])[0]
        shift = my_first - theirs_first                    # my period i is theirs i + shift (in years, or months)
        if grain == "month":
            shift *= 12
        if self.rank and cand["key"].get("rank", 0) == self.rank and all(n in arrays for n in IX) and "ix_active" in arrays:
            self._enable_interaction(arrays["ix_active"])      # a stored fit of the same rank: its interaction is carried with the rest
            if any(tuple(arrays[n].shape) != tuple(self.params[n].shape) for n in IX):
                for n in IX:                # the periods differ: the interaction is started afresh from the base fit
                    del self.params[n], self.components[n]
                self.ix_on = False
        with torch.no_grad():
            for name, q in self.params.items():
                v = torch.as_tensor(arrays[name]) if name in arrays else None
                if v is None:
                    continue
                if name.startswith("h_") and v.shape[0] == q.shape[0]:
                    idx = np.clip(np.arange(q.shape[1]) + shift, 0, v.shape[1] - 1)
                    q.copy_(v[:, torch.as_tensor(idx)])
                    (carried if shift == 0 and v.shape == q.shape else partial).append(name)
                elif tuple(v.shape) == tuple(q.shape):
                    q.copy_(v)
                    carried.append(name)
        for name, tau in cand["taus"].items():
            if name in self.components:
                self.components[name].tau = float(tau)
        return {"from": cand["key"], "carried": carried, "shifted": partial}

    def _initialise(self) -> None:
        """Starting values: the Poisson maximum likelihood of the model leaf + group × year + group × age–sex, by iterative
        proportional fitting (the ML of a log-linear model; Bishop, Fienberg and Holland 1975, ch. 3), written into the
        centred parametrisation so that the effects reproduce it (the profiles' and levels' means to b0, the group
        levels and each group profile's own level to θ_grp, the rest to θ_cat, f_all, f_grp and h_all), then one
        backfitting pass for the place deviations (`_backfit_places`). A margin with no events counts half an event.
        The first start (each margin against the flat rate, then centred) began IX at an objective of 4.3·10⁸; the
        overall profile alone left the first Newton step moving f_grp by 13; this one begins within 1.5 % of the
        optimum (2026-10-06)."""
        d = self.data
        nE, (nT, nG) = len(d.leaves), d.N.shape[1:]
        grp = np.asarray(d.leaf_group)
        nK = int(grp.max()) + 1
        Ntg = d.N.sum(axis=0).astype(np.float64)                       # [T, G]: every leaf shares the exposure
        O_e = np.maximum(np.bincount(d.e, weights=d.y, minlength=nE), 0.5)
        O_kt = np.maximum(np.bincount(grp[d.e].astype(np.int64) * nT + d.t, weights=d.y, minlength=nK * nT), 0.5).reshape(nK, nT)
        O_kg = np.maximum(np.bincount(grp[d.e].astype(np.int64) * nG + d.g, weights=d.y, minlength=nK * nG), 0.5).reshape(nK, nG)
        exposed_t, exposed_g = Ntg.sum(axis=1) > 0, Ntg.sum(axis=0) > 0
        sm = np.ones((nK, nG)) if self._emask is None else self._emask.cpu().numpy()
        ok = exposed_g[None, :] & (sm > 0)                                   # [K, G]: a group's exposed cells
        # the margins made consistent: a margin with no events counts half an event, so each group's course and profile
        # margins are rescaled to its leaves' total; inconsistent margins have no IPF solution, and a small restricted
        # group's scale ran to overflow (F53, SIM V, 2026-10-06)
        tot_k = np.bincount(grp, weights=O_e, minlength=nK)
        O_kt = np.where(exposed_t[None, :], O_kt, 0.0)
        O_kt = O_kt * (tot_k / np.maximum(O_kt.sum(axis=1), 1e-300))[:, None]
        O_kg = np.where(ok, O_kg, 0.0)
        O_kg = O_kg * (tot_k / np.maximum(O_kg.sum(axis=1), 1e-300))[:, None]
        O_kt, O_kg = np.where(exposed_t[None, :], O_kt, 1.0), np.where(ok, O_kg, 1.0)
        a, b, c = np.zeros(nE), np.zeros((nK, nT)), np.zeros((nK, nG))
        for _ in range(200):
            a_old = a.copy()
            S = np.einsum("kt,tg,kg->k", np.exp(b), Ntg, np.exp(c) * sm)
            a = np.log(O_e) - np.log(S)[grp]
            A = np.bincount(grp, weights=np.exp(a), minlength=nK)               # [K]
            den = A[:, None] * ((np.exp(c) * sm) @ Ntg.T)                        # [K, T]
            b = np.where(exposed_t[None, :], np.log(O_kt) - np.log(np.where(exposed_t[None, :], den, 1.0)), 0.0)
            den = A[:, None] * (np.exp(b) @ Ntg)                                 # [K, G]
            c = np.where(ok, np.log(O_kg) - np.log(np.where(ok, den, 1.0)), 0.0)
            # the per-group scale held fixed every sweep (the leaves' a takes it at the next): profile and course at mean 0
            c = np.where(ok, c - ((c * ok).sum(axis=1) / np.maximum(ok.sum(axis=1), 1))[:, None], 0.0)
            b = b - b.mean(axis=1, keepdims=True)
            if np.abs(a - a_old).max() < 1e-10:
                break
        # the IPF fixes each group's leaves × profile × course only up to a scale per group: put each profile's mean over
        # its admissible cells (and each course's mean) at zero, the scale on the leaves. Left free, a group with two
        # admissible cells or one death (A33, A34) drifted to −36 and its level to +240 (SIM I, 2026-10-06)
        shift = (c * ok).sum(axis=1) / np.maximum(ok.sum(axis=1), 1) + b.mean(axis=1)
        c = np.where(ok, c - ((c * ok).sum(axis=1) / np.maximum(ok.sum(axis=1), 1))[:, None], 0.0)
        b = b - b.mean(axis=1, keepdims=True)
        a = a + shift[grp]
        level = np.bincount(grp, weights=a, minlength=nK) / np.maximum(np.bincount(grp, minlength=nK), 1)
        bbar = b.mean(axis=0)
        cbar = (c * ok).sum(axis=0) / np.maximum(ok.sum(axis=0), 1)
        F, B = (c - cbar[None, :]) * ok, b - bbar[None, :]
        if self._emask is not None:
            # the excluded ages of an allowed sex start on the line through their nearest admissible bands (the RW2's
            # own extension), not at zero beside them
            nB = self.nB
            for k in range(nK):
                for sx in range(2):
                    row = F[k, sx * nB:(sx + 1) * nB]
                    adm = np.flatnonzero(ok[k, sx * nB:(sx + 1) * nB])
                    if 0 < len(adm) < nB:
                        lo2, hi2 = adm[:2], adm[-2:]
                        slope_lo = (row[lo2[-1]] - row[lo2[0]]) / max(lo2[-1] - lo2[0], 1)
                        slope_hi = (row[hi2[-1]] - row[hi2[0]]) / max(hi2[-1] - hi2[0], 1)
                        for j in range(nB):
                            if j < adm[0]:
                                row[j] = row[adm[0]] + (j - adm[0]) * slope_lo
                            elif j > adm[-1]:
                                row[j] = row[adm[-1]] + (j - adm[-1]) * slope_hi
        # the course by geography carrier, centred across the carriers; the part centring removes joins h_all
        Bo = self._to_outer(B, mean=True)
        bbar = bbar + Bo.mean(axis=0)
        Bo = Bo - Bo.mean(axis=0, keepdims=True)
        course = Bo[self.outer.cpu().numpy()].mean(axis=1)
        # each group's own profile and course levels (the profiles' over the exposed age–sex cells, as they are centred)
        if self._fproj is None:
            lv = level + (F * ok).sum(axis=1) / np.maximum(ok.sum(axis=1), 1) + course
        else:
            # on an incomplete table the centring removes an additive part α_k + β_g from the profiles, not the row
            # means alone: α_k joins the group's level and β_g the overall profile, so the effects reproduce the fit on
            # every admissible cell (crediting the row means only started SIM I at 8 times its optimum, 2026-10-06)
            idx, P, _ = (t.cpu().numpy() for t in self._fproj)
            removed = F.reshape(-1)[idx] - P @ F.reshape(-1)[idx]
            kk, gg = np.divmod(idx, nG)
            A = np.zeros((len(idx), nK + nG))
            A[np.arange(len(idx)), kk] = 1.0
            A[np.arange(len(idx)), nK + gg] = 1.0
            coef = np.linalg.lstsq(A, removed, rcond=None)[0]
            lv = level + coef[:nK] + course
            cbar = cbar + coef[nK:]
        with torch.no_grad():
            self.params["b0"].fill_(float(lv.mean() + bbar.mean() + cbar[exposed_g].mean()))
            self.params["th_grp"].copy_(torch.as_tensor(lv - lv.mean())[None, :])
            self.params["th_cat"].copy_(torch.as_tensor(a - level[grp])[None, :])
            self.params["h_all"].copy_(torch.as_tensor(bbar)[None, :])
            self.params["h_grp"].copy_(torch.as_tensor(Bo))
            self.params["f_all"].copy_(torch.as_tensor(cbar).reshape(self.params["f_all"].shape))
            self.params["f_grp"].copy_(torch.as_tensor(F).reshape(self.params["f_grp"].shape))
        # their strengths from the same fit: Fellner–Schall's value for a well-identified effect, rank / x̂ᵀQx̂ (its
        # trace term is small). At τ = 1 the leaf levels (sd ≈ 4 on IX, final τ 0.06) were pulled to their group's and
        # a chord step then moved one by 195
        x = self.effects()
        for n in ("th_grp", "th_cat", "f_all", "f_grp", "h_all", "h_grp"):
            comp = self.components[n]
            v = x[n].detach().cpu().numpy().reshape(comp.batch, -1)
            q = float(sum(v[r] @ (comp.shape.Q @ v[r]) for r in range(comp.batch)))
            if comp.rank > 0 and q > 0:
                comp.tau = float(np.clip(comp.rank / q, 1e-3, 1e3))
        self._backfit_places(a, b, c)

    def _backfit_places(self, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> None:
        """One backfitting pass for the leaf-place deviations over the main-effects fit: each (leaf, place)'s penalised
        Poisson estimate w = argmin E·eʷ − O·w + ½τw² (τ the current v_cat strength), solved per cell, then split into
        the place (v_all), group-place (v_grp) and leaf-place (v_cat) parts their centrings expect. From the main
        effects alone, the first Newton step moved a v_cat by 66 (a cell with events where μ was tiny gets y/μ, not
        log(y/μ)), and later steps spent themselves undoing it (IX, 2026-10-06)."""
        d = self.data
        nU, nE = d.N.shape[0], len(d.leaves)
        grp = np.asarray(d.leaf_group)
        sm = np.ones_like(c) if self._emask is None else self._emask.cpu().numpy()
        W = np.einsum("utg,kt,kg->ku", d.N, np.exp(b), np.exp(c) * sm)                        # [K, U]
        E = np.exp(a)[:, None] * W[grp]
        Obs = np.bincount(d.e.astype(np.int64) * nU + d.u, weights=d.y, minlength=nE * nU).reshape(nE, nU)
        nK = int(grp.max()) + 1
        grp = self.outer.cpu().numpy()[grp]            # the place deviations belong to the geography carriers
        nK = int(grp.max()) + 1
        # the place strengths' start: Marshall's (1991) moment estimate of the between-unit variance of observed over
        # expected (less its Poisson part) at each level, each level's expectation carrying the level above; the
        # ICAR and iid parts of a level share its variance equally. At τ = 1 the first outer moved s_grp by 14 and
        # then the strengths jumped ×100
        O_u, E_u = Obs.sum(0), E.sum(0)
        O_ku, E_ku = np.zeros((nK, nU)), np.zeros((nK, nU))
        np.add.at(O_ku, grp, Obs)
        np.add.at(E_ku, grp, E)
        def moment(o, e):
            m = o.sum() / e.sum()
            keep = e > 0
            s2 = float((e[keep] * (o[keep] / e[keep] - m) ** 2).sum() / e[keep].sum())
            noise = m / e[keep].mean()
            if s2 <= 2.0 * noise:
                # the between-unit variance is not distinguishable from the Poisson part: start shrunk. Against τ = 1,
                # held-out NB log-likelihood on SIM VII, VIII, XV, XVII, III: better on four, XV by 0.10 per death
                return 1e3
            var = (s2 - noise) / m ** 2                                        # of the log relative risk, by the delta method
            return float(np.clip(1.0 / var, 1.0, 1e3))
        ratio_u = np.divide(O_u, E_u, out=np.ones_like(E_u), where=E_u > 0)
        t_all = moment(O_u, E_u)
        t_grp = moment(O_ku, E_ku * ratio_u[None, :])
        ratio_ku = np.divide(O_ku, E_ku, out=np.ones_like(E_ku), where=E_ku > 0)
        t_cat = moment(Obs, E * ratio_ku[grp])
        for n, t in (("s_all", 2 * t_all), ("v_all", 2 * t_all), ("s_grp", 2 * t_grp), ("v_grp", 2 * t_grp), ("v_cat", t_cat)):
            self.components[n].tau = float(np.clip(t, 1.0, 1e3))
        tau = self.components["v_cat"].tau
        w = np.zeros_like(E)
        for _ in range(40):
            ew = E * np.exp(w)
            dw = np.clip((Obs - ew - tau * w) / (ew + tau), -1.0, 1.0)
            w += dw
            if np.abs(dw).max() < 1e-8:
                break
        cnt = np.bincount(grp, minlength=nK)[:, None]
        gmean = np.zeros((nK, nU))
        np.add.at(gmean, grp, w)
        gmean /= np.maximum(cnt, 1)
        place = gmean.mean(axis=0)
        with torch.no_grad():
            self.params["v_cat"].copy_(torch.as_tensor(w - gmean[grp]))
            self.params["v_grp"].copy_(torch.as_tensor(gmean - place[None, :]))
            self.params["v_all"].copy_(torch.as_tensor(place)[None, :])

    def _mean(self, iterations: int, loglik_tol: float = 0.0) -> int:
        """The mean's MAP at fixed strengths by exact Newton on the assembled Hessian (`solver.fit_mean`, ARCHITECTURE
        §5.3), for every model: counts (IX cold 59 s against the retired v0 Newton–CG's 501 s), the low-rank
        interaction (its factors by `solver.ix_sweep`), the mark and share models (their cells' Fisher weights)."""
        from . import solver
        nw = getattr(self, "_solver_v1", None) or solver.StructuredNewton(self)
        tol = max(loglik_tol, 1e-3)
        steps = solver.fit_mean(self, iterations=iterations, loglik_tol=tol, solver=nw)
        if self.ix_on:
            # the interaction's factors by a joint (modified exact) Newton step, alternating with the base's Newton;
            # the alternation between the two blocks converges linearly (IX rank 3: 53,322, 457, 36, 6, 3.1, 2.0,
            # 1.5 … units), and an alternation below two log-likelihood units ends it
            for _ in range(iterations):
                gain = solver.ix_sweep(self)
                # a chord start on the sweep's last factor was measured and dropped: rank-1 IX took 63 Newton steps and
                # 228 s against 36 and 178 s (2026-10-06)
                steps += solver.fit_mean(self, iterations=iterations, loglik_tol=tol, solver=nw)
                if gain < max(2.0, min(tol, 1e3)):
                    break
        return steps

    def _objective_norm(self) -> float:
        """The divisor of the objective (events for counts)."""
        return self.scale

    def _update_taus(self) -> list[float]:
        """The strengths' update (ARCHITECTURE §5.4): with the horseshoe, its node weights from the tree levels' exact
        Laplace variances (`_update_horseshoe`); the safeguarded Newton step on log τ of every learned strength
        (`_score_taus`); with the interaction, its ω strengths from ω's own system (`solver.ix_strengths`). Returns
        the |log τ| changes, one per component."""
        from . import solver
        nw = getattr(self, "_solver_v1", None) or solver.StructuredNewton(self)
        self._solver_v1 = nw
        if self.prior == "horseshoe":
            self._update_horseshoe(nw)
        changes = self._score_taus(nw)
        if self.ix_on:
            if getattr(self, "_ix_omega", None) is None:
                solver.ix_sweep(self)
            ix = dict(zip(("ix_os", "ix_ov"), solver.ix_strengths(self), strict=True))
            changes = [ix.get(n, ch) for n, ch in zip(self.components, changes, strict=True)]
        return changes

    def _update_horseshoe(self, nw) -> None:
        """The horseshoe on the tree levels (ARCHITECTURE §4.3): θ_n ~ N(0, σ²λ_n²), λ_n ~ C⁺(0, 1), as the
        reweighted Gaussian penalty τ·Σ w_n θ_n² with w_n = E[1/λ_n²]. Through the auxiliary form λ² | ν ~ IG(½, 1/ν),
        ν ~ IG(½, 1) (Makalic & Schmidt 2016) the mean-field fixed point is closed: with c = τ·E[θ_n²]/2,
        w = 1/(c + 1/(1 + w)), so w = (√(1 + 4/c) − 1)/2. E[θ²] = θ̂² + Var θ_n, the node's Laplace variance, read
        exactly from the globals' covariance block of the v1 factor (`solver.StructuredNewton.traces`; v0 used
        1/(Fisher diagonal + τw)). A node near zero gets w ≈ c^(−½), a large precision, and shrinks to its parent; a
        node far from it gets w ≈ 1/c and is left nearly free, which is what one variance per level cannot do: shrink
        the noise and keep the signal. σ² = 1/τ stays the level's global scale, learned with the other strengths."""
        if getattr(nw, "_last", None) is None:
            nw.refactor()
        nw.traces(probes=0)
        var = np.diag(nw._Sx)
        x = self.effects()
        for name in HS:
            c = self.components[name]
            v = x[name].detach().reshape(-1).cpu().numpy()
            o = nw.goff[name]
            e2 = v * v + var[o:o + v.size]
            cc = np.maximum(0.5 * c.tau * e2, 1e-12)
            self._set_weights(name, (np.sqrt(1.0 + 4.0 / cc) - 1.0) / 2.0)

    def _set_weights(self, name: str, w: np.ndarray) -> None:
        """A tree level's precision becomes diag(w): every consumer (the penalty, the Newton preconditioner,
        Fellner–Schall, the Laplace posterior) reads it from the component's shape."""
        c = self.components[name]
        w = np.clip(np.asarray(w, dtype=float), 1e-6, 1e8)
        c.shape = structures.Shape("horseshoe", sp.diags(w, format="csr"), c.shape.rank, c.shape.centred, c.shape.components)
        self._Q[name] = _torch_sparse(c.shape.Q, self.dtype, self.device)

    def _score_taus(self, nw) -> list[float]:
        """A safeguarded Newton step on ρ = log τ (v1; ARCHITECTURE §5.4) for the Laplace marginal likelihood (LAML),
        W's dependence on the mean dropped: the gradient g_j = ½(r_j − τ_j xᵀQ_jx − τ_j tr(ΣQ_j)), and the observed
        negative Hessian −H_ij = ½δ_ij τ_j(tr(ΣQ_j) + xᵀQ_jx) − ½τ_iτ_j tr(ΣQ_iΣQ_j) − τ_iτ_j xᵀQ_iΣQ_jx (zero, as it
        must be, for a component the data do not inform). Away from the optimum −H can be indefinite: its spectrum
        is floored before the solve. **The safeguard is mgcv's** (Wood 2011, §3): the LAML itself is evaluated at each
        new mean, and a step that lowered it is halved from where it started instead of being followed by a new one.
        Steps are clipped to ×100; a strength past `SHRUNK` and still rising has shrunk its effect away and stops.
        The fixed point is Fellner–Schall's (g = 0)."""
        names = [n for n, c in self.components.items() if c.rank > 0 and not c.fixed and not n.startswith("ix_")]
        rho_now = np.log([self.components[n].tau for n in names])
        rank = np.array([self.components[n].rank for n in names])
        rem = {}

        def read_laml() -> float:
            rem["left"] = nw.remaining()
            return (-float(self.objective()) * self._objective_norm() + rem["left"] + 0.5 * float(rank @ rho_now)
                    - 0.5 * nw.logdet_constrained())
        laml = read_laml()
        # the LAML is read accurately only near the mean's mode: far from it (a large strength step just taken) the
        # remaining decrease is itself a rough quadratic estimate, and SIH I's reference read 800 units high, so the
        # guard reverted a sound fit to its first outer's strengths (2026-10-06). Comparisons need both reads accurate
        accurate = rem["left"] < 10.0
        # the LAML is comparable across outers only when nothing else moves between them: with the interaction on (its
        # factors and strengths), or a mark model's dispersion re-estimated every outer (its cells' weights), there is
        # no line search (IX rank 1 halved every step; birth weight halved back to τ = 1 where v0 had 10⁴)
        prev = (None if self.ix_on or hasattr(self, "cell_derivatives") or self.likelihood == "nb"
                else getattr(self, "_laml_prev", None))
        # the step aims at the fixed point without W's derivative, which sits a few per cent of τ from the LAML's own
        # optimum (IX, 2026-10-06): a fall of a few units is that difference, not an overshoot
        if prev is not None and not (prev["accurate"] and accurate):
            prev = None
        if prev is not None and laml < prev["laml"] - 2.0:
            # read again from a factor at the current mean before rejecting: the outers' factor is one Newton step
            # back, and its log-determinant moved SIM II's LAML by 8 units at the same strengths (2026-10-06)
            nw.refactor()
            laml = read_laml()
        self.laml = laml
        if prev is not None and laml < prev["laml"] - 2.0:
            if prev["halvings"] >= 3:
                # three halvings did not help: back to the best strengths found, and stop there
                for n, r0 in zip(names, prev["rho"], strict=True):
                    self.components[n].tau = float(np.exp(r0))
                self._laml_prev = None
                self.laml_gain = 0.0
                return [0.0] * len(self.components)
            step = prev["step"] / 2
            self._laml_prev = {**prev, "step": step, "halvings": prev["halvings"] + 1}
            for n, r0, dlt in zip(names, prev["rho"], step, strict=True):
                self.components[n].tau = float(np.clip(np.exp(r0 + dlt), *TAU_BOUNDS))
            self.laml_gain = float("inf")
            # a halved step is small by construction: it must not read as convergence (SIM II stopped mid-halving)
            return [1.0] * len(self.components)
        # Hutchinson probes for the place traces: 8 on a large block, 16 on a sparse one. Halved on IX and XX the held-out
        # figures were unchanged to 1e-5 and IX's strengths took 7.3 s against 11.0; on VII (277 deaths) the held-out
        # NB log-likelihood fell by 0.17 per death (2026-10-06)
        probes = int(os.environ.get("PEGASUS_SCORING_PROBES", "8" if self.scale >= 1e5 else "16"))
        tr, quad, T, R, names = nw.scoring(probes=probes)
        tau = np.array([self.components[n].tau for n in names])
        q = np.array([quad[n] for n in names])
        t = np.array([tr[n] for n in names])
        g = 0.5 * (rank - tau * q - tau * t)
        # the place traces are probe estimates: a gradient within twice its standard error is noise (on IX it reached
        # ±13 for v_all, which kept the predicted gain above the stop for a dozen outers), so g is shrunk by it
        se = 0.5 * tau * np.array([getattr(nw, "trace_se", {}).get(n, 0.0) for n in names])
        g = np.sign(g) * np.maximum(np.abs(g) - 2.0 * se, 0.0)
        tt = np.outer(tau, tau)
        negH = np.diag(0.5 * tau * (t + q)) - 0.5 * tt * T - tt * R
        negH = (negH + negH.T) / 2
        # the spectrum floored on each component's own scale (the matrix scaled by its diagonal), not on the largest
        # eigenvalue's, which belongs to the best-informed component and would flatten the weakly informed ones
        dg = np.sqrt(np.maximum(np.abs(np.diag(negH)), 1e-12))
        w, v = np.linalg.eigh(negH / np.outer(dg, dg))
        w = np.maximum(w, 1e-2)
        step = (v @ ((v.T @ (g / dg)) / w)) / dg
        # where Fellner–Schall (a convergent map) points the same way and further, take its step: the flat directions
        # of a weakly identified strength are where Newton's curvature is least reliable
        fs = np.log(np.maximum(rank - tau * t, 1e-12) / np.maximum(tau * q, 1e-300))
        bolder = (np.sign(fs) == np.sign(step)) & (np.abs(fs) > np.abs(step))
        step = np.where(bolder, fs, step)
        # no jump to a boundary: from the first outer's τ = 1, Newton's step overran the clip for s_all and v_all on IX,
        # and sent to 10·SHRUNK they stayed there (the LAML is flat out there): held-out NB log-likelihood −1.63793
        # against −1.63716 (2026-10-06)
        # each strength's own step radius, adapted as Rprop's (Riedmiller & Braun 1993): halved when its step reverses,
        # ×1.2 while it keeps its direction, ×100 at most. Unguarded far from the mode, SIM VI's steps flipped between
        # two states (s_grp 10 ↔ 1,000, v_cat 0.85 ↔ 85) for 28 outers (2026-10-06)
        radius = getattr(self, "_tau_radius", None) or {}
        last = getattr(self, "_tau_sign", None) or {}
        lim = np.empty(len(names))
        for i, n in enumerate(names):
            r0 = radius.get(n, np.log(100.0))
            sg = float(np.sign(step[i]))
            if last.get(n, 0.0) * sg < 0:
                r0 = r0 / 2
            elif last.get(n, 0.0) * sg > 0:
                r0 = min(r0 * 1.2, np.log(100.0))
            lim[i] = max(r0, 1e-3)
            radius[n], last[n] = lim[i], sg
        self._tau_radius, self._tau_sign = radius, last
        step = np.clip(step, -lim, lim)
        gone = (tau > self.shrunk) & (step > 0)
        step = np.where(gone, 0.0, step)
        if float(g @ step) <= 0.0 and float(np.abs(g).max()) > 0.0:
            # clipping a non-diagonal Newton step component by component can leave a descent direction of the LAML (SIM
            # VI's predicted gain came out −1,800, which read as convergence after one outer, 2026-10-06): the diagonal
            # Newton step instead, an ascent direction since the floored diagonal is positive
            step = np.clip(g / (dg * dg), -lim, lim)
            step = np.where((tau > self.shrunk) & (step > 0), 0.0, step)
        # the step's own predicted gain in the marginal likelihood: along the BYM ridge (s against v) the likelihood
        # is flat and τ can wander without changing the fit, so convergence is read from the gain, not from Δρ
        self.laml_gain = float(0.5 * g @ step)
        # one LAML unit: at 0.1 the BYM ridge's outers changed no held-out figure (II 11 → 7, VI 14 → 10 outers, the
        # held-out NB log-likelihood equal to five decimals, 2026-10-06)
        if self.laml_gain < float(os.environ.get("PEGASUS_LAML_TOL", "1.0")):
            return [0.0] * len(self.components)
        self._laml_prev = {"rho": rho_now, "laml": laml, "step": step, "halvings": 0, "accurate": accurate}
        out = {}
        for n, tau_n, d in zip(names, tau, step, strict=True):
            new = float(np.clip(tau_n * np.exp(d), *TAU_BOUNDS))
            out[n] = abs(np.log(new / tau_n))
            self.trace_log.append((n, self.components[n].rank, quad[n], tr[n], tau_n, new))
            self.components[n].tau = new
        return [out.get(n, 0.0) for n in self.components]

    def nb_loglik(self, phi: float | np.ndarray, x: dict[str, torch.Tensor] | None = None,
                  places: np.ndarray | None = None) -> float:
        """The NB log-likelihood of every cell of the block at fixed μ (ARCHITECTURE §5.2), ``phi`` a
        scalar or a value per place, over the cells of ``places`` (a boolean mask; None: all). Non-empty
        cells enter exactly; the empty cells' Σ log p(0) = −φ Σ_empty log(1 + μ/φ) is the sum over every
        cell minus the non-empty cells', the former streamed leaf by leaf (one [U, T, G] slab at a time,
        P10). ``x`` overrides the fitted effects (a forecast: held-out years)."""
        with torch.no_grad():
            x = self.effects() if x is None else x
            mu = torch.exp(self.eta_nnz(x)).cpu().numpy()
            lp = self._leaf_place(x)                                              # [E, U]
            lin = (self._time(x)[:, None, :]
                   + (x["s_all"][0] + x["v_all"][0])[None, :, None] + self._grp_place(x)[:, :, None])
            base = torch.exp(lin)                                                 # [K, U, T]
            prof = self._prof(x)                                                  # [K, G]
        y, u = self.data.y, self.data.u
        sel = slice(None)
        keep = np.ones(self.N.shape[0], dtype=bool) if places is None else np.asarray(places, dtype=bool)
        if places is not None:
            cell = keep[u]
            mu, y, u = mu[cell], y[cell], u[cell]
            sel = torch.as_tensor(keep, device=self.device)
        per_place = np.ndim(phi) > 0
        ph = np.asarray(phi, dtype=float)[u] if per_place else float(phi)
        full = (special.gammaln(y + ph) - special.gammaln(ph) - special.gammaln(y + 1)
                + ph * np.log(ph / (ph + mu)) + y * np.log(mu / (ph + mu)))
        divisor = (torch.as_tensor(np.asarray(phi, dtype=float)[keep], dtype=self.dtype, device=self.device)[:, None, None]
                   if per_place else float(phi))
        total = 0.0                                      # Σ_all φ log(1 + μ/φ)
        with torch.no_grad():
            om = self._om(x) if self.ix_on else None
            for e in range(lp.shape[0]):
                k = int(self.grp[e])
                m = lp[e][sel][:, None, None] * base[k][sel][:, :, None] * self.N[sel] * prof[k][None, None, :]
                if om is not None and int(self.ixpos[e]) >= 0:
                    m = m * torch.exp(torch.einsum("r,ru,rt->ut", x["ix_psi"][:, int(self.ixpos[e])], om, x["ix_t"]))[sel][:, :, None]
                oe = self._offset(e)
                if oe is not None:
                    m = m * torch.exp(oe[sel])[:, :, None]
                total += float((divisor * torch.log1p(m / divisor)).sum())
        return float(full.sum()) - (total - float((ph * np.log1p(mu / ph)).sum()))

    def _dispersion(self, places: np.ndarray | None = None) -> float:
        """φ by maximum likelihood with μ fixed (ARCHITECTURE §5.2): the maximiser of `nb_loglik` over
        the cells of ``places`` (a boolean mask over the block's places; None: all of them).

        Two estimators failed first, on chapter IX 2010–2023: moments (Pearson residuals of cells
        with tiny μ and y ≥ 1 dominate: φ = 0.013), and a power series for the empty cells
        (they hold 1.95 M of 4.99 M expected events, μ/φ is not small, the series diverges)."""
        nll = self._nb_loglik_binned(places)

        res = optimize.minimize_scalar(nll, bounds=(np.log(1e-3), np.log(1e6)), method="bounded",
                                       options={"xatol": 1e-3})
        phi = float(np.exp(res.x))
        if places is None:
            self.dispersion_check = {"phi": phi, "evaluations": int(res.nfev),
                                     "loglik_gain_over_poisson": float(nll(np.log(1e6)) - res.fun)}
        return float("inf") if phi > 0.99e6 else phi

    def _nb_loglik_binned(self, places: np.ndarray | None = None, bins: int = 8192):
        """−`nb_loglik` as a function of log φ at fixed μ, for the 1-D search of `_dispersion`: the non-empty cells
        exactly, and the sum over every cell of φ·log(1 + μ/φ) from one streamed pass that bins the cells by log μ
        (count, Σμ, Σμ² per bin; the bin's term at its mean plus the second-order correction ½f''·Σ(μ − μ̄)²,
        exact to about 10⁻⁹ relative at 8,192 bins). Each evaluation then costs O(bins) instead of a pass over every
        cell (IX: 185 M cells, about 1 s per evaluation and 14 evaluations)."""
        with torch.no_grad():
            x = self.effects()
            mu = torch.exp(self.eta_nnz(x)).cpu().numpy()
            lp = self._leaf_place(x)
            lin = (self._time(x)[:, None, :]
                   + (x["s_all"][0] + x["v_all"][0])[None, :, None] + self._grp_place(x)[:, :, None])
            base = torch.exp(lin)
            prof = self._prof(x)
            y, u = self.data.y, self.data.u
            sel = slice(None)
            if places is not None:
                keep = np.asarray(places, dtype=bool)
                cell = keep[u]
                mu, y = mu[cell], y[cell]
                sel = torch.as_tensor(keep, device=self.device)
            # the edges: log μ is a sum of the factors' logs, so their extremes bound it (one pass, not two)
            Npos = self.N[sel][self.N[sel] > 0]
            def ext(t):
                t = torch.log(t[t > 0])
                return float(t.min()), float(t.max())
            parts = [ext(lp[:, sel] if places is not None else lp), ext(base[:, sel] if places is not None else base),
                     ext(Npos), ext(prof)]
            lo, hi = sum(p[0] for p in parts) - 1e-6, sum(p[1] for p in parts) + 1e-6
            slabs = range(lp.shape[0])
            n = torch.zeros(bins, dtype=self.dtype, device=self.device)
            s1, s2 = torch.zeros_like(n), torch.zeros_like(n)
            om = self._om(x) if self.ix_on else None
            if om is not None:          # an active leaf's slab carries exp(I) (a bound for the edges: |I| at most)
                imax = float(self._I(x).abs().max())
                lo, hi = lo - imax, hi + imax
            if self.hc is not None or self.off is not None:     # and the leaf-place-period offsets
                hmax = float(self._offset().abs().max())
                lo, hi = lo - hmax, hi + hmax
            for e in slabs:
                k = int(self.grp[e])
                m = lp[e][sel][:, None, None] * base[k][sel][:, :, None] * self.N[sel] * prof[k][None, None, :]
                if om is not None and int(self.ixpos[e]) >= 0:
                    m = m * torch.exp(torch.einsum("r,ru,rt->ut", x["ix_psi"][:, int(self.ixpos[e])], om, x["ix_t"]))[sel][:, :, None]
                oe = self._offset(e)
                if oe is not None:
                    m = m * torch.exp(oe[sel])[:, :, None]
                m = m.reshape(-1)
                # an unexposed cell (μ = 0) goes to an extra bin that is dropped: no compaction of the slab
                idx = torch.where(m > 0, ((torch.log(m) - lo) / (hi - lo) * bins).clamp_(0, bins - 1),
                                  torch.full_like(m, bins)).long()
                n += torch.bincount(idx, minlength=bins + 1)[:bins].to(self.dtype)  # bincount: 3x index_add_'s speed
                s1 += torch.bincount(idx, weights=m, minlength=bins + 1)[:bins]
                s2 += torch.bincount(idx, weights=m * m, minlength=bins + 1)[:bins]
        n, s1, s2 = (t.cpu().numpy() for t in (n, s1, s2))
        used = n > 0
        n, s1, s2 = n[used], s1[used], s2[used]
        mbar = s1 / n
        spread = np.maximum(s2 - s1 * mbar, 0.0)
        # Σ_cells lgamma(y + φ) over the distinct counts (exact)
        vals, cnt = np.unique(y, return_counts=True)
        const = float(special.gammaln(y + 1).sum())
        logmu = np.log(mu)

        def nll(log_phi: float) -> float:
            ph = float(np.exp(log_phi))
            lpm = np.log(ph + mu)
            full = (float((cnt * special.gammaln(vals + ph)).sum()) - len(y) * special.gammaln(ph) - const
                    + float((ph * (np.log(ph) - lpm) + y * (logmu - lpm)).sum()))
            total = float((n * ph * np.log1p(mbar / ph) - 0.5 * ph / (ph + mbar) ** 2 * spread).sum())
            return -(full - (total - float((ph * np.log1p(mu / ph)).sum())))
        return nll

    def dispersion_by(self, labels: np.ndarray) -> np.ndarray:
        """φ per place when each group of places (``labels``, one per place) has its own, by `_dispersion`."""
        out = np.empty(len(labels))
        for g in np.unique(labels):
            out[labels == g] = self._dispersion(labels == g)
        return out

    # ---- prediction ---------------------------------------------------------------

    def expected(self, leaves: np.ndarray, spatial: bool = True,
                 x: dict[str, torch.Tensor] | None = None) -> tuple[np.ndarray, np.ndarray]:
        """For a set of leaves (a node of the tree): μ[u,t] summed over the leaves and groups,
        and Σμ²[u,t] over the underlying cells (for the aggregate's dispersion). ``x`` overrides
        the fitted effects (a forecast, `extrapolate`)."""
        with torch.no_grad():
            x = self.effects() if x is None else x
            lp = self._leaf_place(x, spatial)
            pt = self._place_time(x, spatial)
            sel = torch.as_tensor(leaves, device=self.device)
            K, U = len(self.data.groups), self.N.shape[0]
            ix = self.ix_on and spatial
            E = torch.exp(self._I_of(x, sel)) if ix else None
            off = self._offset(sel) if spatial else (None if self.hc is None else self.hc[sel][:, None, :])
            if off is not None:         # the category courses and N2's offset [n, U, T]
                H = torch.exp(off)
                E = H if E is None else E * H
            ix = E is not None
            if ix:      # a leaf-specific factor makes each leaf's place-time factor its own: [K, U, T] sums over the leaves
                w = torch.zeros((K, *pt.shape[1:]), dtype=self.dtype, device=self.device).index_add_(
                    0, self.grp[sel], lp[sel][:, :, None] * E)
            else:
                w = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel])[:, :, None]
            mu = (w * pt).sum(0)
            M2 = torch.einsum("utg,kg->kut", self.N ** 2, self._prof(x, 2.0))
            lin = self._time(x)[:, None, :]
            if spatial:
                lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + self._grp_place(x)[:, :, None]
            if ix:
                w2 = torch.zeros((K, *pt.shape[1:]), dtype=self.dtype, device=self.device).index_add_(
                    0, self.grp[sel], (lp[sel][:, :, None] * E) ** 2)
            else:
                w2 = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel] ** 2)[:, :, None]
            mu2 = (w2 * torch.exp(2 * lin) * M2).sum(0)
        mu, mu2 = mu.cpu().numpy(), mu2.cpu().numpy()
        if self.supply is not None:
            mu, mu2 = mu * self.supply, mu2 * self.supply ** 2
        return mu, mu2

    def expected_by_group(self, leaves: np.ndarray, spatial: bool = True,
                          x: dict[str, torch.Tensor] | None = None) -> np.ndarray:
        """μ[u,t,g] summed over the leaves (g = sex × age band)."""
        with torch.no_grad():
            x = self.effects() if x is None else x
            lp = self._leaf_place(x, spatial)
            sel = torch.as_tensor(leaves, device=self.device)
            K, U = len(self.data.groups), self.N.shape[0]
            lin = self._time(x)[:, None, :]
            if spatial:
                lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + self._grp_place(x)[:, :, None]
            prof = self._prof(x)                                                        # [K, G]
            E = torch.exp(self._I_of(x, sel)) if self.ix_on and spatial else None
            off = self._offset(sel) if spatial else (None if self.hc is None else self.hc[sel][:, None, :])
            if off is not None:
                H = torch.exp(off)
                E = H if E is None else E * H
            if E is not None:
                w = torch.zeros((K, U, self.N.shape[1]), dtype=self.dtype, device=self.device).index_add_(
                    0, self.grp[sel], lp[sel][:, :, None] * E)
                mu = torch.einsum("kut,kut,kg,utg->utg", w, torch.exp(lin), prof, self.N)
            else:
                w = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel])
                mu = torch.einsum("ku,kut,kg,utg->utg", w, torch.exp(lin), prof, self.N)
        mu = mu.cpu().numpy()
        return mu if self.supply is None else mu * self.supply[:, :, None]

    def exposure_variance(self, leaves: np.ndarray, spatial: bool = True, rho: float = 0.0,
                          x: dict[str, torch.Tensor] | None = None) -> np.ndarray:
        """Var(μ[u,t]) from the uncertainty of the population (ARCHITECTURE §3.1, §4.1, P8): the cells'
        log N_g ~ N(log N̂_g, s_g²) with ``data.S`` from the population's intervals, μ = Σ_g μ_g, so
        Var(μ) = Σ_g μ_g² (e^{s_g²} − 1) + ρ [(Σ_g μ_g s_g)² − Σ_g μ_g² s_g²]: ρ = 0 independent cells,
        ρ = 1 the log errors of a place-year's sex-age cells fully shared (first order). Zero where the
        population carries no uncertainty (POPSVS)."""
        if self.data.S is None:
            return np.zeros(self.data.N.shape[:2])
        mu_g, S = self.expected_by_group(leaves, spatial, x), self.data.S
        return (mu_g ** 2 * np.expm1(S ** 2)).sum(2) + rho * ((mu_g * S).sum(2) ** 2 - (mu_g ** 2 * S ** 2).sum(2))

    def observed(self, leaves: np.ndarray) -> np.ndarray:
        nU, nT, _ = self.data.N.shape
        m = np.isin(self.data.e, leaves)
        out = np.zeros((nU, nT))
        np.add.at(out, (self.data.u[m], self.data.t[m]), self.data.y[m])
        return out

    def observed_by_group(self, leaves: np.ndarray) -> np.ndarray:
        out = np.zeros(self.data.N.shape)
        m = np.isin(self.data.e, leaves)
        np.add.at(out, (self.data.u[m], self.data.t[m], self.data.g[m]), self.data.y[m])
        return out

    def refit(self, data: BlockData, hc: torch.Tensor | None | type(...) = ..., tau_scale: dict | None = None,
              off: torch.Tensor | None | type(...) = ...) -> Monolith:
        """This model's mean refitted on other counts of the same lattice (a planted world, a held-out locus), from
        this fit's MAP at this fit's strengths and dispersion, to the production fit's closing tolerance. Re-learning
        the strengths changed what a refit absorbs by under 0.001 (evaluation 2026-10-06, absorption) at 3–5 times
        the cost."""
        from . import solver

        if self.rank:
            raise NotImplementedError("a refit of the interaction's model is not built")
        m2 = Monolith(data, self.graph, self.graph_kind, device=str(self.device), prior=self.prior)
        for n, c in m2.components.items():
            c.tau = self.components[n].tau * (tau_scale or {}).get(n, 1.0)
        with torch.no_grad():
            for n, v in self.params.items():
                m2.params[n].copy_(v)
        # the category courses as a fixed offset of this mean: by default this fit's own (a world drawn from a robust
        # fit and refitted without them read every category's course as a departure: 25–39 findings per null world,
        # 2026-10-07); `robust`'s alternation passes its own
        m2.hc = self.hc if hc is ... else hc
        m2.off = self.off if off is ... else off  # N2's offset likewise (`laplace.marginal` passes its own)
        solver.fit_mean(m2, iterations=30, loglik_tol=1.0)
        m2._solver_v1 = None        # the solver and the model refer to each other: a world's factor freed with it, not
        m2.phi = self.phi           # at the next full collection (a grid of worlds held 17 GB, 2026-10-06)
        return m2

    def robust(self, rounds: int = 2, trim: float = 0.005, min_expected: float = 0.05, log=print,
               max_sweeps: int = 5, sweep_tol: float = 0.05, footprints: tuple[float, ...] = (),
               courses: bool = False) -> Monolith:
        """This fit made robust to the departures stage C must report (docs/plans/2026-10-07-robust-expectation.md):
        each round flags the leaf × place × period cells beyond the predictive's upper ``trim`` quantile (their
        observed totals against NB(μ, φ_x), φ_x the leaf-place-period dispersion by trimmed likelihood, so the flags
        are not judged by a dispersion the outliers inflated), imputes their counts by the current expectation (EM for
        missing cells: the fit converges to the one on the other cells) and refits from this MAP at these strengths.
        The block's φ is re-estimated on the imputed counts, and the observed counts are restored for the surprises.

        Why (evaluation 2026-10-07, real events): fitted on every cell, chapter I's φ was about 0.1 and its categories'
        levels were set with their epidemic years; measles was expected at 200–300 admissions a year against 33–83
        observed outside 2018–19, and every stage-C method missed it."""
        import dataclasses

        from scipy import stats as st

        from .surprise import place_year_phi

        d = self.data
        E, (U, T) = len(d.leaves), d.N.shape[:2]
        obs = np.zeros((E, U, T))
        np.add.at(obs, (d.e, d.u, d.t), d.y)
        m, info = self, []
        # round 0 fits the structure (the category courses) on the observed counts and flags nothing: trimming judges
        # cells against an expectation, and before the courses exist a category in a group another dominates is
        # mis-expected everywhere; its ordinary counts were flagged as excesses, imputed away, and the courses then fit
        # the imputed zeros (B25–B33 expected near zero in ordinary years, 2026-10-07). Structure first, trimming second
        # ``courses`` (off by default): each category's own time course, fitted with the mean (`fit_category_courses`).
        # On the documented events the plain robust fit found all five by three methods or more; with flexible
        # courses (v7) a category-wide epidemic became its own course (measles 2018–19 expected at 876 and 830 against
        # 891 and 833) and with smooth ones (v8) COVID-19 lifted B34's level fifteenfold in every ordinary year. The
        # courses fix the siblings of a category that dominates its group (B25–B33 under COVID-19). Which reference a
        # question takes, the background or the category's own course, is the question registry's to declare
        # (evaluation 2026-10-07, robust expectation)
        for r in range(0 if courses else 1, rounds + 1):
            if not courses:
                mu = np.stack([m.expected(np.array([e]))[0] for e in range(E)])        # [E, U, T]
                live = (mu >= min_expected) | (obs > 0)
                o, mm = obs[live][:, None], mu[live][:, None]
                phi_x = place_year_phi(o, mm, np.full(o.shape, np.inf), trim=trim)
                k = float(phi_x) if np.isfinite(phi_x) else 1e12
                p = st.nbinom.sf(obs - 1, k, k / (k + np.maximum(mu, 1e-12)))
                flag = (p < trim) & (obs > mu)
                flag |= self._regional_flags(obs, mu, k, trim, footprints)
                info.append({"round": r, "phi_x": round(k, 3), "cells_flagged": int(flag.sum()),
                             "events_flagged": float(obs[flag].sum()), "expected_there": float(mu[flag].sum())})
                log(f"robust round {r}: φ_x {k:.3g}, {int(flag.sum())} leaf-place-periods flagged "
                    f"({obs[flag].sum():.0f} events against {mu[flag].sum():.0f} expected)")
                m = self.refit(m._impute(d, flag), hc=None)
                continue
            if r == 0:
                y_new = d.y.astype(float)
                info.append({"round": 0, "structure": True})
                log("robust round 0: structure (category courses) on the observed counts")
            else:
                y_new = None
            mu = np.stack([m.expected(np.array([e]))[0] for e in range(E)]) if r else None   # [E, U, T]
            flag = None
            if r:
                live = (mu >= min_expected) | (obs > 0)
                o, mm = obs[live][:, None], mu[live][:, None]
                phi_x = place_year_phi(o, mm, np.full(o.shape, np.inf), trim=trim)
                k = float(phi_x) if np.isfinite(phi_x) else 1e12
                p = st.nbinom.sf(obs - 1, k, k / (k + np.maximum(mu, 1e-12)))
                flag = (p < trim) & (obs > mu)
                cells = int(flag.sum())
                flag |= self._regional_flags(obs, mu, k, trim, footprints)
                dw = m._impute(d, flag)
                info.append({"round": r, "phi_x": round(k, 3), "cells_flagged": int(flag.sum()), "by_cell": cells,
                             "events_flagged": float(obs[flag].sum()), "expected_there": float(mu[flag].sum())})
                log(f"robust round {r}: φ_x {k:.3g}, {int(flag.sum())} leaf-place-periods flagged "
                    f"({obs[flag].sum():.0f} events against {mu[flag].sum():.0f} expected)")
            # the mean and the category courses by alternation, each given the other (block coordinate descent on a
            # convex objective, so it reaches the joint optimum): a course fitted once after the mean cannot move the
            # group's course, and a category that dominates its group (COVID-19 in B25–B34) left its siblings with an
            # expectation near zero in ordinary years (2026-10-07)
            if r == 0:
                dw = dataclasses.replace(d, y=y_new)

            # the structure round fits the time courses smooth (the group's at 10³ its strength), so no epidemic becomes
            # a course before the first trimming can see it; the trimming rounds refit at the learned strengths
            smooth = {"h_grp": 1e3, "h_all": 1e3} if r == 0 else None

            def course_map(model, h, dw=dw, flag=flag, smooth=smooth):
                """One sweep: the mean refitted with the courses ``h`` as an offset (warm, from ``model``'s MAP), then
                the courses given it."""
                nxt = model.refit(dw, hc=h, tau_scale=smooth)
                nxt.category_courses = nxt.fit_category_courses(d.y, missing=flag, data=d, log=lambda _x: None,
                                                                taus=[1e3] if smooth else None)
                return nxt, nxt.hc

            # the fixed point of the sweep map, accelerated by SQUAREM (Varadhan & Roland 2008): two sweeps, an
            # extrapolation along their drift, one stabilising sweep. The plain sweeps converged linearly at a rate
            # near 0.9 per sweep on SIM I (0.63, 0.36, 0.23, 0.15, 0.10, 0.079, 0.073, 0.068, … 2026-10-07)
            m, h0 = course_map(m, m.hc)
            prev = np.log(np.maximum(m.course_totals, 1e-9))
            for sweep in range(max_sweeps):
                m1, h1 = course_map(m, h0)
                m2, h2 = course_map(m1, h1)
                rr, vv = h1 - h0, h2 - 2 * h1 + h0
                nv = float(vv.norm())
                alpha = -float(rr.norm()) / nv if nv > 0 else -1.0
                alpha = min(max(alpha, -4.0), -1.0)           # α = −1 is the plain double sweep; −4 bounds the step
                h_ext = h0 - 2 * alpha * rr + alpha ** 2 * vv
                m, h0 = course_map(m2, h_ext)
                tot = np.log(np.maximum(m.course_totals, 1e-9))
                # the predictions, not the split, and only where they hold an event: a category expected at 0.001
                # moving to 0.004 is 1.4 on the log scale and no change to anything read
                held = (np.exp(tot) >= 1.0) | (np.exp(prev) >= 1.0)
                moved = float(np.abs(tot - prev)[held].max()) if held.any() else 0.0
                prev = tot
                log(f"  squarem {sweep}: course moved {moved:.3g}, α {alpha:.2f}, τ {m.category_courses['tau']:.3g}")
                if moved < sweep_tol:
                    break
        m.phi = m._dispersion()
        m.data = d
        m.robust_info = info
        m.robust_tag = {"rounds": rounds, "trim": trim, "min_expected": min_expected, "v": 9, "courses": courses}
        log(f"robust: φ {self.phi:.3g} -> {m.phi:.3g}")
        return m

    def fit_category_courses(self, y: np.ndarray | None = None, taus: np.ndarray | None = None,
                             centre: float = 1e4, missing: np.ndarray | None = None, data: BlockData | None = None,
                             log=print) -> dict:
        """Each category's own time course h_cat[e, t] (docs/plans/2026-10-07-robust-expectation.md, step 4): given
        every other effect, the category's yearly totals O[e, t] (of ``y``, the cells' counts; None: the data's) are
        Poisson(M[e, t] e^{h[e, t]}), M the expectation without the course; h has an RW2 prior of precision τ shared
        by the block and is centred over periods (a penalty ``centre`` on its mean: the course is a shape, the level
        stays the category's θ_cat; a free level drifted between the two from sweep to sweep and the alternation of
        `robust` never settled, 2026-10-07), τ chosen by the Laplace marginal likelihood summed over the categories.
        RW2, not RW1: a background is a smooth course and an epidemic a one- or two-year spike, the separation of
        the outbreak-detection baselines (Farrington et al. 1996; Noufaily et al. 2013). Under RW1 the measles course
        followed 2018–19 itself (876 and 830 expected against 891 and 833 observed).
        ``missing`` [E, U, T] marks cells left out of both totals (`robust`'s flagged departures): the exact likelihood
        of the courses without them, where imputing them by the expectation (an EM step) converged slowly and let a
        course follow half of yellow fever's 2017–18 outbreak. A category whose epidemic dominates its ICD group's
        course (COVID-19 in B25–B34, dengue over yellow fever in A90–A99) otherwise inherits that course in every
        ordinary year. Sets ``self.hc``."""
        d = self.data if data is None else data         # the observed cells (`robust` refits on imputed ones)
        E, T = len(d.leaves), d.N.shape[1]
        obs = np.zeros((E, T))
        yy = d.y if y is None else y
        keep = np.ones(len(yy), bool) if missing is None else ~missing[d.e, d.u, d.t]
        np.add.at(obs, (d.e[keep], d.t[keep]), yy[keep])
        saved, self.hc = self.hc, None
        with torch.no_grad():
            x = self.effects()
            lp = self._leaf_place(x)                                              # [E, U]
            pt = self._place_time(x)                                              # [K, U, T]
            M = torch.einsum("eu,eut->et", lp, pt[self.grp]).cpu().numpy()       # [E, T]
            if missing is not None:
                miss = torch.as_tensor(missing, dtype=lp.dtype, device=lp.device)
                M = M - torch.einsum("eut,eu,eut->et", miss, lp, pt[self.grp]).cpu().numpy()
            if self.ix_on:
                M = np.stack([self.expected(np.array([e]))[0].sum(0) for e in range(E)])
        if self.supply is not None:
            M = np.stack([self.expected(np.array([e]))[0].sum(0) for e in range(E)])
        self.hc = saved
        D = np.diff(np.eye(T), n=2, axis=0)            # RW2: curvature penalised, a slow trend free
        R = D.T @ D
        M = np.maximum(M, 1e-12)

        def fit(tau: float) -> tuple[np.ndarray, float]:
            P = tau * R + centre * np.ones((T, T)) / T ** 2 + 1e-8 * np.eye(T)
            h = np.zeros((E, T))
            for _ in range(50):
                lam = M * np.exp(h)
                g = obs - lam - h @ P
                H = lam[:, :, None] * np.eye(T)[None] + P[None]
                step = np.linalg.solve(H, g[..., None])[..., 0]
                h = h + np.clip(step, -5, 5)
                if np.abs(step).max() < 1e-8:
                    break
            lam = M * np.exp(h)
            H = lam[:, :, None] * np.eye(T)[None] + P[None]
            ll = float(np.sum(obs * np.log(lam) - lam - special.gammaln(obs + 1)))
            sign, logdet_p = np.linalg.slogdet(P)
            lml = ll - 0.5 * float(np.einsum("et,ts,es->", h, P, h)) + 0.5 * E * logdet_p \
                - 0.5 * float(np.linalg.slogdet(H)[1].sum())
            return h, lml

        grid = np.logspace(-2, 4, 25) if taus is None else np.asarray(taus, dtype=float)
        best = max(((fit(tau), tau) for tau in grid), key=lambda r: r[0][1])
        (h, lml), tau = best
        self.hc = torch.as_tensor(h, dtype=self.dtype, device=self.device)
        self.course_totals = M * np.exp(h)          # each category's predicted total per period [E, T]
        info = {"tau": float(tau), "lml": round(lml, 2), "max_abs": round(float(np.abs(h).max()), 3)}
        log(f"category courses: τ {tau:.3g}, max |h| {info['max_abs']}")
        return info

    def _impute(self, d: BlockData, flag: np.ndarray) -> BlockData:
        """The block's counts with every flagged leaf × place × period replaced by its expectation over its sex-age
        groups (EM for missing cells), zero counts included: scaling only the non-empty entries left a flagged
        region's empty cells at zero, below their expectation, and pulled the background down."""
        import dataclasses

        f = flag[d.e, d.u, d.t]
        keep = ~f
        parts_e, parts_u, parts_t, parts_g, parts_y = [d.e[keep]], [d.u[keep]], [d.t[keep]], [d.g[keep]], [d.y[keep].astype(float)]
        for e in np.unique(np.nonzero(flag)[0]):
            uu, tt = np.nonzero(flag[e])
            mg = self.expected_by_group(np.array([e]))[uu, tt]                     # [n, G]
            ii, gg = np.nonzero(mg > 0)
            parts_e.append(np.full(len(ii), e, dtype=d.e.dtype))
            parts_u.append(uu[ii].astype(d.u.dtype))
            parts_t.append(tt[ii].astype(d.t.dtype))
            parts_g.append(gg.astype(d.g.dtype))
            parts_y.append(mg[ii, gg])
        return dataclasses.replace(d, e=np.concatenate(parts_e), u=np.concatenate(parts_u), t=np.concatenate(parts_t),
                                   g=np.concatenate(parts_g), y=np.concatenate(parts_y))

    def _regional_flags(self, obs: np.ndarray, mu: np.ndarray, k: float, trim: float,
                        footprints: tuple[float, ...]) -> np.ndarray:
        """[E, U, T] cells inside a regional excess: a cell is flagged when, at some heat-kernel scale on the place
        graph (`multiscale`), the kernel-weighted count around it is a discovery of BH at q = 0.05 over every centre
        and period of that scale (its gamma upper-tail probability); the region-period is then missing whole.
        Tested at the cells' own level (0.005) instead, chance alone marked hundreds of regions over ~50,000 tests
        per scale and trimmed 33,677 cells of SIM I against 8,358 by cells alone (2026-10-07).

        **Off by default** (``footprints=()`` in `robust`): with BH and whole regions missing the flags still grew
        round after round (SIM I: 48,195 then 161,661 cells), because this null takes cells as independent while
        N1's spatial share makes neighbourhood aggregates more variable; trimming the regions it over-calls lowers
        the background and calls more. A calibrated regional null (the replicates with N1's spatial noise of
        `multiscale.peaks`) is the debt; until then diffuse outbreaks are partly absorbed (yellow fever 2017–18:
        expected 44 and 76 deaths against 195 and 257 observed, still a 3–4× departure). Diffuse outbreaks of one or two events per place pass a
        cell-by-cell trim (yellow fever 2017–18: p ≈ 0.01 per cell) and lifted the category's course."""
        import torch as th

        from . import multiscale

        if not footprints:
            return np.zeros(obs.shape, bool)
        E, U, T = obs.shape
        sp = getattr(self, "_spectrum", None)
        if sp is None:
            sp = self._spectrum = multiscale.GraphSpectrum(self.graph[0], U, self.graph[1])
        Ob = th.as_tensor(obs.transpose(1, 0, 2).reshape(U, E * T), dtype=th.float32)
        M = th.as_tensor(mu.transpose(1, 0, 2).reshape(U, E * T), dtype=th.float32)
        V = M + M * M / max(k, 1e-9)
        from . import control

        out = np.zeros((U, E * T), dtype=bool)
        for s in sp.scales(footprints):
            K = sp.kernel(s).cpu()
            z = multiscale.tail_z(K @ Ob, K @ M, (K * K) @ V)
            p = th.special.ndtr(-z.double()).numpy()
            live = (M.numpy() > 0)
            sel = np.zeros(p.shape, dtype=bool)
            sel[live] = control.bh(p[live], 0.05)
            out |= sel
        # the region-period is missing whole, its cells below their expectation too: keeping only the cells above it
        # selected the upper half of the region's noise, pulled the background down and let the flags grow round after
        # round (SIM I: 15,636 then 27,011 cells, 2026-10-07)
        return out.reshape(U, E, T).transpose(1, 0, 2)

    def robust_stored(self, rounds: int = 2, trim: float = 0.005, min_expected: float = 0.05, log=print) -> Monolith:
        """`robust`, read from the store when it was made before (its own key: the fit's plus the robust settings),
        else made and stored."""
        tag = {"rounds": rounds, "trim": trim, "min_expected": min_expected, "v": 9, "courses": False}   # v9: trimming only
        key = {**self.key(), "robust": tag}
        arrays, meta = store.get_arrays("monolith", key), store.manifest("monolith", key)
        if arrays is not None and meta is not None:
            with torch.no_grad():
                for k, v in arrays.items():
                    if k in self.params:
                        self.params[k].copy_(torch.as_tensor(v))
            self.phi = float(meta["phi"])
            self.robust_info = meta.get("robust_info")
            self.robust_tag = tag
            if "h_cat" in arrays:
                self.hc = torch.as_tensor(arrays["h_cat"], dtype=self.dtype, device=self.device)
            return self
        m = self.robust(rounds, trim, min_expected, log=log)
        arrays = {k: v.detach().cpu().numpy() for k, v in m.params.items()}
        if m.hc is not None:
            arrays["h_cat"] = m.hc.detach().cpu().numpy()
        store.put_arrays("monolith", m.key(), arrays, {**m.summary(), "robust_info": m.robust_info})
        return m

    def without(self, cells: np.ndarray) -> Monolith:
        """The fit with the place-period ``cells`` ([U, T] boolean) held out: their exposure and counts removed for
        every leaf of the block, the mean refitted (`refit`), and the result predicting at the full exposure again.
        A departure there is then read against a fit that never saw it: in-sample, a refit absorbs 9–63 % of one by
        its locus (ARCHITECTURE §10.3; the masking that outbreak baselines correct, Farrington, Noufaily 2013)."""
        d = self.data
        N = d.N.copy()
        N[cells] = 0.0
        keep = ~cells[d.u, d.t]
        held = dataclasses.replace(d, N=N, e=d.e[keep], u=d.u[keep], t=d.t[keep], g=d.g[keep], y=d.y[keep],
                                   key={**d.key, "held_out": int(cells.sum())})
        m2 = self.refit(held)
        m2.N = self.N                       # predict at the real exposure; the counts stay the held-out ones
        return m2

    def summary(self) -> dict:
        d = self.data
        bym = {}
        for level in ("all", "grp"):
            s, v = self.components[f"s_{level}"].tau, self.components[f"v_{level}"].tau
            bym[level] = {"rho": (1 / s) / (1 / s + 1 / v), "sd": float(np.sqrt(1 / s + 1 / v))}
        return {"block": d.block, "dataset": d.dataset, "graph": self.graph_kind, "years": [int(d.years[0]), int(d.years[-1])],
                "leaves": len(d.leaves), "groups": len(d.groups), "places": len(d.places),
                "events": float(d.y.sum()), "nonempty_cells": int(len(d.y)), "unallocated": d.unallocated,
                "phi": self.phi, "dispersion_check": getattr(self, "dispersion_check", None), "taus": {k: c.tau for k, c in self.components.items()}, "spatial_share": bym,
                "fit_seconds": self.history[-1]["seconds"] if self.history else None,
                "outers": len(self.history), "converged": getattr(self, "converged", None),
                "stop_reason": getattr(self, "stop_reason", None), "rank": self.rank, "centring": CENTRING}

    # ---- persistence -------------------------------------------------------------

    def key(self) -> dict:
        return {**self.data.key, "graph": self.graph_kind, **({"rank": self.rank} if self.rank else {}),
                **({"prior": self.prior} if self.prior != "gaussian" else {}),
                **({"likelihood": self.likelihood} if self.likelihood != "poisson" else {}),
                **({"robust": self.robust_tag} if getattr(self, "robust_tag", None) else {})}

    def save(self) -> None:
        arrays = {k: v.detach().cpu().numpy() for k, v in self.params.items()}
        if self.ix_on:
            arrays["ix_active"] = self.ixl.cpu().numpy()
        for name in HS if self.prior == "horseshoe" else ():
            arrays[f"hs_{name}"] = self.components[name].shape.Q.diagonal()
        store.put_arrays("monolith", self.key(), arrays, self.summary())

    @classmethod
    def load(cls, dataset: str, event: str, block: str, years: range | list[int],
             graph_kind: str = "contiguity", profile: str = "block", device: str = "cpu", rank: int = 0,
             geography: str | None = "group", geo_pool: float = GEO_POOL,
             prior: str = "gaussian", **source) -> Monolith:
        """A fitted block from the store (its data re-assembled from the gateway's cache). ``rank`` is the
        interaction's R (0: the base model)."""
        from . import graphs

        data = assemble(dataset, event, block, years, profile, geography=geography, geo_pool=geo_pool, **source)
        model = cls(data, graphs.graph(data.places, graph_kind), graph_kind, device=device, **({"rank": rank} if rank else {}),
                    **({"prior": prior} if prior != "gaussian" else {}))
        arrays = store.get_arrays("monolith", model.key())
        if rank and arrays is not None:
            model._enable_interaction(arrays.get("ix_active"))

        meta = store.manifest("monolith", model.key())
        if arrays is None or meta is None:
            raise LookupError(f"no fitted monolith for {model.key()}")
        with torch.no_grad():
            for k, v in _legacy_centring(arrays, meta).items():
                if k in model.params:
                    model.params[k].copy_(torch.as_tensor(v))
        for k, tau in meta["taus"].items():
            model.components[k].tau = float(tau)
        for name in HS if prior == "horseshoe" else ():
            model._set_weights(name, arrays[f"hs_{name}"])
        model.phi = float(meta["phi"]) if meta.get("phi") is not None else float("nan")
        model._restore(meta)
        model.history = [{"seconds": meta.get("fit_seconds")}]
        return model

    def _restore(self, meta: dict) -> None:
        """Model-specific state beyond parameters and τ's (none for counts)."""


class MarkModel(Monolith):
    """A positive continuous mark (ARCHITECTURE §4.4): log m ~ N(ν, ς²) per event, with ν the
    same linear predictor as the counts' η (levels, profiles, history, geography), without
    exposure. Each non-empty cell carries n events, l1 = Σ log m and l2 = Σ (log m)², so its
    mean log ȳ = l1/n has variance σ²_w/n + σ²_c: σ²_w within cells (from l2), σ²_c a cell-level
    component learned from the residuals. Marks exist only where events do: there are no
    empty cells and no factorised total; the likelihood is a weighted Gaussian over the
    non-empty cells."""

    # on the log mark's scale an effect of sd 0.01 is 1 % of a birth weight (about 30 g): the threshold is sd < 0.001
    shrunk = 1e6

    def __init__(self, data: BlockData, graph: tuple[np.ndarray, np.ndarray], graph_kind: str,
                 device: str = "cpu"):
        if data.n is None:
            raise ValueError("a mark model needs mark data (assemble(..., source='mark'))")
        super().__init__(data, graph, graph_kind, device)
        self.logN_nnz = torch.zeros_like(self.logN_nnz)        # no exposure: η is the mean log mark
        n = data.n
        within = float(np.sum(data.l2 - n * data.y ** 2) / max(np.sum(n - 1), 1.0))  # l1²/n = n·ȳ²
        self.sigma2_w = max(within, 1e-12)
        self.sigma2_c = 0.1 * self.sigma2_w
        self.n_t = torch.as_tensor(n, dtype=self.dtype, device=self.device)
        self.scale = float(np.sum(n))
        self._weights()

    def _weights(self) -> None:
        self.w = 1.0 / (self.sigma2_w / self.n_t + self.sigma2_c)

    def objective(self) -> torch.Tensor:
        x = self.effects()
        r = self.y - self.eta_nnz(x)
        return (0.5 * (self.w * r * r).sum() + self.penalty(x)) / float(self.w.sum())

    def cell_derivatives(self, eta: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Per non-empty cell, the first and second derivative of the objective's data term in η (log-likelihood
        units): the v1 solver's weights (`solver.StructuredNewton._mark_factors`). Gaussian: w(η − ȳ) and w."""
        return self.w * (eta - self.y), self.w.clone()

    def _objective_norm(self) -> float:
        return float(self.w.sum())

    def _initialise(self) -> None:
        d = self.data
        with torch.no_grad():
            self.params["b0"].fill_(float(np.sum(d.n * d.y) / np.sum(d.n)))

    def fit(self, outer: int = 25, inner: int = 30, tol: float = 0.02, log=print, warm=None, mean_tol: float = 0.0,
            **_ignored) -> MarkModel:
        start = time.time()
        self._laml_prev = self.laml = self._tau_radius = self._tau_sign = None
        self._initialise()
        self.warm_info = self.warm_start(warm) if warm else None
        for it in range(outer):
            self._mean(inner, loglik_tol=mean_tol)
            changes = self._update_taus()
            old = self.sigma2_c
            self.sigma2_c = self._cell_variance()
            self._weights()
            changes.append(abs(np.log(max(self.sigma2_c, 1e-12) / max(old, 1e-12))))
            self.history.append({"iteration": it, "taus": {k: c.tau for k, c in self.components.items()},
                                 "sigma2_c": self.sigma2_c, "seconds": time.time() - start})
            taus = " ".join(f"{k}={c.tau:.3g}" for k, c in self.components.items())
            log(f"outer {it}: max change {max(changes):.3f}, σ²_w {self.sigma2_w:.4g} σ²_c {self.sigma2_c:.4g}, "
                f"{time.time() - start:.0f}s | {taus}")
            if max(changes) < tol:
                break
        self._mean(inner)
        self.phi = float("nan")
        return self

    def _cell_variance(self) -> float:
        """σ²_c by moments: E[(ȳ − ν)²] = σ²_w/n + σ²_c, cells weighted by n."""
        with torch.no_grad():
            r = (self.y - self.eta_nnz(self.effects())).cpu().numpy()
        n = self.data.n
        return float(max(np.sum(n * (r ** 2 - self.sigma2_w / n)) / np.sum(n), 1e-8))

    def expected(self, leaves: np.ndarray, spatial: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """For a set of leaves: the n-weighted mean of ν over each (u, t)'s non-empty cells, and
        the variance of the observed mean log there, (σ²_w Σn + σ²_c Σn²)/(Σn)²."""
        d = self.data
        with torch.no_grad():
            nu = self.eta_nnz(self.effects(), spatial).cpu().numpy()
        m = np.isin(d.e, leaves)
        U, T = d.N.shape[:2]
        sn, snn, snu = np.zeros((U, T)), np.zeros((U, T)), np.zeros((U, T))
        np.add.at(sn, (d.u[m], d.t[m]), d.n[m])
        np.add.at(snn, (d.u[m], d.t[m]), d.n[m] ** 2)
        np.add.at(snu, (d.u[m], d.t[m]), d.n[m] * nu[m])
        mean = np.divide(snu, sn, out=np.full((U, T), np.nan), where=sn > 0)
        var = np.divide(self.sigma2_w * sn + self.sigma2_c * snn, sn ** 2, out=np.full((U, T), np.nan), where=sn > 0)
        return mean, var

    def observed(self, leaves: np.ndarray) -> np.ndarray:
        """The observed mean log mark per (u, t) over the leaves' cells (NaN where no event)."""
        d = self.data
        m = np.isin(d.e, leaves)
        U, T = d.N.shape[:2]
        sn, sl = np.zeros((U, T)), np.zeros((U, T))
        np.add.at(sn, (d.u[m], d.t[m]), d.n[m])
        np.add.at(sl, (d.u[m], d.t[m]), d.n[m] * d.y[m])
        return np.divide(sl, sn, out=np.full((U, T), np.nan), where=sn > 0)

    def events(self, leaves: np.ndarray) -> np.ndarray:
        d = self.data
        m = np.isin(d.e, leaves)
        out = np.zeros(d.N.shape[:2])
        np.add.at(out, (d.u[m], d.t[m]), d.n[m])
        return out

    def summary(self) -> dict:
        out = super().summary()
        out.update({"kind": "mark", "events": float(np.sum(self.data.n)), "sigma2_w": self.sigma2_w,
                    "sigma2_c": self.sigma2_c, "phi": None})
        return out

    def _restore(self, meta: dict) -> None:
        self.sigma2_w, self.sigma2_c = float(meta["sigma2_w"]), float(meta["sigma2_c"])
        self._weights()


class _CellMark(MarkModel):
    """The mark models that are not log-normal (ARCHITECTURE §4.4): a count-valued mark and a binary share. Each cell
    (e, u, t, g) carries n events and an accumulator; ν = η is the *link* of the cell's mean (the same linear predictor as
    the counts', without exposure). The likelihood is a quasi-likelihood of the family, every cell weighted by its
    over-dispersion at the previous outer iteration (``_weights``); the dispersion is estimated by moments, as the
    log-normal's cell variance is. A place-year's observed value, expectation and variance are on the family's y scale
    (``observed``, ``expected``), which is where the lenses read a departure."""

    shrunk = SHRUNK              # logit and log-mean scales, as the counts'
    family = ""
    dispersion_name = ""
    disp = 0.0                 # the family's dispersion; 0 until the first outer iteration
    mu_c = None                # each cell's mean at the previous outer iteration

    def __init__(self, data: BlockData, graph: tuple[np.ndarray, np.ndarray], graph_kind: str, device: str = "cpu"):
        super().__init__(data, graph, graph_kind, device)
        self.total_t = torch.as_tensor(data.y * data.n, dtype=self.dtype, device=self.device)   # Σ m (a count) or k (successes)
        self.mu_c = torch.full_like(self.n_t, float(data.y @ data.n / data.n.sum()))
        self._weights()

    def _weights(self) -> None:
        raise NotImplementedError

    def _objective_norm(self) -> float:
        return self.scale

    def _initialise(self) -> None:
        raise NotImplementedError

    def _moment(self) -> float:
        """The dispersion by moments at the current fit."""
        raise NotImplementedError

    def fit(self, outer: int = 25, inner: int = 30, tol: float = 0.02, log=print, warm=None, mean_tol: float = 0.0,
            **_ignored) -> _CellMark:
        start = time.time()
        self._laml_prev = self.laml = self._tau_radius = self._tau_sign = None
        self._initialise()
        self.warm_info = self.warm_start(warm) if warm else None
        for it in range(outer):
            self._mean(inner, loglik_tol=mean_tol)
            changes = self._update_taus()
            old = self.disp
            self.disp = self._moment()
            with torch.no_grad():
                self.mu_c = self._cell_mean().detach()
            self._weights()
            changes.append(abs(self.disp - old) / (self.disp + 0.01))
            self.history.append({"iteration": it, "taus": {k: c.tau for k, c in self.components.items()},
                                 self.dispersion_name: self.disp, "seconds": time.time() - start})
            taus = " ".join(f"{k}={c.tau:.3g}" for k, c in self.components.items())
            log(f"outer {it}: max change {max(changes):.3f}, {self.dispersion_name} {self.disp:.4g}, {time.time() - start:.0f}s | {taus}")
            if max(changes) < tol:
                break
        self._mean(inner)
        self.phi = float("nan")
        return self

    def _cell_mean(self) -> torch.Tensor:
        raise NotImplementedError

    def _sums(self, leaves: np.ndarray, *cols: np.ndarray) -> list[np.ndarray]:
        """Per (u, t), the sums over the cells of ``leaves`` of each column."""
        d = self.data
        m = np.isin(d.e, leaves)
        U, T = d.N.shape[:2]
        out = []
        for c in cols:
            a = np.zeros((U, T))
            np.add.at(a, (d.u[m], d.t[m]), c[m])
            out.append(a)
        return out

    def summary(self) -> dict:
        out = super().summary()
        out.update({"family": self.family, self.dispersion_name: self.disp})
        out.pop("sigma2_w", None)
        out.pop("sigma2_c", None)
        return out

    def _restore(self, meta: dict) -> None:
        self.disp = float(meta[self.dispersion_name])
        with torch.no_grad():
            self.mu_c = self._cell_mean().detach()
        self._weights()

    def events(self, leaves: np.ndarray) -> np.ndarray:
        return self._sums(leaves, self.data.n)[0]


class ShareModel(_CellMark):
    """A binary share (death in hospital, caesarean): k of n events carry the mark, logit p = ν. Beta-binomial by
    quasi-likelihood: the binomial score with each cell weighted 1/(1 + (n − 1)ρ), ρ the intra-cell correlation by
    moments. y is the empirical logit log((k + ½)/(n − k + ½)) of a place-year, its expectation and variance
    from the cells' p by the delta method."""

    family, dispersion_name = "share", "rho"

    def _weights(self) -> None:
        self.w = 1.0 / (1.0 + (self.n_t - 1.0) * self.disp)

    def _initialise(self) -> None:
        d = self.data
        p = float(np.clip(np.sum(d.y * d.n) / np.sum(d.n), 1e-6, 1 - 1e-6))
        with torch.no_grad():
            self.params["b0"].fill_(float(np.log(p / (1 - p))))

    def objective(self) -> torch.Tensor:
        x = self.effects()
        eta = self.eta_nnz(x)
        nll = (self.w * (self.n_t * torch.nn.functional.softplus(eta) - self.total_t * eta)).sum()
        return (nll + self.penalty(x)) / self.scale

    def cell_derivatives(self, eta: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        p = torch.sigmoid(eta)
        return self.w * (self.n_t * p - self.total_t), self.w * self.n_t * p * (1 - p)

    def _cell_mean(self) -> torch.Tensor:
        return torch.sigmoid(self.eta_nnz(self.effects()))

    def _moment(self) -> float:
        p = self._cell_mean().cpu().numpy().clip(1e-9, 1 - 1e-9)
        n, k = self.data.n, self.data.y * self.data.n
        r2 = (k - n * p) ** 2 / (n * p * (1 - p)) - 1.0
        return float(np.clip(np.sum((n - 1) * r2) / max(np.sum((n - 1) ** 2), 1.0), 0.0, 1.0))

    def expected(self, leaves: np.ndarray, spatial: bool = True) -> tuple[np.ndarray, np.ndarray]:
        d = self.data
        with torch.no_grad():
            p = torch.sigmoid(self.eta_nnz(self.effects(), spatial)).cpu().numpy()
        n = d.n
        N, K, V = self._sums(leaves, n, n * p, n * p * (1 - p) * (1 + (n - 1) * self.disp))
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = np.log((K + 0.5) / (N - K + 0.5))
            var = V * (1.0 / (K + 0.5) + 1.0 / (N - K + 0.5)) ** 2
        return np.where(N > 0, mean, np.nan), np.where(N > 0, var, np.nan)

    def observed(self, leaves: np.ndarray) -> np.ndarray:
        N, K = self._sums(leaves, self.data.n, self.data.y * self.data.n)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(N > 0, np.log((K + 0.5) / (N - K + 0.5)), np.nan)


class CountModel(_CellMark):
    """A count-valued mark (ICU days of the admissions that used ICU): per-event mean μ with log μ = ν and variance
    μ + μ²/θ, by quasi-likelihood on the cell sums (n, Σm): each cell weighted 1/(1 + μ/θ) at its previous μ, 1/θ by
    moments from Σm². y is the log of a place-year's mean count."""

    family, dispersion_name = "count", "inv_theta"

    def _weights(self) -> None:
        self.w = torch.ones_like(self.n_t) if self.mu_c is None else 1.0 / (1.0 + self.mu_c * self.disp)

    def _initialise(self) -> None:
        d = self.data
        with torch.no_grad():
            self.params["b0"].fill_(float(np.log(max(np.sum(d.y * d.n) / np.sum(d.n), 1e-9))))

    def objective(self) -> torch.Tensor:
        x = self.effects()
        eta = self.eta_nnz(x)
        nll = (self.w * (self.n_t * torch.exp(eta) - self.total_t * eta)).sum()
        return (nll + self.penalty(x)) / self.scale

    def cell_derivatives(self, eta: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        mu = torch.exp(eta)
        return self.w * (self.n_t * mu - self.total_t), self.w * self.n_t * mu

    def _cell_mean(self) -> torch.Tensor:
        return torch.exp(self.eta_nnz(self.effects()))

    def _moment(self) -> float:
        mu = self._cell_mean().cpu().numpy()
        n, s1, s2 = self.data.n, self.data.y * self.data.n, self.data.l2
        q = np.sum(s2 - 2 * mu * s1 + n * mu ** 2)
        return float(max((q - np.sum(n * mu)) / np.sum(n * mu ** 2), 0.0))

    def expected(self, leaves: np.ndarray, spatial: bool = True) -> tuple[np.ndarray, np.ndarray]:
        n = self.data.n
        with torch.no_grad():
            mu = torch.exp(self.eta_nnz(self.effects(), spatial)).cpu().numpy()
        N, S, V = self._sums(leaves, n, n * mu, n * mu * (1 + mu * self.disp))
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(N > 0, np.log(S / N), np.nan), np.where(N > 0, V / S ** 2, np.nan)

    def observed(self, leaves: np.ndarray) -> np.ndarray:
        N, S = self._sums(leaves, self.data.n, self.data.y * self.data.n)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(N > 0, np.log(S / N), np.nan)


def model_class(source: dict | None) -> type[Monolith]:
    """The model of a reader's source: counts by the Poisson-NB monolith, a mark by its family's (``mark``: log-normal)."""
    kind = (source or {}).get("source", "events")
    return {"mark": MarkModel, "count": CountModel, "share": ShareModel}.get(kind, Monolith)


# ---------------------------------------------------------------------- model choice


def extrapolate(model: Monolith, test: BlockData, history: str = "auto") -> tuple[Monolith, dict[str, torch.Tensor]]:
    """A fit carried to later periods: every effect as fitted, the histories h extrapolated.
    ``history`` chooses the forecast of h:
      linear    the RW2's forecast mean, linear from the last two fitted periods;
      damped5   the last slope damped by half each year (Gardner & McKenzie's damped trend; the annual default since
                2026-10-06: against linear, held out on seven SIM chapters, never worse by more than 0.001 per death
                over 2018-19 and better over 2022-23, where the straight line carried COVID-19's 2020-21 rise on and
                expected 33 times B25-B34's deaths; evaluation 2026-10-06, ICD structure);
      damped8   the same with 0.8;
      level     flat at the mean of the last twelve months;
      level36   flat at the mean of the last thirty-six months (the monthly default: on dengue 2019–23
                precision 0.57 -> 0.64 for recall 0.92 -> 0.91; median and robust reach precision 0.71
                but recall 0.81, missing the big epidemics of states that already had one in the fit,
                evaluation 2026-10-05, dengue baseline);
      median    flat at the median over the whole fit (a long memory that ignores epidemics as outliers);
      robust    flat at a Farrington-style reweighted mean over the whole fit: months more than one
                robust sd (1.4826 MAD) from the level get weight 1/r², iterated, so past epidemics
                are downweighted and the baseline is the endemic level.
    At the monthly grain h is free to follow epidemic waves (τ_h ≈ 0.002 on dengue), so the last two
    months' slope is noise that a 60-month horizon multiplies (evaluation 2026-10-05, dengue monthly).
    Returns a model over the test data (for its exposure and cells) and the forecast effects."""
    if not np.array_equal(test.places, model.data.places) or test.leaves != model.data.leaves \
            or test.groups != model.data.groups:
        raise ValueError("test data must share the fit's places, leaves and profile carriers")
    if test.outer_groups != model.data.outer_groups:
        # the geography carriers are the fit's: a pooled carrier (`geo_pool`) is decided on the fitted years' shares
        test = dataclasses.replace(test, group_outer=model.data.group_outer, outer_groups=model.data.outer_groups)
    tm = Monolith(test, model.graph, model.graph_kind, device=str(model.device), rank=model.rank)
    if model.ix_on:
        tm._enable_interaction(model.ixl.cpu().numpy())
    tm.phi = model.phi
    return tm, extrapolate_effects(model, tm, model.effects(), history)


def extrapolate_effects(model: Monolith, tm: Monolith, effects: dict[str, torch.Tensor],
                        history: str = "auto") -> dict[str, torch.Tensor]:
    """The effects (the fitted ones, or a posterior draw's) with their histories h carried over the
    test periods of ``tm`` (see `extrapolate`)."""
    monthly = model.data.grain == "month"
    if history == "auto":
        history = "level36" if monthly else "damped5"
    test = tm.data
    with torch.no_grad():
        x = {k: v.detach().clone() for k, v in effects.items()}
        if "ix_t" in x:      # the interaction's course is a random walk of order 1: its forecast mean is flat at the last value
            x["ix_t"] = x["ix_t"][:, -1:].expand(-1, test.N.shape[1]).clone()
        if monthly:
            # months after the last fitted month; the cyclic season repeats as fitted
            steps = torch.arange(1, test.N.shape[1] + 1, dtype=model.dtype, device=model.device)
        else:
            last = float(model.data.years[-1])
            steps = torch.as_tensor(test.years.astype(float) - last, dtype=model.dtype, device=model.device)
        if history == "linear" or (not monthly and history in ("level", "damped8", "damped5")):
            # annual grain: the RW2's forecast mean (linear), or its last slope damped by d per year
            # (damped8: d = 0.8; damped5: d = 0.5), or flat at the last value
            d = {"linear": 1.0, "level": 0.0, "damped8": 0.8, "damped5": 0.5}[history]
            reach = steps if d == 1.0 else (torch.zeros_like(steps) if d == 0.0
                                            else d * (1 - d ** steps) / (1 - d))
            for name in ("h_all", "h_grp"):
                h = x[name]
                slope = h[:, -1:] - h[:, -2:-1]
                x[name] = h[:, -1:] + slope * reach[None, :]
        else:
            H = (x["h_all"] + x["h_grp"]).cpu().numpy()                      # [groups, T]
            level = np.array([_baseline_level(row, history) for row in H])
            level = torch.as_tensor(level, dtype=model.dtype, device=model.device)[:, None]
            x["h_all"] = level.mean(dim=0, keepdim=True) + 0.0 * steps[None, :]
            x["h_grp"] = (level - level.mean(dim=0, keepdim=True)) + 0.0 * steps[None, :]
    return x


def regime_history(model: Monolith, history: str = "auto", purpose: str = "expectation") -> str:
    """BP's default history. The ``expectation`` (calibrated, for surprises; ADR-0009): ``climatology`` at the
    monthly grain, ``damped5`` at the annual one. The ``alarm`` baseline (ADR-0012): at the monthly grain the
    flat ``level36``, the mean of the last 36 months of h, which no past epidemic regime enters; at the annual
    grain the expectation's own single member (a damped slope has no epidemic regimes to leave out)."""
    if history != "auto":
        return history
    if model.data.grain == "month":
        return "level36" if purpose == "alarm" else "climatology"
    return "damped5"


def extrapolate_members(model: Monolith, tm: Monolith, history: str = "auto",
                        effects: dict[str, torch.Tensor] | None = None) -> list[tuple[float, dict[str, torch.Tensor]]]:
    """The regimes of the later periods: [(weight, effects)] whose mixture is BP's predictive of the history.
    ``auto`` (`regime_history`) is at the annual grain one member whose h carries the RW2's last slope damped
    by 0.5 per year (``damped5``), and at the monthly grain the ``climatology``: every year of the fit is a
    member, its twelve months of h (national and group) standing for the same months of a later year, equal
    weights. An epidemic series has no level to extrapolate and its epidemic years are normal ones. Rolling
    origins (evaluation 2026-10-05, BP level): annual, 7 fields at 2014, 2016, 2019, damped5 + place course
    held-out log score -1.37 M against -1.52 M for the linear forecast with the block's φ; monthly dengue at
    2014 and 2018, climatology -1.39 M against -4.68 M for level36 (obs/expected 1.2 against 2.2). Any other
    ``history`` is one member, `extrapolate_effects`."""
    monthly = model.data.grain == "month"
    history = regime_history(model, history)
    x0 = model.effects() if effects is None else effects
    if history != "climatology":
        return [(1.0, extrapolate_effects(model, tm, x0, history))]
    if not monthly:
        raise ValueError("the climatology of a fit's years is a monthly-grain regime")
    T, years = tm.data.N.shape[1], model.data.N.shape[1] // 12
    base = extrapolate_effects(model, tm, x0, "level36")
    members = []
    for j in range(years):
        idx = torch.as_tensor([12 * j + t % 12 for t in range(T)], device=model.device)
        x = dict(base)
        x["h_all"], x["h_grp"] = x0["h_all"][:, idx], x0["h_grp"][:, idx]
        members.append((1.0 / years, x))
    return members


def _baseline_level(h: np.ndarray, kind: str) -> float:
    """A flat baseline for a history h (log scale) over its fitted months."""
    if kind == "level":
        return float(h[-12:].mean())
    if kind == "level36":
        return float(h[-36:].mean())
    if kind == "median":
        return float(np.median(h))
    if kind == "robust":
        level = float(np.median(h))
        scale = max(1.4826 * float(np.median(np.abs(h - level))), 1e-6)
        for _ in range(50):
            r = np.abs(h - level) / scale
            w = np.where(r <= 1.0, 1.0, 1.0 / np.maximum(r, 1e-12) ** 2)
            new = float((w * h).sum() / w.sum())
            if abs(new - level) < 1e-8:
                break
            level = new
        return level
    raise ValueError(f"unknown history forecast {kind!r}")


def heldout(model: Monolith, test: BlockData, interaction: bool = True, history: str = "auto") -> dict:
    """Score a fit on later years (ARCHITECTURE §5.4): every effect as fitted, the histories
    h extrapolated by ``history`` (`extrapolate`; the annual default is the damped trend).
    Returns the Poisson deviance over every test cell (empty cells through the factorised
    total) and the NB log-likelihood of the non-empty cells at the fitted φ, and of every cell
    (``nb_loglik_all``, the empty ones through the factorised sum). ``interaction=False`` scores the same fit with
    its low-rank interaction switched off, which separates the term's gain from a better-converged base. ``history``
    is `extrapolate`'s forecast of the courses."""
    tm, x = extrapolate(model, test, history=history)
    if not interaction:
        x = {k: (torch.zeros_like(v) if k.startswith("ix_") else v) for k, v in x.items()}
    with torch.no_grad():
        eta = tm.eta_nnz(x)
        lam = float(tm.total(x))
        mu = torch.exp(eta).cpu().numpy()
    y = test.y
    dev = 2 * (float(np.sum(y * np.log(y / mu))) - float(y.sum()) + lam)
    phi = model.phi
    nb = float(np.sum(special.gammaln(y + phi) - special.gammaln(phi) - special.gammaln(y + 1)
                      + phi * np.log(phi / (phi + mu)) + y * np.log(mu / (phi + mu)))) if np.isfinite(phi) else None
    return {"deviance": dev, "events": float(y.sum()), "expected": lam, "deviance_per_event": dev / float(y.sum()),
            "nb_loglik_nonempty": nb, "nb_loglik_all": tm.nb_loglik(phi, x) if np.isfinite(phi) else None, "years": test.years.tolist(), "graph": model.graph_kind,
            "profile": test.key.get("profile", "group")}


# ---------------------------------------------------------------------- helpers


_FAMILY_DROP = {"years", "data", "through", "population", "population_model", "split", "rank", "prior"}


def _family(key: dict) -> dict:
    """What makes two stored fits the same model of the same events: the key without its years, exposure and split."""
    return {k: v for k, v in key.items() if k not in _FAMILY_DROP}


def _periods_of(key: dict) -> list[int]:
    return list(key["years"])


def _within_groups(leaf_group: np.ndarray, n: int) -> structures.Shape:
    """θ_cat: iid, centred within each group (the group carries the mean)."""
    return structures.Shape("iid_within", sp.identity(n, format="csr"), n - len(np.unique(leaf_group)),
                            centred=True, components=leaf_group)


def _legacy_centring(arrays: dict, meta: dict) -> dict:
    """Raw parameters stored under centring 1 rewritten so that the current centring gives the effects they were fitted
    as: the old centring applied to them (each sex's profile row and each iid place row to its own mean), which the
    current one then leaves as they are. Without it a stored fit's μ moved by a factor per sex on loading."""
    if meta.get("centring", 1) >= CENTRING:
        return arrays
    out = dict(arrays)
    for name in ("f_all", "f_grp", "v_all", "v_grp", "v_cat"):
        if name in out:
            v = np.asarray(out[name], dtype=np.float64)
            out[name] = v - v.mean(axis=1, keepdims=True)
    return out


def _centre(x: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    ncomp = int(labels.max()) + 1
    sums = torch.zeros((x.shape[0], ncomp), dtype=x.dtype, device=x.device).index_add_(1, labels, x)
    counts = torch.bincount(labels, minlength=ncomp).to(x.dtype)
    return x - (sums / counts)[:, labels]


def _torch_sparse(Q: sp.csr_matrix, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
    coo = Q.tocoo()
    idx = torch.as_tensor(np.vstack([coo.row, coo.col]), dtype=torch.int64)
    return torch.sparse_coo_tensor(idx, torch.as_tensor(coo.data, dtype=dtype), coo.shape,
                                   device=device).coalesce()


def _cached_icar(edges: np.ndarray, weights: np.ndarray, n: int) -> structures.Shape:
    key = {"what": "icar", "n": n, "edges": int(len(edges)), "hash": int(np.sum(edges[:, 0] * 7919 + edges[:, 1])),
           "w": round(float(np.sum(weights * (1 + edges[:, 0] % 97))), 6)}
    cached = store.get_arrays("structures", key)
    if cached is not None:
        Q = sp.csr_matrix((cached["data"], cached["indices"], cached["indptr"]), shape=(n, n))
        return structures.Shape("icar", Q, int(cached["rank"]), True, cached["components"])
    shape = structures.icar(edges, weights, n)
    store.put_arrays("structures", key, {"data": shape.Q.data, "indices": shape.Q.indices, "indptr": shape.Q.indptr,
                                         "rank": np.array(shape.rank), "components": shape.components})
    return shape
