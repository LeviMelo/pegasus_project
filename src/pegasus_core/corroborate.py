"""Corroboration: an effect seen again in an independent field (ARCHITECTURE §8.3, tier R3).

A one-off event (a dam collapse, an epidemic year, a fire) cannot recur in the other temporal half, and a
split of its own events says only that it is not a selection artefact. What confirms it is a second
measurement of the same place and time that does not share the first one's records.

**The sources are declared, never named here.** Every other served event type whose records carry an ICD-10 code
(its primary classifier, or the code tree that defines its events, as SINAN's agravo) is a source for a lead whose
codes it holds; a context field is a source where pegasus_data declares which ICD-10 codes record its events (the
disasters field's `icd10`). `sources` lists them.

**The null is the corroborating field's own.** The statistic is computed on the lead's places and years in
that field; the null is the same statistic on random place sets of the same size, in the same states, matched
on population (a quintile of the nation's municipalities), over the same years. A place set that is as active
as the lead in the other field by the field's own variation, in a year when the whole state was, does not
corroborate. The p-value is (1 + #{null ≥ observed}) / (1 + B), so its floor is 1/(B + 1).

**Overlap (§8.5).** Two systems that a declared link pairs share persons (a death in hospital is an admission that
ended in death): the corroborating count is the source's events less the expected number linked to the lead's system
(Σ p_match, `gateway.linked_counts`), and the linked share is recorded as the measured overlap. Systems no link pairs
are taken as sharing no record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa

from . import config, gateway, store


def _system(dataset: str) -> str:
    return dataset.upper().replace(".", "-")


@dataclass(frozen=True)
class Source:
    """One independent field: an event type's ICD-10-coded events (``kind`` events), or a context field crossed by a
    declared ICD-10 correspondence (``kind`` field)."""
    kind: str
    dataset: str
    event: str = ""
    column: str = ""                          # the ICD-10 column of its records
    link: tuple[str, str] | None = None       # a declared link to the lead's system: (spec, this source's side)
    codes: tuple[tuple[str, tuple[str, ...]], ...] = ()   # a field: (ICD-10 code or range, its typologies)
    harm: tuple[str, ...] = ()                # a field: its columns counting people harmed (declared)

    @property
    def label(self) -> str:
        if self.kind == "field":
            return f"{self.dataset} (declared ICD-10 correspondence)"
        return f"{self.dataset} {self.event}" + (f", less records linked by {self.link[0]}" if self.link else "")


def icd_column(dataset: str, event: str) -> str | None:
    """The column whose ICD-10 code classifies an event type's records: its primary classifier when that is ICD-10,
    else the ICD-10 code tree that defines its events (`model: event_type`); None when it has neither."""
    et = gateway.event_type(dataset, event)
    primary = next((c for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    if primary is not None:
        return primary["column"] if primary.get("structure") == "ICD10" else None
    return next((r["column"] for r in gateway.roles(dataset)
                 if r.get("model") == "event_type" and "ICD10" in (r.get("codelists") or [])), None)


def sources(dataset: str, served: list[tuple[str, str]]) -> list[Source]:
    """The independent fields of a lead of ``dataset``: every served event type of another system with ICD-10-coded
    records (with the declared link to ``dataset`` whose linked records it shares, a side not grouped), and every
    context field with a declared ICD-10 correspondence."""
    specs = gateway.link_specs()
    out: list[Source] = []
    for ds, ev in dict.fromkeys(served):
        if _system(ds) == _system(dataset) or (col := icd_column(ds, ev)) is None:
            continue
        link = next(((name, side) for name, s in specs.items()
                     for side, sd, other in (("left", s.left, s.right), ("right", s.right, s.left))
                     if _system(sd.dataset) == _system(ds) and _system(other.dataset) == _system(dataset)
                     and not (sd.group and (sd.where or getattr(sd, "latest", None)))), None)
        out.append(Source("events", ds, ev, col, link))
    for name, spec in gateway.declared_fields().items():
        if spec.get("icd10"):
            out.append(Source("field", name, codes=tuple((str(k), tuple(v)) for k, v in spec["icd10"].items()),
                              harm=tuple(spec.get("harm") or ())))
    return out


def _covers(key: str, category: str) -> bool:
    """An ICD-10 code or range (``X00-X09``) of a correspondence covers a 3-character category."""
    lo, _, hi = key.partition("-")
    return lo[:3] <= category <= (hi or lo)[:3]


def typologies_for(source: Source, categories: list[str]) -> list[str]:
    """The typologies a field's correspondence gives the lead's categories (empty: the field does not apply)."""
    return sorted({t for key, ts in source.codes for c in categories if _covers(key, c) for t in ts})


@dataclass
class Corroboration:
    tested: bool
    source: str = ""
    label: str = ""
    observed: float = float("nan")
    null_median: float = float("nan")
    p: float = 1.0
    detail: dict[str, Any] | None = None

    def asdict(self) -> dict[str, Any]:
        return {"tested": self.tested, "source": self.source, "label": self.label, "observed": self.observed,
                "null_median": self.null_median, "p": self.p, **(self.detail or {})}


# ---------------------------------------------------------------------- readers (cached under the store)


def field_events(name: str, harm: tuple[str, ...] = ()) -> pa.Table:
    """A context field's events, 2010 on: u (6 digits), year, typology, and ``harmed`` the people its declared harm
    columns count (pegasus_data's `load_field`)."""
    key = {"what": "field_events", "field": name, "harm": list(harm), "data": config.data_version()}
    hit = store.get_table("corroborate", key)
    if hit is not None:
        return hit
    raw = gateway.raw_field(name, list(range(2010, 2025)))
    con = duckdb.connect()
    con.register("r", raw)
    harmed = " + ".join(f'coalesce(TRY_CAST("{c}" AS DOUBLE), 0)' for c in harm) or "0"
    t = con.execute(f"""SELECT CAST(municipality AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, typology,
        CAST({harmed} AS DOUBLE) AS harmed FROM r""").fetch_arrow_table()
    store.put_table("corroborate", key, t, {"source": f"pegasus_data.load_field({name})"})
    return t


def source_year(source: Source, year: int) -> pa.Table:
    """A source's events of a year by residence × 3-character ICD-10 category: y, and k the expected number linked to
    the lead's system (0 without a link)."""
    key = {"what": "source_year", "dataset": source.dataset, "event": source.event, "column": source.column,
           "link": list(source.link or ()), "year": year, "data": config.data_version()}
    hit = store.get_table("corroborate", key)
    if hit is not None:
        return hit
    if source.link:
        t = gateway.linked_counts(source.dataset, source.event, year, source.link[0], source.link[1],
                                  classifier=source.column).counts
        y, k = "n", "k"
    else:
        t = gateway.event_counts(source.dataset, source.event, year, classifier=source.column).counts
        y, k = "y", "0"
    con = duckdb.connect()
    con.register("t", t)
    out = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, left(upper(code), 3) AS code,
        CAST(sum({y}) AS DOUBLE) AS y, CAST(sum({k}) AS DOUBLE) AS k FROM t GROUP BY ALL""").fetch_arrow_table()
    store.put_table("corroborate", key, out, {"source": source.label, "year": year})
    return out


# ---------------------------------------------------------------------- matrices of the corroborating field


class Fields:
    """The corroborating fields on the session's grid (places × years), loaded once."""

    def __init__(self, places: np.ndarray, years: np.ndarray, state_of: np.ndarray, population: np.ndarray,
                 edges: np.ndarray | None = None):
        self.places, self.years = places, np.asarray(years)
        self.edges = edges      # the graph (pairs of indices into ``places``): the null of a connected lead is connected sets
        self._adjacent: list[np.ndarray] | None = None
        self.state = state_of
        self.quintile = np.digitize(population, np.quantile(population, [0.2, 0.4, 0.6, 0.8]))
        self._index = {int(u): i for i, u in enumerate(places)}
        self._cache: dict[Any, Any] = {}

    def adjacent(self) -> list[np.ndarray]:
        """The neighbours of every place (the graph's adjacency lists), built once."""
        if self._adjacent is None:
            e = np.concatenate([self.edges, self.edges[:, ::-1]])
            order = np.argsort(e[:, 0], kind="stable")
            e = e[order]
            cut = np.searchsorted(e[:, 0], np.arange(len(self.places) + 1))
            self._adjacent = [e[cut[i]:cut[i + 1], 1] for i in range(len(self.places))]
        return self._adjacent

    def field(self, source: Source, typologies: list[str]) -> np.ndarray:
        """People harmed [place, year] in a context field's events of the typologies (its declared harm columns; the
        events themselves when it declares none)."""
        key = ("field", source, tuple(typologies))
        if key not in self._cache:
            t = field_events(source.dataset, source.harm)
            u, yr, ty, h = (t.column(c).to_numpy(zero_copy_only=False) for c in ("u", "year", "typology", "harmed"))
            ok = np.isin(yr, self.years) & np.isin(ty, typologies)
            out = np.zeros((len(self.places), len(self.years)))
            ti = {int(y): j for j, y in enumerate(self.years)}
            for a, b, v in zip(u[ok], yr[ok], h[ok], strict=True):
                i = self._index.get(int(a))
                if i is not None:
                    out[i, ti[int(b)]] += float(v) if source.harm else 1.0
            self._cache[key] = out
        return self._cache[key]

    def _table(self, source: Source) -> pa.Table | None:
        if ("table", source) not in self._cache:
            parts = []
            for y in self.years:
                try:
                    t = source_year(source, int(y))
                except gateway.nothing_published():      # not published for the year (chikungunya before 2015): no events
                    continue
                parts.append(t.append_column("year", pa.array(np.full(t.num_rows, int(y), dtype=np.int16))))
            self._cache[("table", source)] = pa.concat_tables(parts) if parts else None
        return self._cache[("table", source)]

    def holds(self, source: Source, categories: list[str]) -> bool:
        """Whether the source has any event of the categories (its own codes; a field by its correspondence)."""
        if source.kind == "field":
            return bool(typologies_for(source, categories))
        key = ("codes", source)
        if key not in self._cache:
            t = self._table(source)
            self._cache[key] = set() if t is None else set(t.column("code").to_pylist())
        return bool(self._cache[key] & set(categories))

    def events(self, source: Source, categories: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """(events not linked to the lead's system, expected linked) [place, year] for the 3-character categories."""
        key = ("events", source, tuple(sorted(categories)))
        if key not in self._cache:
            t = self._table(source)
            free = np.zeros((len(self.places), len(self.years)))
            linked = np.zeros_like(free)
            if t is not None:
                con = duckdb.connect()
                con.register("s", t)
                con.register("c", pa.table({"code": sorted(categories)}))
                r = con.execute("SELECT u, year, sum(y) AS y, sum(k) AS k FROM s WHERE code IN (SELECT code FROM c) "
                                "GROUP BY ALL").fetch_arrow_table()
                ti = {int(y): j for j, y in enumerate(self.years)}
                for a, b, v, k in zip(*(r.column(c).to_pylist() for c in ("u", "year", "y", "k")), strict=True):
                    i = self._index.get(int(a)) if a is not None else None
                    if i is not None:
                        free[i, ti[int(b)]] += float(v) - float(k)
                        linked[i, ti[int(b)]] += float(k)
            self._cache[key] = (free, linked)
        return self._cache[key]


# ---------------------------------------------------------------------- the test


def _components(fields: Fields, rows: np.ndarray) -> list[np.ndarray]:
    """The connected components of ``rows`` in the graph (a lead's places that touch form one cluster)."""
    adj, member, comps = fields.adjacent(), {int(r) for r in rows}, []
    seen: set[int] = set()
    for r in rows:
        if int(r) in seen:
            continue
        stack, comp = [int(r)], []
        seen.add(int(r))
        while stack:
            a = stack.pop()
            comp.append(a)
            for b in adj[a]:
                if int(b) in member and int(b) not in seen:
                    seen.add(int(b))
                    stack.append(int(b))
        comps.append(np.array(comp, dtype=np.int64))
    return comps


def _grow(adj: list[np.ndarray], seed: int, size: int, rng: np.random.Generator) -> list[int]:
    """A random connected set of ``size`` places grown from ``seed`` (a random frontier place each step); it stops
    short where the component runs out."""
    chosen, frontier, inside = [seed], [], {seed}
    frontier.extend(int(b) for b in adj[seed])
    while len(chosen) < size and frontier:
        k = int(rng.integers(len(frontier)))
        frontier[k], frontier[-1] = frontier[-1], frontier[k]
        a = frontier.pop()
        if a in inside:
            continue
        inside.add(a)
        chosen.append(a)
        frontier.extend(int(b) for b in adj[a] if int(b) not in inside)
    return chosen


def _null_sets(fields: Fields, rows: np.ndarray, rng: np.random.Generator, replicates: int, connected: bool = True
               ) -> np.ndarray:
    """[replicates, len(rows)] place indices. A lead's places that touch each other are a cluster, and a cluster
    shares its neighbours' shocks in the other field: each cluster of c places is replaced by a random connected set
    of c places grown from a random seed of the cluster's state (``connected``; a set that cannot reach c places is
    redrawn). Places with no neighbour in the lead, and every place when ``connected`` is False or the graph is
    unknown, are replaced by a random place of the same state and population quintile (the state alone if fewer than
    five), distinct within a draw where possible."""
    out = np.empty((replicates, len(rows)), dtype=np.int64)
    position = {int(r): j for j, r in enumerate(rows)}
    rest = list(range(len(rows)))
    if connected and fields.edges is not None:
        adj = fields.adjacent()
        for comp in _components(fields, rows):
            if len(comp) < 2:
                continue
            cols = [position[int(r)] for r in comp]
            pool = np.nonzero(fields.state == fields.state[comp[0]])[0]
            for k in range(replicates):
                for _ in range(20):
                    got = _grow(adj, int(rng.choice(pool)), len(comp), rng)
                    if len(got) == len(comp):
                        break
                else:
                    got = list(rng.choice(pool, size=len(comp), replace=True))
                out[k, cols] = got
            rest = [j for j in rest if j not in set(cols)]
    for j in rest:
        r = rows[j]
        same = np.nonzero((fields.state == fields.state[r]) & (fields.quintile == fields.quintile[r]))[0]
        if same.size < 5:
            same = np.nonzero(fields.state == fields.state[r])[0]
        out[:, j] = rng.choice(same, size=replicates, replace=True)
    return out


def corroborate(fields: Fields, source: Source, categories: list[str], rows: np.ndarray, years: list[int],
                direction: int, seed_text: str, replicates: int = 4999, connected: bool = True) -> Corroboration:
    """Is the lead's place set × years unusual in the independent field, against the field's own variation?"""
    sid = f"{source.kind}:{source.dataset}:{source.event}"
    if direction <= 0:
        return Corroboration(False, sid, source.label, detail={"reason": "a deficit is not corroborated by a field"})
    cols = (fields.years >= years[0]) & (fields.years <= years[-1])
    other = ~cols
    rng = np.random.default_rng(config.seed(seed_text))
    detail: dict[str, Any] = {}

    if source.kind == "field":
        m = fields.field(source, typologies_for(source, categories))
        obs = float(m[rows][:, cols].sum())        # people the registry reports harmed at the places in the window

        def null_of(sets: np.ndarray) -> np.ndarray:
            return m[sets][:, :, cols].sum((1, 2)).astype(float)

        detail["unit"] = ("people the registry reports harmed" if source.harm else "registered events") +             " at the places in the window"
    else:
        y, linked = fields.events(source, categories)
        tot = float(y[rows][:, cols].sum() + linked[rows][:, cols].sum())
        if source.link:
            detail["overlap"] = float(linked[rows][:, cols].sum() / tot) if tot > 0 else 0.0
        base = np.median(y[:, other], axis=1) if other.any() else np.zeros(len(y))

        def ratio(r: np.ndarray) -> np.ndarray:
            observed = y[r][..., cols].sum((-1, -2))
            expected = base[r].sum(-1) * cols.sum()
            return np.log((observed + 0.5) / (expected + 0.5))

        obs = float(ratio(rows))
        null_of = ratio
        detail["unit"] = "log (window count + ½) / (the places' median year × years + ½)"
        detail["observed_count"] = float(y[rows][:, cols].sum())
    chunk = max(1, min(replicates, int(2e7 // max(len(rows) * int(cols.sum()), 1))))      # bounded memory at any replicate count
    null = np.concatenate([null_of(_null_sets(fields, rows, rng, min(chunk, replicates - i), connected))
                           for i in range(0, replicates, chunk)])
    p = float((1 + np.sum(null >= obs)) / (1 + len(null)))
    if source.kind == "field" and obs == 0:
        p = 1.0
    detail["replicates"] = replicates
    return Corroboration(True, sid, source.label, obs, float(np.median(null)), p, detail)


def categories_of(registry, node: str) -> list[str]:
    """The distinct 3-character ICD-10 categories under a node of the SIM code tree."""
    return sorted({c[:3] for c in registry.leaves(node) if re.match(r"^[A-Z]\d\d", c)})
