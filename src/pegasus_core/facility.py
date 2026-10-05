"""The institution behind an event: which facility recorded it (ARCHITECTURE §7.7, §9.1).

A lead that is one hospital's coding looks like a place effect at municipal grain. This module reads the
facility column of the event type (pegasus_data's `institution` role: SIH-RD `CNES`, SIM-DO `CODESTAB`)
and serves the cube (residence municipality, facility, 3-character code, year) -> events, from which
`explain.facility_concentration` judges a lead. The cube is a gateway-level cache, one table per year.

SIH names the facility of every admission. SIM names it only for deaths certified in an establishment
(`CODESTAB` is empty for a death at home or in the street): a lead's SIM facility coverage is reported
beside its verdict, and a place whose deaths have no facility cannot be judged here.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import duckdb
import numpy as np
import pyarrow as pa
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

from . import config, gateway, store

CODE_CHARS = 3     # the classifier's category level; subcodes are not kept (a 4-character coding habit is seen at 3)


def facility_column(dataset: str) -> tuple[str, str | None]:
    """(facility column, the facility's own municipality column or None) from pegasus_data's roles."""
    import pegasus_data as pg

    roles = pg.roles(dataset)
    fac = [r for r in roles if r.get("model") == "institution" and r.get("property") == "facility"]
    if not fac:
        raise LookupError(f"{dataset}: no facility among its institution roles")
    where = [r for r in roles if r.get("model") == "where" and r.get("property") in ("facility_municipality", "municipality")]
    return fac[0]["column"], where[0]["column"] if where else None


def facility_cube(dataset: str, event: str, year: int) -> pa.Table:
    """Events of one year by (u residence, facility, code3). ``facility`` is the CNES code as text, '' when the
    record names none; ``fm`` the facility's municipality as the data gives it ('' if the dataset has none)."""
    import pegasus_data as pg

    strata = gateway._strata(dataset)
    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    classifier = next((c["column"] for c in spec["classifiers"] if c["role"] == "primary"), None)
    if classifier is None:
        raise LookupError(f"{dataset}/{event}: no primary classifier, no facility cube")
    fcol, mcol = facility_column(dataset)
    key = {"what": "facility_cube", "dataset": dataset, "event": event, "year": year, "classifier": classifier,
           "facility": fcol, "data": config.data_version(), "v": 1, **gateway._df_key(dataset, year)}
    hit = store.get_table("gateway", key)
    if hit is not None:
        return hit
    by = [strata["residence"], fcol, classifier] + ([mcol] if mcol else [])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.count_events(dataset, event, period=year, geography="BR", by=by, root=config.data_root(),
                              allow_partial=False, max_download=8 * 1024**3)
    con = duckdb.connect()
    con.register("r", raw)
    fm = f"coalesce(left(trim(CAST(\"{mcol}\" AS VARCHAR)), 6), '')" if mcol else "''"
    out = con.execute(f"""SELECT CAST({gateway._residence_sql(strata['residence'])} AS INTEGER) AS u,
            coalesce(trim(CAST("{fcol}" AS VARCHAR)), '') AS facility, {fm} AS fm,
            left(upper(trim(CAST("{classifier}" AS VARCHAR))), {CODE_CHARS}) AS code,
            CAST({year} AS SMALLINT) AS year, CAST(sum(events) AS INTEGER) AS y
        FROM r WHERE "{classifier}" IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, out, {"source": f"pegasus_data.count_events({dataset}, {event}) by residence, {fcol}, {classifier}"})
    return out


class Facilities:
    """A session's facility cube as integer columns, indexed for the lead-level reads of `tally`.

    ``places``/``years`` are the evidence grid's. Rows are (place index, facility id, year index, events), once for
    events of any cause and, per block, for the block's codes. Both are sorted by place; the block rows are also
    ranged by facility for the residents of other places."""

    def __init__(self, dataset: str, event: str, years: list[int], places: np.ndarray, grid_years: np.ndarray):
        self.dataset, self.event, self.years = dataset, event, [int(y) for y in years]
        self.places, self.grid_years = np.asarray(places), np.asarray(grid_years)
        self._blocks: dict[str, tuple] = {}
        names: set[str] = set()
        for y in self.years:
            names.update(facility_cube(dataset, event, y).column("facility").unique().to_pylist())
        self.names = np.array(sorted(names), dtype=object)               # '' (no facility) sorts first
        self._by_name = {n: i for i, n in enumerate(self.names)}
        self.none = self._by_name.get("", -1)
        self._total = self._read(None)

    def _read(self, codes: list[str] | None) -> tuple[np.ndarray, ...]:
        """(place idx, facility id, year idx, code idx, events) summed over the cube, for ``codes`` (None: every code,
        code idx 0)."""
        con = duckdb.connect()
        fac = pa.table({"facility": pa.array(self.names.tolist(), pa.string()), "f": pa.array(range(len(self.names)), pa.int32())})
        con.register("fac", fac)
        con.register("pl", pa.table({"u": pa.array(self.places.astype(np.int32)), "p": pa.array(range(len(self.places)), pa.int32())}))
        if codes is not None:
            con.register("cd", pa.table({"code": pa.array(codes, pa.string()), "c": pa.array(range(len(codes)), pa.int32())}))
        out = []
        for y in self.years:
            t = facility_cube(self.dataset, self.event, y)
            con.register("t", t)
            code = "JOIN cd USING (code)" if codes is not None else ""
            sel = "cd.c" if codes is not None else "0"
            out.append(con.execute(f"""SELECT pl.p AS p, fac.f AS f, {sel} AS c, CAST(sum(t.y) AS DOUBLE) AS y
                FROM t JOIN pl USING (u) JOIN fac USING (facility) {code} GROUP BY ALL""").fetch_arrow_table())
        cols = []
        for k, ty in (("p", np.int32), ("f", np.int32), ("c", np.int32), ("y", np.float64)):
            cols.append(np.concatenate([o.column(k).to_numpy().astype(ty) for o in out]))
        tix = np.concatenate([np.full(o.num_rows, i, np.int16) for i, o in enumerate(out)])
        p, f, c, y = cols
        t_idx = np.searchsorted(self.grid_years, np.array(self.years))[tix]       # the year's column on the grid
        order = np.argsort(p, kind="stable")
        return p[order], f[order], t_idx[order].astype(np.int16), c[order], y[order]

    def block(self, key: str, codes: list[str]) -> tuple:
        """The block's rows (cached by ``key``): sorted by place, plus the offsets by place and the order by facility."""
        if key not in self._blocks:
            p, f, t, c, y = self._read(codes)
            starts = np.searchsorted(p, np.arange(len(self.places) + 1))
            by_f = np.argsort(f, kind="stable")
            f_starts = np.searchsorted(f[by_f], np.arange(len(self.names) + 1))
            self._blocks[key] = (p, f, t, c, y, starts, by_f, f_starts, {code: i for i, code in enumerate(codes)})
        return self._blocks[key]

    @staticmethod
    def _gather(starts: np.ndarray, rows: np.ndarray) -> np.ndarray:
        return np.concatenate([np.arange(starts[r], starts[r + 1]) for r in rows]) if len(rows) else np.zeros(0, dtype=np.int64)

    def tally(self, key: str, block_codes: list[str], lead_codes: list[str], rows: np.ndarray):
        """The lead's events by facility: the `explain.FacilityTally` of residents of ``rows`` (grid place indices)
        for the codes of the lead and of its block."""
        from .scans import explain

        p, f, t, c, y, starts, by_f, f_starts, cidx = self.block(key, block_codes)
        T = len(self.grid_years)
        sel = self._gather(starts, rows)
        tp, tf, tt, _, ty, *_ = self._total
        tstarts = np.searchsorted(tp, np.arange(len(self.places) + 1))
        tsel = self._gather(tstarts, rows)
        used = np.unique(np.concatenate([f[sel], tf[tsel]]))
        if used.size == 0:
            return None
        local = np.full(len(self.names), -1, dtype=np.int64)
        local[used] = np.arange(used.size)
        is_lead = np.zeros(len(block_codes), bool)
        is_lead[[cidx[c_] for c_ in lead_codes if c_ in cidx]] = True
        F = used.size

        def fold(fl, tl, w):
            return np.bincount(fl * T + tl, weights=w, minlength=F * T).reshape(F, T)

        lead = fold(local[f[sel]][is_lead[c[sel]]], t[sel][is_lead[c[sel]]], y[sel][is_lead[c[sel]]])
        block = fold(local[f[sel]], t[sel], y[sel])
        total = fold(local[tf[tsel]], tt[tsel], ty[tsel])
        inside = np.zeros(len(self.places), bool)
        inside[rows] = True

        def outside(top: np.ndarray):
            lo, bl = np.zeros((len(top), T)), np.zeros((len(top), T))
            for j, i in enumerate(top):
                g = by_f[f_starts[used[i]]:f_starts[used[i] + 1]]
                g = g[~inside[p[g]]]
                np.add.at(bl[j], t[g], y[g])
                m = is_lead[c[g]]
                np.add.at(lo[j], t[g][m], y[g][m])
            return lo, bl

        return explain.FacilityTally(self.names[used], lead, block, total, outside)


# ---------------------------------------------------------------------- the supply term (ARCHITECTURE §4.5, ADR-0017)

EPIDEMIC_PREFIXES = ("A", "B", "J", "U")   # ICD chapters I, X and XXII: epidemic-prone, never read as a facility's supply
SUPPLY_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)  # exponents tried for each index
CLIP = (0.02, 20.0)                        # an index outside this is a facility entering or leaving the data
PSEUDO = 5.0                               # events added to a place-year's other-chapter count (small places)
DEADBAND = 2.0                             # standard deviations of an index's counting noise below which it is read as no step


@dataclass
class Pairs:
    """(place, facility, year) -> events in the block (x) and in the other, supply-bearing chapters (o)."""

    names: np.ndarray                      # facility ids; '' (no facility) first
    u: np.ndarray                          # place code
    f: np.ndarray                          # index into names
    year: np.ndarray
    x: np.ndarray
    o: np.ndarray


def pairs(dataset: str, event: str, years: list[int], block_codes: list[str]) -> Pairs:
    """The cube folded to the block and to everything outside it and outside the epidemic-prone chapters."""
    con = duckdb.connect()
    con.register("bc", pa.table({"code": pa.array(sorted(set(block_codes)), pa.string())}))
    parts = []
    for y in years:
        con.register("t", facility_cube(dataset, event, int(y)))
        epi = " OR ".join(f"t.code LIKE '{p}%'" for p in EPIDEMIC_PREFIXES)
        parts.append(con.execute(f"""SELECT u, facility, year,
            CAST(sum(CASE WHEN bc.code IS NOT NULL THEN t.y ELSE 0 END) AS DOUBLE) AS x,
            CAST(sum(CASE WHEN bc.code IS NULL AND NOT ({epi}) THEN t.y ELSE 0 END) AS DOUBLE) AS o
            FROM t LEFT JOIN bc USING (code) GROUP BY ALL""").fetch_arrow_table())
    tab = pa.concat_tables(parts)
    names, f = np.unique(np.array(tab.column("facility").to_pylist(), dtype=object), return_inverse=True)
    return Pairs(names, tab.column("u").to_numpy(), f.astype(np.int64), tab.column("year").to_numpy().astype(int),
                 tab.column("x").to_numpy(), tab.column("o").to_numpy())


def supply_indices(p: Pairs, places: np.ndarray, years: np.ndarray, pop: np.ndarray) -> dict[str, np.ndarray]:
    """Two [U, T] indices of how much hospital the place's residents had, from other chapters only (so the block's
    own events never enter them):

    ``volume``       sum over the facilities f serving the place of w_uf r_ft: w_uf the share of the place's block
                     events recorded at f (all years), r_ft the facility's volume of other chapters as a share of
                     the nation's, over its own mean across the years. An opening, a closing, a facility entering
                     or leaving the data are steps of r.
    ``utilisation``  the place's own other-chapter admissions over what its mean rate and the nation's course
                     give (``PSEUDO`` events added): the residents' recorded use of any facility."""
    U, T = len(places), len(years)
    ok = np.isin(p.u, places)
    u = np.searchsorted(places, p.u[ok])
    f, t, x, o = p.f[ok], np.searchsorted(years, p.year[ok]), p.x[ok], p.o[ok]
    F = len(p.names)
    Of = np.zeros((F, T))
    np.add.at(Of, (f, t), o)
    rel = Of / np.maximum(Of.sum(0), 1e-9)
    mean = rel.mean(1, keepdims=True)
    r = np.divide(rel, mean, out=np.ones_like(rel), where=mean > 0)
    key = u.astype(np.int64) * F + f
    uk, inv = np.unique(key, return_inverse=True)
    wx = np.bincount(inv, weights=x)
    pu, pf = uk // F, uk % F
    total = np.bincount(pu, weights=wx, minlength=U)
    share = wx / np.maximum(total[pu], 1e-9)
    volume, v_volume = np.zeros((U, T)), np.zeros((U, T))
    for tt in range(T):
        np.add.at(volume[:, tt], pu, share * r[pf, tt])
        np.add.at(v_volume[:, tt], pu, share ** 2 / (Of[pf, tt] + PSEUDO))
    volume[total <= 0] = 1.0                      # a place with no block events has no facility to weigh
    other = np.zeros((U, T))
    np.add.at(other, (u, t), o)
    rate = other.sum(1, keepdims=True) / np.maximum(pop.sum(1, keepdims=True), 1e-9)
    expected = rate * pop
    course = other.sum(0) / np.maximum(expected.sum(0), 1e-9)
    return {"volume": _deadband(volume, v_volume), "utilisation": _deadband((other + PSEUDO) / (expected * course + PSEUDO), 1.0 / (other + PSEUDO))}


def _deadband(index: np.ndarray, var: np.ndarray) -> np.ndarray:
    """An index with the noise of its counts taken out. The log index of a cell carries the sampling variance of the
    counts it is made of (``var``, Poisson), times an inflation ``c`` read off the places themselves (the median over
    places of the variance of their course over its Poisson variance, so the minority with real steps does not set it).
    The log is soft-thresholded at ``DEADBAND`` standard deviations: a sole-provider town's index is its own other-chapter
    counts, and without the threshold their noise entered its expectation (sd of z 0.96 to 1.06, evaluation 2026-10-05,
    institutions); a closure, an opening or a facility entering the data is many standard deviations."""
    L = np.log(np.clip(index, *CLIP))
    ok = var.mean(1) > 0
    c = float(np.median(L[ok].var(1) / var[ok].mean(1))) if ok.any() else 1.0
    sd = np.sqrt(max(c, 1.0) * var)
    return np.exp(np.sign(L) * np.maximum(np.abs(L) - DEADBAND * sd, 0.0))


def renormalise(a: np.ndarray, mu: np.ndarray, rounds: int = 20) -> np.ndarray:
    """Scale ``a`` so that a place's expected total and a year's expected total are what they were without it:
    the supply term moves events between years within a place and between places within a year, never adds any."""
    a = a.copy()
    for _ in range(rounds):
        a *= (mu.sum(1) / np.maximum((mu * a).sum(1), 1e-300))[:, None]
        a *= (mu.sum(0) / np.maximum((mu * a).sum(0), 1e-300))[None, :]
    return a


def nb_loglik(y: np.ndarray, mu: np.ndarray, kappa: float) -> float:
    """Negative binomial log-likelihood with Var = mu + kappa mu^2 (the place-year aggregate, one kappa)."""
    r = 1.0 / kappa
    return float((gammaln(y + r) - gammaln(r) - gammaln(y + 1) + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu))).sum())


def _kappa(y: np.ndarray, mu: np.ndarray) -> tuple[float, float]:
    k = minimize_scalar(lambda q: -nb_loglik(y, mu, q), bounds=(1e-4, 5.0), method="bounded").x
    return float(k), nb_loglik(y, mu, k)


@dataclass
class Supply:
    """The fitted supply term of one block: a [U, T] multiplier of its expectation and what it was chosen by."""

    factor: np.ndarray
    exponents: dict[str, float]
    info: dict = field(default_factory=dict)


def fit_supply(y: np.ndarray, mu: np.ndarray, indices: dict[str, np.ndarray], fixed: dict[str, float] | None = None) -> Supply:
    """Exponents (a grid) of the indices by the negative binomial likelihood of the block's place-year cells under
    ``mu`` x the renormalised term, the dispersion refitted at each. Exponents of zero everywhere: no supply term."""
    live = mu > 1e-6
    logs = {k: np.log(np.clip(v, *CLIP)) for k, v in indices.items()}
    k0, l0 = _kappa(y[live], mu[live])
    names = list(logs)
    if fixed is not None:                      # exponents given, not chosen (a measurement of the pass-through)
        e = {n: float(fixed.get(n, 0.0)) for n in names}
        a = renormalise(np.exp(sum(b * logs[n] for n, b in e.items())), mu)
        k, ll = _kappa(y[live], (mu * a)[live])
        return Supply(a, e, {"loglik_gain": ll - l0, "kappa_before": k0, "kappa_after": k, "cells": int(live.sum()), "fixed": True})
    best = (0.0, dict.fromkeys(names, 0.0), k0)
    grid = np.array(np.meshgrid(*([SUPPLY_GRID] * len(names)))).reshape(len(names), -1).T
    for g in grid:
        e = dict(zip(names, g, strict=True))
        a = renormalise(np.exp(sum(b * logs[k] for k, b in e.items())), mu)
        k, ll = _kappa(y[live], (mu * a)[live])
        if ll - l0 > best[0]:
            best = (ll - l0, e, k)
    gain, e, k = best
    a = renormalise(np.exp(sum(b * logs[n] for n, b in e.items())), mu)
    return Supply(a, {n: float(b) for n, b in e.items()}, {"loglik_gain": gain, "kappa_before": k0, "kappa_after": k, "cells": int(live.sum())})


def attach_supply(model, dataset: str, event: str) -> Supply:
    """Fit the supply term of a loaded annual count block from the facility cube and set ``model.supply`` (the
    monolith's expectation then carries it in every tier). It takes the block's B1 expectation as the fit left it,
    with no refit, and chooses two exponents (``SUPPLY_GRID``) on the same cells it is then applied to. The cube is
    annual: at the monthly grain an annual factor put on each month raised the outbreak lens's B1 cells from 83 to
    139 (a step inside a year lands in the wrong months), so the monthly blocks keep no supply term."""
    d = model.data
    if d.grain != "year":
        raise NotImplementedError("the supply term needs the facility cube at the block's grain; the cube is annual")
    leaves = np.arange(len(d.leaves))
    model.supply = None
    mu, _ = model.expected(leaves, spatial=True)
    p = pairs(dataset, event, [int(v) for v in d.years], d.leaves)
    sup = fit_supply(model.observed(leaves), mu, supply_indices(p, d.places, d.years, d.N.sum(2)), config.supply_exponents())
    model.supply = sup.factor
    return sup


# ---------------------------------------------------------------------- the institution lattice (cells (f, t), E_i)

LATTICE_MIN_EXPECTED = 30.0     # a facility needs this many expected block events over the period to be read
LATTICE_G = 27.0                # likelihood-ratio statistic of a window (Bonferroni over ~10^5 windows at 0.01)
LATTICE_RATIO = 1.6             # smallest step read (ADR-0014's volume step)
VOLUME_FOLLOWS = 0.5            # the other chapters stepped by at least this share of the block's log step: a volume step


def best_window(obs: np.ndarray, exp: np.ndarray, kappa: float):
    """Per row, the window [a, b) with the largest likelihood-ratio gain over a constant ratio (Poisson, scaled by
    1 + kappa * mean cell mean): (G, a, b, log ratio inside / outside)."""
    n, T = obs.shape
    cy, cm = np.concatenate([np.zeros((n, 1)), obs.cumsum(1)], 1), np.concatenate([np.zeros((n, 1)), exp.cumsum(1)], 1)
    Y, M = cy[:, -1], cm[:, -1]
    best = np.zeros((n, 4))
    best[:, 3] = 0.0
    for a in range(T):
        for b in range(a + 1, T + 1):
            if a == 0 and b == T:
                continue
            yi, mi = cy[:, b] - cy[:, a], cm[:, b] - cm[:, a]
            yo, mo = Y - yi, M - mi
            with np.errstate(divide="ignore", invalid="ignore"):
                ci, co, c0 = yi / mi, yo / mo, Y / M
                ll = lambda yy, cc, mm: np.where(yy > 0, yy * np.log(np.where(cc > 0, cc, 1.0)), 0.0) - cc * mm  # noqa: E731
                g = 2 * (ll(yi, ci, mi) + ll(yo, co, mo) - ll(yi, c0, mi) - ll(yo, c0, mo))
                g = np.where(np.isfinite(g) & (mi > 0) & (mo > 0), g, 0.0) / (1 + kappa * (Y / T))
                lr = np.log((yi + 0.5) / np.maximum(mi, 1e-9)) - np.log((yo + 0.5) / np.maximum(mo, 1e-9))   # half an event each side: a facility that never recorded the block has a finite ratio
            better = g > best[:, 0]
            best[better] = np.stack([g, np.full(n, a), np.full(n, b), lr], 1)[better]
    return best


def institution_lattice(p: Pairs, places: np.ndarray, years: np.ndarray, mu: np.ndarray) -> dict:
    """The block on the institution lattice: cells (facility, year) with the facility's *catchment* as exposure.

    A facility's expected block events are m_ft = sum_u q_uf mu_ut, mu the place model's expectation and q_uf the
    share of place u's other-chapter events recorded at f over all years (the care-flow kernel the data itself gives,
    not circular with the block). Each facility with enough expected events is searched for its best window
    (a step or a bump: a run of years whose observed/expected ratio differs from the rest) by the Poisson
    likelihood ratio G, with the dispersion of the facilities' own residuals; a window is *volume* when the
    facility's other-chapter volume, as a share of the nation's, moved with it (>= ``VOLUME_FOLLOWS`` of the log
    step), else *specific* (the facility's handling of the block: coding, a service, a real event it served).
    Returns the facilities' steps and the cell arrays."""
    U, T = len(places), len(years)
    ok = np.isin(p.u, places)
    u, f = np.searchsorted(places, p.u[ok]), p.f[ok]
    t, x, o = np.searchsorted(years, p.year[ok]), p.x[ok], p.o[ok]
    F = len(p.names)
    key = u.astype(np.int64) * F + f
    uk, inv = np.unique(key, return_inverse=True)
    pu, pf = uk // F, uk % F
    wo = np.bincount(inv, weights=o)
    wx = np.bincount(inv, weights=x)
    tot = np.bincount(pu, weights=wo, minlength=U)
    q = np.where(tot[pu] > 0, wo / np.maximum(tot[pu], 1e-9), wx / np.maximum(np.bincount(pu, weights=wx, minlength=U)[pu], 1e-9))
    m = np.zeros((F, T))
    for tt in range(T):
        np.add.at(m[:, tt], pf, q * mu[pu, tt])
    y = np.zeros((F, T))
    np.add.at(y, (f, t), x)
    vol = np.zeros((F, T))
    np.add.at(vol, (f, t), o)
    nat = vol.sum(0)
    rel = vol / np.maximum(nat, 1e-9)
    named = p.names != ""
    use = named & (m.sum(1) >= LATTICE_MIN_EXPECTED)

    ids = np.nonzero(use)[0]
    # dispersion of the facilities' own cells around their constant ratio (quasi-Poisson, the median facility)
    c0 = y[ids].sum(1, keepdims=True) / m[ids].sum(1, keepdims=True)
    res = (y[ids] - c0 * m[ids]) ** 2 / np.maximum(c0 * m[ids], 1e-9)
    kappa = float(max(0.0, np.median((res.mean(1) - 1) / np.maximum((c0 * m[ids]).mean(1), 1e-9))))
    bx = best_window(y[ids], m[ids], kappa)
    # the same window read on the other chapters' share of the nation's volume
    a, b = bx[:, 1].astype(int), bx[:, 2].astype(int)
    inside = (np.arange(T)[None, :] >= a[:, None]) & (np.arange(T)[None, :] < b[:, None])
    ro = rel[ids]
    eps = 0.01 * np.maximum(ro.mean(1), 1e-9)       # a hundredth of the facility's mean share: a facility absent from the data has a finite step
    lo = np.log(((ro * inside).sum(1) / np.maximum(inside.sum(1), 1) + eps) / ((ro * ~inside).sum(1) / np.maximum((~inside).sum(1), 1) + eps))
    step = (bx[:, 0] >= LATTICE_G) & (np.abs(bx[:, 3]) >= np.log(LATTICE_RATIO))
    volume = step & (np.sign(lo) == np.sign(bx[:, 3])) & (np.abs(lo) >= VOLUME_FOLLOWS * np.abs(bx[:, 3]))
    rows = []
    for i in np.nonzero(step)[0]:
        lo_i, lr_i, a_i, b_i = float(lo[i]), float(bx[i, 3]), int(a[i]), int(b[i])
        if a_i == 0 and b_i > T / 2:          # a step is reported as its shorter side: the run after it (the sign turns)
            a_i, b_i, lo_i, lr_i = b_i, T, -lo_i, -lr_i
        elif b_i == T and a_i < T / 2:
            a_i, b_i, lo_i, lr_i = 0, a_i, -lo_i, -lr_i
        rows.append({"facility": str(p.names[ids[i]]), "g": float(bx[i, 0]), "start": int(years[a_i]), "end": int(years[b_i - 1]),
                     "log_ratio": lr_i, "other_log_ratio": lo_i, "kind": "volume" if volume[i] else "specific",
                     "expected": float(m[ids[i]].sum()), "observed": float(y[ids[i]].sum())})
    return {"steps": rows, "facilities": int(use.sum()), "named_facilities": int(named.sum()), "kappa": kappa,
            "y": y, "m": m, "volume": vol}
