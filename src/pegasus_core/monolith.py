"""The monolith: one hierarchical model of event intensities (ARCHITECTURE §4–§5).

For a block (one chapter of a classifier tree), leaves e (ICD categories),
places u, years t and groups g = sex × age band:

    y[e,u,t,g] ~ NegBin(μ, φ),   μ = N[u,t,g] · exp(η)
    η = b0 + θ_grp[p(e)] + θ_cat[e]                      levels along the tree
          + f_all[g] + f_grp[p(e), g]                     age–sex profiles (RW2 over age, per sex)
          + h_all[t] + h_grp[p(e), t]                     history (RW2 over years)
          + s_all[u] + v_all[u] + s_grp[p(e),u] + v_grp[p(e),u]   geography (scaled ICAR + iid: BYM)

p(e) is the leaf's ICD group (the profile and geography level). Every effect
is centred along its structure; every strength τ is learned by Fellner–Schall
updates (Wood & Fasiolo 2017) with a block-diagonal Hessian. The mean is fitted
by penalised Poisson likelihood through the factorised sum (§5.1): no empty
cell is ever formed. φ is estimated afterwards by moments (§5.2).
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import torch
from scipy import optimize, special

from . import config, control, gateway, store, structures

AGE_EDGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]  # 18 bands; last is 80+
N_BANDS = len(AGE_EDGES)
TAU_BOUNDS = (1e-8, 1e8)
MAX_TAU_STEP = np.log(10.0)  # Fellner–Schall updates are damped to ×10 per outer iteration
SHRUNK = 1e5                 # a τ above this leaves its effect at a negligible size (sd < 0.003)


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

    def periods(self) -> np.ndarray:
        """The time axis as period codes: the years, or YYYYMM at the monthly grain."""
        if self.grain == "month":
            return (np.repeat(self.years, 12) * 100 + np.tile(np.arange(1, 13), len(self.years))).astype(np.int64)
        return self.years


ASSEMBLY = 1    # bumped when what `_assemble` returns for the same inputs changes in a way the source hash cannot see


def assemble(dataset: str, event: str, block: str, years: range | list[int], profile: str = "group",
             source: str = "events", grain: str = "year", population: str | None = None, cache: bool = True,
             **source_args) -> BlockData:
    """One block's cells and populations, from the gateway, memoised in the store (kind ``blockdata``).

    The 10.7 M cells of SIH chapter X monthly took 467 s to assemble, and every variant of a fit (train and
    full, a rolling origin, a split, another exposure) re-read them. The entry is addressed by everything the
    assembly reads: its arguments, the data version, the population's key *and its content hash*, the
    assembly code (the hash of `_assemble`'s and `gateway`'s source, and `ASSEMBLY`), so a changed input or
    a changed reader is a different address and a stale entry is never served. The confirmation reserve is
    checked before the cache is read. ``cache=False`` assembles afresh and stores nothing."""
    control.check_reserved(dataset, years)
    if not cache:
        return _assemble(dataset, event, block, years, profile, source, grain, population, **source_args)
    ys = np.array(sorted(set(years)))
    population = population or config.population_source()
    pop = gateway.population(ys.tolist(), source=population)
    h = hashlib.sha256()
    for name in pop.column_names:
        h.update(np.ascontiguousarray(pop.column(name).to_numpy()).tobytes())
    key = {"what": "blockdata", "dataset": dataset, "event": event, "block": block, "years": ys.tolist(),
           "profile": profile, "source": source, "grain": grain, "args": source_args, "data": config.data_version(),
           **gateway.population_key(population), "population_hash": h.hexdigest()[:16], "assembly": _assembly_code()}
    arrays, meta = store.get_arrays("blockdata", key), store.manifest("blockdata", key)
    if arrays is not None and meta is not None:
        return _blockdata_from(arrays, meta)
    data = _assemble(dataset, event, block, years, profile, source, grain, population, **source_args)
    store.put_arrays("blockdata", key, *_blockdata_to(data))
    return data


@functools.cache
def _assembly_code() -> str:
    """The hash of the code a BlockData is a function of: the assembly and the gateway's readers."""
    h = hashlib.sha256(str(ASSEMBLY).encode())
    for fn in (_assemble, _index_of, age_band, _chapter):
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
    meta = {"dataset": d.dataset, "event": d.event, "block": d.block, "leaves": d.leaves, "groups": d.groups,
            "unallocated": d.unallocated, "data_key": d.key, "grain": d.grain, "population": d.population}
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
    if month:
        d.grain = "month"
        d.month_of_year = np.tile(np.arange(12), len(d.years))
    return d


def _assemble(dataset: str, event: str, block: str, years: range | list[int], profile: str = "group",
              source: str = "events", grain: str = "year", population: str | None = None, **source_args) -> BlockData:
    """One block's cells and populations, from the gateway.

    ``block`` is an ICD-10 chapter, or ``*`` for an event type without a classifier tree.
    ``profile`` is the tree level that carries profiles, history and geography: ``group``
    (the ICD block, pooling its categories) or ``category`` (each category its own).
    ``source`` chooses the gateway reader, each giving cells of (u, year, sex, age, code):

        events       counts of the event type (y)
        code_list    counts of events under each category of a code-list column, e.g.
                     SINASC's CODANOMAL (``column=``); the exposure is still the population
        mark         accumulator states of a numeric mark (``mark=``, ``bounds=``,
                     ``classifier=``): n, l1 = Σ log m, l2 = Σ (log m)²; y is l1/n
    """
    control.check_reserved(dataset, years)      # the confirmation reserve is read by claims only (ARCHITECTURE §8.3)
    years = np.array(sorted(set(years)))
    population = population or config.population_source()
    edges = gateway.age_edges(population)   # the population source fixes the age bands (never padded or split)
    nB = len(edges)
    pop = gateway.population(years.tolist(), source=population)
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
        tree = gateway.code_structure("ICD10")
        code, parent, level = (tree.column(c).to_pylist() for c in ("code", "parent", "level"))
        parent_of = dict(zip(code, parent, strict=True))
        level_of = dict(zip(code, level, strict=True))
    categories = (["*"] if block == "*" else
                  sorted(c for c, lv in level_of.items() if lv == "category" and _chapter(c, parent_of) == block))
    carrier = {c: (parent_of[c] if profile == "group" and parent_of[c] is not None else c) for c in categories}
    groups = sorted(set(carrier.values()))
    gidx = {g: i for i, g in enumerate(groups)}
    eidx = {c: i for i, c in enumerate(categories)}
    values = ("n", "l1", "l2") if source == "mark" else ("y",)
    weight = "n" if source == "mark" else "y"
    readers = {"events": gateway.event_counts, "code_list": gateway.code_list_counts, "mark": gateway.mark_moments}
    if grain == "month":
        if source != "events":
            raise NotImplementedError("the monthly grain reads event counts")
        readers["events"] = gateway.monthly_counts
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
           **({} if grain == "year" else {"grain": grain})}
    y = sums["l1"] / sums["n"] if source == "mark" else sums["y"]
    live = N[u, t, g] > 0
    if not live.all():
        # events in a cell the population holds nobody in (the account's interval-free zeros: 1 death in 14 years of IX):
        # no rate exists there, so they are counted as unallocated, never given a guessed denominator
        w = (sums["n"] if source == "mark" else y)[~live]
        unallocated["no population in the cell"] = unallocated.get("no population in the cell", 0) + int(w.sum())
        e, u, t, g, y = e[live], u[live], t[live], g[live], y[live]
        sums = {v: x[live] for v, x in sums.items()}
    data = BlockData(dataset, event, block, years, places, categories, groups,
                     np.array([gidx[carrier[c]] for c in categories]), N, e, u, t, g, y, unallocated, key,
                     S=S, population=population)
    if source == "mark":
        data.n, data.l2 = sums["n"], sums["l2"]
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

    @property
    def rank(self) -> float:
        """The effective rank: the shape's rank per row, less the dimensions that centring
        across rows removes (across groups: 1/nGrp of them; within groups: nGrp/nE)."""
        return self.shape.rank * self.batch * self.free


class Monolith:
    """One block's fitted model."""

    def __init__(self, data: BlockData, graph: tuple[np.ndarray, np.ndarray], graph_kind: str,
                 device: str = "cpu"):
        self.data = data
        self.graph_kind = graph_kind
        self.graph = graph
        self.device = torch.device(device)
        self.dtype = torch.float64
        nU, nT, nG = data.N.shape
        nE, nGrp = len(data.leaves), len(data.groups)
        icar = _cached_icar(graph[0], graph[1], nU)
        self.nB = nG // 2                      # age bands per sex (the population source's)
        rw_age = structures.random_walk(self.nB, order=2)
        rw_t = structures.random_walk(nT, order=2 if nT >= 4 else 1)
        self.components = {
            "th_grp": Component("th_grp", structures.iid(nGrp), 1),
            "th_cat": Component("th_cat", _within_groups(data.leaf_group, nE), 1),
            "f_all": Component("f_all", rw_age, 2),
            "f_grp": Component("f_grp", rw_age, nGrp * 2, free=(nGrp - 1) / nGrp),
            "h_all": Component("h_all", rw_t, 1),
            "h_grp": Component("h_grp", rw_t, nGrp, free=(nGrp - 1) / nGrp),
            "s_all": Component("s_all", icar, 1),
            "v_all": Component("v_all", structures.iid(nU), 1),
            "s_grp": Component("s_grp", icar, nGrp, free=(nGrp - 1) / nGrp),
            "v_grp": Component("v_grp", structures.iid(nU), nGrp, free=(nGrp - 1) / nGrp),
            "v_cat": Component("v_cat", structures.iid(nU), nE, free=(nE - nGrp) / nE),
        }
        if data.grain == "month":
            season = structures.random_walk(12, order=2, cyclic=True)
            self.components["c_all"] = Component("c_all", season, 1)
            self.components["c_grp"] = Component("c_grp", season, nGrp, free=(nGrp - 1) / nGrp)
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
        self.n_cells = float(nE * np.count_nonzero(data.N > 0))
        self.phi: float = float("inf")
        self.forcing = 0.5               # the largest relative residual CG stops at (Eisenstat–Walker cap)
        self.cg_iterations = 0           # conjugate-gradient iterations so far (the cost of the mean fit)
        self.newton_log: list[tuple] = []   # per Newton step: objective, gradient norm, CG iterations, step length, decrease
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
            "h_all": acc((1, nT), zero, d.t), "h_grp": acc((nGrp, nT), pe, d.t),
            "s_all": acc((1, nU), zero, d.u), "v_all": acc((1, nU), zero, d.u),
            "s_grp": acc((nGrp, nU), pe, d.u), "v_grp": acc((nGrp, nU), pe, d.u),
            "v_cat": acc((nE, nU), d.e, d.u),
        }
        if d.grain == "month":
            moy = d.month_of_year[d.t]
            self.Y["c_all"] = acc((1, 12), zero, moy)
            self.Y["c_grp"] = acc((nGrp, 12), pe, moy)
        self.y_offset = float(np.sum(y * np.log(d.N[d.u, d.t, d.g])))   # Σ y log N, constant

    # ---- effects (centred) -------------------------------------------------

    def effects(self, params: dict[str, torch.Tensor] | None = None) -> dict[str, torch.Tensor]:
        """The centred effects of ``params`` (default: the fitted ones). The map is linear, which the
        Laplace approximation uses (``laplace.py``)."""
        params = self.params if params is None else params
        out = {"b0": params["b0"]}
        for name in self.components:
            v = _centre(params[name], self._labels[name])
            # group deviations sum to zero across groups; a leaf's place effect within its group
            if name in ("h_grp", "s_grp", "v_grp", "c_grp"):
                v = v - v.mean(dim=0, keepdim=True)
            elif name == "f_grp":
                v = (v.reshape(-1, 2, self.nB) - v.reshape(-1, 2, self.nB).mean(dim=0, keepdim=True)).reshape(v.shape)
            elif name == "v_cat":
                v = _centre(v.T.contiguous(), self.grp).T
            out[name] = v
        nGrp = len(self.data.groups)
        out["f_all"] = out["f_all"].reshape(1, 2 * self.nB)
        out["f_grp"] = out["f_grp"].reshape(nGrp, 2 * self.nB)
        return out

    def _place_time(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """[groups, U, T] of exp(h + g) · M: the factor every leaf of a group shares."""
        M = torch.einsum("utg,kg->kut", self.N, torch.exp(x["f_all"] + x["f_grp"]))
        lin = self._time(x)[:, None, :]
        if spatial:
            lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
        return torch.exp(lin) * M

    def _time(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[groups, T]: history (h), plus season (c) at monthly grain, by group."""
        lin = x["h_all"][0][None, :] + x["h_grp"]
        if "c_all" in x:
            lin = lin + x["c_all"][0][self.moy][None, :] + x["c_grp"][:, self.moy]
        return lin

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
            eta = (eta + x["s_all"][0][self.u] + x["v_all"][0][self.u] + x["s_grp"][p, self.u] + x["v_grp"][p, self.u]
                   + x["v_cat"][self.e, self.u])
        return eta

    def total(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """Λ = Σ over every cell of μ, through the factorisation."""
        leaf_place = self._leaf_place(x, spatial)                                   # [E, U]
        per_group = torch.zeros((len(self.data.groups), self.N.shape[0]), dtype=self.dtype,
                                device=self.device).index_add_(0, self.grp, leaf_place)  # [K, U]
        return (per_group[:, :, None] * self._place_time(x, spatial)).sum()

    def _fisher_mass(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """A scalar whose gradient in each effect is that effect's Fisher diagonal: for Poisson
        counts Λ = Σ μ (∂Λ/∂effect = Σ μ over the cells the effect touches)."""
        return self.total(x)

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
        Σ y·η comes from the sufficient statistics; only Λ is computed per evaluation."""
        x = self.effects()
        linear = sum((x[k] * self.Y[k]).sum() for k in self.Y) + self.y_offset
        loglik = linear - self.total(x)
        return (-loglik + self.penalty(x)) / self.scale

    # ---- fitting ----------------------------------------------------------------

    def fit(self, outer: int = 25, inner: int = 30, tol: float = 0.02, log=print, warm: str | dict | None = None,
            accelerate: bool = False, move_tol: float = 0.0, mean_tol: float = 0.0) -> Monolith:
        """The outer loop: the mean at fixed τ's, then the Fellner–Schall update of every τ, until no τ moves
        by more than ``tol`` (a log-ratio). ``warm`` ("auto", or a stored fit's key) starts from a related
        fit (`warm_start`); ``accelerate`` mixes the last iterates of log τ by Anderson acceleration (`_Anderson`)
        and ``move_tol`` also stops when two successive τ updates each moved the mean's MAP by less than that many
        log-likelihood units (the refit's decrease of the penalised objective, ½ΔθᵀHΔθ: the total shift in
        posterior standard deviations, squared and halved), however far the weakly identified τ's still wander
        along their ridge. ``mean_tol`` ends each outer's Newton steps when one lowers the objective by less than
        that many log-likelihood units (the parameters persist across outers, so the unfinished tail is carried
        on; the last mean fit, after the loop, runs to the full tolerance). None of these changes what a
        converged fit is (the fixed point of the same update); they change how many outers, and how much work
        in each, reach it."""
        start = time.time()
        self._initialise()
        self.warm_info = self.warm_start(warm) if warm else None
        changes = [0.0] if self.warm_info else [np.inf]
        accel = _Anderson() if accelerate else None
        quiet = 0
        self.converged, self.stop_reason = False, f"outer cap {outer}"
        for it in range(outer):
            # the mean need not be precise while the τ's still move: a few Newton steps until they settle
            t0 = time.time()
            steps = self._fit_mean(inner if max(changes) < 0.1 else 10, loglik_tol=mean_tol)
            t1 = time.time()
            changes = self._update_taus(accel)
            move = max(self.refit_decrement, 0.0) * self._objective_norm()   # log-likelihood units the last τ update moved the MAP by
            quiet = quiet + 1 if move < move_tol and max(changes) < 0.5 and self.refit_converged else 0
            self.history.append({"iteration": it, "objective": float(self.objective()) * self.scale, "newton": steps,
                                 "change": max(changes), "move": move, "cg": self.cg_iterations, "mean_seconds": t1 - t0, "tau_seconds": time.time() - t1,
                                 "taus": {k: c.tau for k, c in self.components.items()}, "seconds": time.time() - start})
            taus = " ".join(f"{k}={c.tau:.3g}" for k, c in self.components.items())
            log(f"outer {it}: objective {self.history[-1]['objective']:.1f}, max τ change {max(changes):.3f}, "
                f"{time.time() - start:.0f}s | {taus}")
            if max(changes) < tol:
                self.converged, self.stop_reason = True, f"max τ change {max(changes):.3f} < {tol}"
                break
            if move_tol and quiet >= 2:
                self.converged, self.stop_reason = True, f"the MAP moved {move:.2g} < {move_tol} log-likelihood units twice"
                break
        self._fit_mean(inner)
        self.phi = self._dispersion()
        log(f"φ = {self.phi:.3f}; {time.time() - start:.0f}s; {'converged' if self.converged else 'NOT CONVERGED'}: {self.stop_reason}")
        return self

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
                scored.append((k.get("population", "popsvs") == mine.get("population", "popsvs"),
                               k.get("split") == mine.get("split"), shared / max(len(span(k) | span(mine)), 1),
                               k.get("through") == mine.get("through"), m))
            cand = max(scored, key=lambda s: s[:4])[4] if scored else None
        arrays = store.get_arrays("monolith", cand["key"]) if cand else None
        if cand is None or arrays is None:
            return None
        carried, partial = [], []
        grain = self.data.grain
        my_first, theirs_first = _periods_of(mine)[0], _periods_of(cand["key"])[0]
        shift = my_first - theirs_first                    # my period i is theirs i + shift (in years, or months)
        if grain == "month":
            shift *= 12
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
        """Closed-form marginal starting values: the block's rate, then log observed/expected
        by age–sex, by year and by leaf (each against the block's flat rate)."""
        d = self.data
        nE = len(d.leaves)
        rate = d.y.sum() / (d.N.sum() * nE)
        def ratio(obs: np.ndarray, exposure: np.ndarray) -> np.ndarray:
            # an unexposed group (a mother's male cells) starts at the flat rate, log 0
            return np.divide(obs, exposure, out=np.ones_like(obs), where=exposure > 0)

        by_g = ratio(np.bincount(d.g, weights=d.y, minlength=d.N.shape[2]), d.N.sum(axis=(0, 1)) * nE * rate)
        by_t = ratio(np.bincount(d.t, weights=d.y, minlength=d.N.shape[1]), d.N.sum(axis=(0, 2)) * nE * rate)
        by_e = ratio(np.bincount(d.e, weights=d.y, minlength=nE), np.full(nE, d.N.sum() * rate))
        with torch.no_grad():
            self.params["b0"].fill_(float(np.log(rate)))
            self.params["f_all"].copy_(torch.as_tensor(np.log(np.clip(by_g, 1e-6, None))).reshape(2, -1))
            self.params["h_all"].copy_(torch.as_tensor(np.log(np.clip(by_t, 1e-6, None)))[None, :])
            self.params["th_cat"].copy_(torch.as_tensor(np.log(np.clip(by_e, 1e-6, None)))[None, :])

    def _fit_mean(self, iterations: int, tolerance: float = 1e-9, loglik_tol: float = 0.0) -> int:
        """MAP of the mean given the τ's: truncated Newton–CG (OQ-6). Each step solves H d = −g by
        conjugate gradients on exact Hessian–vector products (double backward through the
        factorised total), preconditioned by the diagonal curvature, to a forcing tolerance
        min(0.5, √‖g‖)·‖g‖ (Eisenstat–Walker); then an Armijo backtracking line search. Stops when
        the objective's decrease falls below ``tolerance`` (relative) or ``loglik_tol`` (log-likelihood units; one
        unit is a shift of about a posterior standard deviation in total). Returns the Newton steps taken.

        It replaced L-BFGS, which used every iteration it was given and, from a start 14 units
        above the optimum (scaled objective, chapter IX), diverged to NaN; Newton–CG reached a gap
        of 1e-3 in one step (3 s) and 5e-6 in 40 s (evaluation 2026-10-04)."""
        params = list(self.params.values())
        steps = 0
        first_f = last_f = None      # the objective before the first step and after the last accepted one
        self.refit_converged = False  # True when a step ended the loop, False when the budget did
        for _ in range(iterations):
            steps += 1
            loss = self.objective()
            grads = torch.autograd.grad(loss, params, create_graph=True)
            g = torch.cat([q.reshape(-1) for q in grads]).detach()
            gnorm = float(g.norm())
            if gnorm < 1e-14:
                self.refit_converged = True
                break
            solve = self._precondition_operator()
            cg_before = self.cg_iterations

            def hv(v: torch.Tensor, grads=grads) -> torch.Tensor:
                parts, i = [], 0
                for q in params:
                    parts.append(v[i:i + q.numel()].view_as(q))
                    i += q.numel()
                out = torch.autograd.grad(grads, params, grad_outputs=parts, retain_graph=True)
                return torch.cat([o.reshape(-1) for o in out]).detach()

            x = torch.zeros_like(g)
            r = -g
            z = solve(r)
            d = z.clone()
            rz = float(r @ z)
            forcing = min(self.forcing, gnorm ** 0.5) * gnorm
            for _ in range(50):
                self.cg_iterations += 1
                Hd = hv(d)
                dHd = float(d @ Hd)
                if dHd <= 0:          # negative curvature: stop at the current iterate (or descend)
                    if not x.any():
                        x = solve(-g)
                    break
                alpha = rz / dHd
                x = x + alpha * d
                r = r - alpha * Hd
                if float(r.norm()) < forcing:
                    break
                z = solve(r)
                rz_new = float(r @ z)
                d = z + (rz_new / rz) * d
                rz = rz_new
            f0, slope, step = float(loss), float(g @ x), 1.0
            first_f = f0 if first_f is None else first_f
            with torch.no_grad():
                base = [q.detach().clone() for q in params]
                for _ in range(30):
                    i = 0
                    for q, b0 in zip(params, base, strict=True):
                        q.copy_(b0 + step * x[i:i + q.numel()].view_as(q))
                        i += q.numel()
                    f1 = float(self.objective())
                    if np.isfinite(f1) and f1 <= f0 + 1e-4 * step * slope:
                        break
                    step /= 2
                else:
                    for q, b0 in zip(params, base, strict=True):
                        q.copy_(b0)
                    self.refit_converged = True
                    break
            last_f = f1
            self.newton_log.append((f0, gnorm, self.cg_iterations - cg_before, step, f0 - f1))
            if f0 - f1 < tolerance * max(1.0, abs(f0)) or (f0 - f1) * self._objective_norm() < loglik_tol:
                self.refit_converged = True
                break
        # how far the mean moved the objective since the τ's last changed: ½ΔθᵀHΔθ per event, whose square root
        # (×√2) is the RMS change of the fitted log-rates over the events
        self.refit_decrement = 0.0 if last_f is None else first_f - last_f
        return steps

    def _precondition_operator(self):
        """r ↦ M⁻¹ r for the Newton–CG solves: the diagonal of the curvature, the Fisher diagonal plus τ·diag(Q)
        per parameter, in the units of the scaled objective. A block-Jacobi version (sparse LU of diag(Fisher) + τQ
        per effect and batch row, as in `laplace.Posterior`) was measured on SIM.DO XVI and was no better:
        the ill-conditioning is the coupling between effects that explain the same cells, not the structure
        inside one (evaluation 2026-10-05, fit throughput)."""
        x = {k: v.detach().requires_grad_(True) for k, v in self.effects().items()}
        names = ["b0", *self.components]
        grads = torch.autograd.grad(self._fisher_mass(x), [x[k] for k in names])
        norm = self._objective_norm()
        parts = []
        for name, d in zip(names, grads, strict=True):
            curv = d.detach().reshape(self.params[name].shape).abs()
            if name in self.components:
                c = self.components[name]
                curv = curv + c.tau * torch.as_tensor(c.shape.Q.diagonal(), dtype=self.dtype,
                                                      device=self.device)[None, :].expand_as(curv)
            parts.append((curv / norm + 1e-12).reshape(-1))
        curvature = torch.cat(parts)
        return lambda r: r / curvature

    def _objective_norm(self) -> float:
        """The divisor of the objective (events for counts)."""
        return self.scale

    def _update_taus(self, accel: _Anderson | None = None) -> list[float]:
        """Fellner–Schall: τ ← (rank − τ·tr(H⁻¹Q)) / (xᵀQx), H ≈ D + τQ per batch row. With ``accel`` the next
        log τ is the Anderson mix of the last iterates' updates, not the update itself; the reported change is
        always the update's (the fixed-point residual), so convergence means the same thing."""
        x = {k: v.detach().requires_grad_(True) for k, v in self.effects().items()}
        grads = torch.autograd.grad(self._fisher_mass(x), [x[k] for k in self.components])
        changes, proposals = [], {}
        for (name, c), d in zip(self.components.items(), grads, strict=True):
            if c.rank <= 0:
                changes.append(0.0)  # the constraints leave this effect nothing (a single group or leaf)
                continue
            D = d.detach().reshape(c.batch, -1).cpu().numpy()  # the Fisher diagonal (see _fisher_mass)
            v = x[name].detach().reshape(c.batch, -1).cpu().numpy()
            Q = c.shape.Q
            quad = float(sum(v[b] @ (Q @ v[b]) for b in range(c.batch)))
            trace = c.free * sum(_trace_inv_times(D[b], c.tau, Q) for b in range(c.batch))
            new = (c.rank - c.tau * trace) / max(quad, 1e-12)
            new = float(np.clip(new, c.tau * np.exp(-MAX_TAU_STEP), c.tau * np.exp(MAX_TAU_STEP)))
            new = float(np.clip(new, *TAU_BOUNDS))
            # a τ climbing past SHRUNK has shrunk its effect to nothing; its further climb is not instability. Nor is
            # its hovering about SHRUNK: the update of an effect that small is ill-defined (xᵀQx -> 0) and cycled
            # between 4.9e4 and 2.9e5 for 120 outers on SINAN-LEPT monthly (change 1.78 with the fit unchanged)
            changes.append(0.0 if max(new, c.tau) > SHRUNK else abs(np.log(new / c.tau)))
            self.trace_log.append((name, c.rank, quad, trace, c.tau, new))
            proposals[name] = new
        if accel is not None:
            active = [k for k, new in proposals.items() if max(new, self.components[k].tau) <= SHRUNK]
            if active:
                u = np.log([self.components[k].tau for k in active])
                g = np.log([proposals[k] for k in active])
                for k, value in zip(active, accel.step(u, g), strict=True):
                    proposals[k] = float(np.clip(np.exp(value), *TAU_BOUNDS))
        for name, new in proposals.items():
            self.components[name].tau = new
        return changes

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
                   + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None])
            base = torch.exp(lin)                                                 # [K, U, T]
            prof = torch.exp(x["f_all"] + x["f_grp"])                             # [K, G]
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
            for e in range(lp.shape[0]):
                k = int(self.grp[e])
                m = lp[e][sel][:, None, None] * base[k][sel][:, :, None] * self.N[sel] * prof[k][None, None, :]
                total += float((divisor * torch.log1p(m / divisor)).sum())
        return float(full.sum()) - (total - float((ph * np.log1p(mu / ph)).sum()))

    def _dispersion(self, places: np.ndarray | None = None) -> float:
        """φ by maximum likelihood with μ fixed (ARCHITECTURE §5.2): the maximiser of `nb_loglik` over
        the cells of ``places`` (a boolean mask over the block's places; None: all of them).

        Two estimators failed first, on chapter IX 2010–2023: moments (Pearson residuals of cells
        with tiny μ and y ≥ 1 dominate: φ = 0.013), and a power series for the empty cells
        (they hold 1.95 M of 4.99 M expected events, μ/φ is not small, the series diverges)."""
        def nll(log_phi: float) -> float:
            return -self.nb_loglik(float(np.exp(log_phi)), places=places)

        res = optimize.minimize_scalar(nll, bounds=(np.log(1e-3), np.log(1e6)), method="bounded",
                                       options={"xatol": 1e-3})
        phi = float(np.exp(res.x))
        if places is None:
            self.dispersion_check = {"phi": phi, "evaluations": int(res.nfev),
                                     "loglik_gain_over_poisson": float(nll(np.log(1e6)) - res.fun)}
        return float("inf") if phi > 0.99e6 else phi

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
            w = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel])
            mu = (w[:, :, None] * pt).sum(0)
            M2 = torch.einsum("utg,kg->kut", self.N ** 2, torch.exp(2 * (x["f_all"] + x["f_grp"])))
            lin = self._time(x)[:, None, :]
            if spatial:
                lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
            w2 = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel] ** 2)
            mu2 = (w2[:, :, None] * torch.exp(2 * lin) * M2).sum(0)
        return mu.cpu().numpy(), mu2.cpu().numpy()

    def expected_by_group(self, leaves: np.ndarray, spatial: bool = True,
                          x: dict[str, torch.Tensor] | None = None) -> np.ndarray:
        """μ[u,t,g] summed over the leaves (g = sex × age band)."""
        with torch.no_grad():
            x = self.effects() if x is None else x
            lp = self._leaf_place(x, spatial)
            sel = torch.as_tensor(leaves, device=self.device)
            K, U = len(self.data.groups), self.N.shape[0]
            w = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel])
            lin = self._time(x)[:, None, :]
            if spatial:
                lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
            prof = torch.exp(x["f_all"] + x["f_grp"])                                   # [K, G]
            mu = torch.einsum("ku,kut,kg,utg->utg", w, torch.exp(lin), prof, self.N)
        return mu.cpu().numpy()

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
                "stop_reason": getattr(self, "stop_reason", None)}

    # ---- persistence -------------------------------------------------------------

    def key(self) -> dict:
        return {**self.data.key, "graph": self.graph_kind}

    def save(self) -> None:
        arrays = {k: v.detach().cpu().numpy() for k, v in self.params.items()}
        store.put_arrays("monolith", self.key(), arrays, self.summary())

    @classmethod
    def load(cls, dataset: str, event: str, block: str, years: range | list[int],
             graph_kind: str = "contiguity", profile: str = "group", device: str = "cpu", **source) -> Monolith:
        """A fitted block from the store (its data re-assembled from the gateway's cache)."""
        from . import graphs

        data = assemble(dataset, event, block, years, profile, **source)
        model = cls(data, graphs.graph(data.places, graph_kind), graph_kind, device=device)
        arrays = store.get_arrays("monolith", model.key())
        meta = store.manifest("monolith", model.key())
        if arrays is None or meta is None:
            raise LookupError(f"no fitted monolith for {model.key()}")
        with torch.no_grad():
            for k, v in arrays.items():
                model.params[k].copy_(torch.as_tensor(v))
        for k, tau in meta["taus"].items():
            model.components[k].tau = float(tau)
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

    def _fisher_mass(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """Gaussian: the Fisher diagonal of an effect is Σ w over the cells it touches."""
        return (self.w * self.eta_nnz(x)).sum()

    def _objective_norm(self) -> float:
        return float(self.w.sum())

    def _initialise(self) -> None:
        d = self.data
        with torch.no_grad():
            self.params["b0"].fill_(float(np.sum(d.n * d.y) / np.sum(d.n)))

    def fit(self, outer: int = 25, inner: int = 30, tol: float = 0.02, log=print) -> MarkModel:
        start = time.time()
        self._initialise()
        for it in range(outer):
            self._fit_mean(inner)
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
        self._fit_mean(inner)
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


# ---------------------------------------------------------------------- model choice


def extrapolate(model: Monolith, test: BlockData, history: str = "auto") -> tuple[Monolith, dict[str, torch.Tensor]]:
    """A fit carried to later periods: every effect as fitted, the histories h extrapolated.
    ``history`` chooses the forecast of h:
      linear    the RW2's forecast mean, linear from the last two fitted periods (the annual default);
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
    tm = Monolith(test, model.graph, model.graph_kind, device=str(model.device))
    tm.phi = model.phi
    return tm, extrapolate_effects(model, tm, model.effects(), history)


def extrapolate_effects(model: Monolith, tm: Monolith, effects: dict[str, torch.Tensor],
                        history: str = "auto") -> dict[str, torch.Tensor]:
    """The effects (the fitted ones, or a posterior draw's) with their histories h carried over the
    test periods of ``tm`` (see `extrapolate`)."""
    monthly = model.data.grain == "month"
    if history == "auto":
        history = "level36" if monthly else "linear"
    test = tm.data
    with torch.no_grad():
        x = {k: v.detach().clone() for k, v in effects.items()}
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


def heldout(model: Monolith, test: BlockData) -> dict:
    """Score a fit on later years (ARCHITECTURE §5.4): every effect as fitted, the histories
    h extrapolated as the RW2's forecast mean (linear from the last two fitted years).
    Returns the Poisson deviance over every test cell (empty cells through the factorised
    total) and the NB log-likelihood of the non-empty cells at the fitted φ."""
    tm, x = extrapolate(model, test)
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
            "nb_loglik_nonempty": nb, "years": test.years.tolist(), "graph": model.graph_kind,
            "profile": test.key.get("profile", "group")}


# ---------------------------------------------------------------------- helpers


class _Anderson:
    """Anderson acceleration (depth ``m``) of the fixed-point iteration u ← g(u) on the vector of log τ.
    With residuals f_k = g(u_k) − u_k it takes u_{k+1} = g_k − ΔG γ, γ = argmin ‖f_k − ΔF γ‖² + λ‖γ‖²
    over the last differences of residuals and updates; a fixed point (f = 0) is left unchanged, so the
    converged τ's are the plain iteration's. Safeguards: the step is limited to the plain damping
    (×10 per component) and the history is dropped when the residual grows by more than half."""

    def __init__(self, m: int = 4, ridge: float = 1e-8):
        self.m, self.ridge = m, ridge
        self.reset()

    def reset(self) -> None:
        self.F: list[np.ndarray] = []
        self.G: list[np.ndarray] = []

    def step(self, u: np.ndarray, g: np.ndarray) -> np.ndarray:
        f = g - u
        if len(self.F) and (len(f) != len(self.F[-1]) or np.linalg.norm(f) > 1.5 * np.linalg.norm(self.F[-1])):
            self.reset()
        self.F.append(f)
        self.G.append(g)
        self.F, self.G = self.F[-(self.m + 1):], self.G[-(self.m + 1):]
        if len(self.F) < 2:
            return g
        dF = np.stack([b - a for a, b in zip(self.F[:-1], self.F[1:], strict=True)], axis=1)
        dG = np.stack([b - a for a, b in zip(self.G[:-1], self.G[1:], strict=True)], axis=1)
        scale = max(float(np.trace(dF.T @ dF)) / dF.shape[1], 1e-300)
        gamma = np.linalg.solve(dF.T @ dF + self.ridge * scale * np.eye(dF.shape[1]), dF.T @ f)
        nxt = g - dG @ gamma
        return u + np.clip(nxt - u, -MAX_TAU_STEP, MAX_TAU_STEP)


_FAMILY_DROP = {"years", "data", "through", "population", "population_model", "split"}


def _family(key: dict) -> dict:
    """What makes two stored fits the same model of the same events: the key without its years, exposure and split."""
    return {k: v for k, v in key.items() if k not in _FAMILY_DROP}


def _periods_of(key: dict) -> list[int]:
    return list(key["years"])


def _within_groups(leaf_group: np.ndarray, n: int) -> structures.Shape:
    """θ_cat: iid, centred within each group (the group carries the mean)."""
    return structures.Shape("iid_within", sp.identity(n, format="csr"), n - len(np.unique(leaf_group)),
                            centred=True, components=leaf_group)


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


def _trace_inv_times(D: np.ndarray, tau: float, Q: sp.csr_matrix, probes: int = 24) -> float:
    """tr((diag(D) + τQ)⁻¹ Q): exact for small n, Hutchinson with a sparse LU otherwise."""
    n = Q.shape[0]
    H = (sp.diags(D) + tau * Q).tocsc() + sp.identity(n, format="csc") * 1e-9
    if n <= 400:
        return float(np.trace(np.linalg.solve(H.toarray(), Q.toarray())))
    lu = spla.splu(H)
    rng = np.random.default_rng(config.seed("hutchinson", n))
    z = rng.choice([-1.0, 1.0], size=(n, probes))
    return float(np.mean(np.sum(z * lu.solve(Q @ z), axis=0)))


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
