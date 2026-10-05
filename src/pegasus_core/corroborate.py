"""Corroboration: an effect seen again in an independent field (ARCHITECTURE §8.3, tier R3).

A one-off event (a dam collapse, an epidemic year, a fire) cannot recur in the other temporal half, and a
split of its own events says only that it is not a selection artefact. What confirms it is a second
measurement of the same place and time that does not share the first one's records: deaths (SIM) against
the disaster registry (S2iD), against notifications (SINAN) or against admissions (SIH).

**The null is the corroborating field's own.** The statistic is computed on the lead's places and years in
that field; the null is the same statistic on random place sets of the same size, in the same states, matched
on population (a quintile of the nation's municipalities), over the same years. A place set that is as active
as the lead in the other field by the field's own variation, in a year when the whole state was, does not
corroborate. The p-value is (1 + #{null ≥ observed}) / (1 + B), so its floor is 1/(B + 1).

**Overlap (§8.5).** SIM deaths and SIH admissions share the person who died in hospital, so the SIH count
excludes admissions that ended in death (MORTE), and the share the exclusion removed is recorded as the
measured upper bound of the overlap. S2iD and SINAN share no record with SIM.

The rules (which field corroborates which codes) are data: `RULES`.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
from pegasus_data._request import NothingPublished

from . import config, gateway, store

#: SIM code prefix → the independent field. ``s2id``: COBRADE typologies; ``sinan``: (dataset, event);
#: ``sih``: admissions of the same ICD-10 category.
MASS = ["Movimento de Massa", "Rompimento/Colapso de barragens", "Erosão"]
WATER = ["Inundações", "Enxurradas", "Alagamentos", "Chuvas Intensas"]
STORM = ["Vendavais e Ciclones", "Tornado", "Granizo", "Chuvas Intensas"]
RULES: list[dict[str, Any]] = [
    {"prefix": ("X36",), "source": "s2id", "typologies": MASS, "label": "S2iD, mass movement or dam collapse"},
    {"prefix": ("X37",), "source": "s2id", "typologies": STORM, "label": "S2iD, storm"},
    {"prefix": ("X38",), "source": "s2id", "typologies": WATER, "label": "S2iD, flood"},
    {"prefix": ("X30",), "source": "s2id", "typologies": ["Onda de Calor e Baixa Umidade"], "label": "S2iD, heat wave"},
    {"prefix": ("X31",), "source": "s2id", "typologies": ["Onda de Frio"], "label": "S2iD, cold wave"},
    {"prefix": ("X00", "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08", "X09"), "source": "s2id",
     "typologies": ["Incêndio Florestal"], "label": "S2iD, wildfire"},
    {"prefix": ("A92",), "source": "sinan", "system": ("SINAN-CHIK", "notification"), "label": "SINAN chikungunya notifications"},
    {"prefix": ("A90", "A91"), "source": "sinan", "system": ("SINAN-DENG", "probable_case"), "label": "SINAN dengue probable cases"},
    {"prefix": ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q"), "source": "sih",
     "label": "SIH admissions (survivors) of the same category"},
]


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


def rule_for(code: str) -> dict[str, Any] | None:
    for r in RULES:
        if any(code.startswith(p) for p in r["prefix"]):
            return r
    return None


# ---------------------------------------------------------------------- readers (cached under the store)


def s2id_events() -> pa.Table:
    """Every S2iD event, 2010 on: u (6 digits), year, typology, group, deaths."""
    import pegasus_data as pg

    key = {"what": "s2id", "data": config.data_version()}
    hit = store.get_table("corroborate", key)
    if hit is not None:
        return hit
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.load_field("disasters", years=list(range(2010, 2025)), settings=pg.load_settings(root=config.data_root()))
    con = duckdb.connect()
    con.register("r", raw)
    t = con.execute("""SELECT CAST(municipality AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, typology,
        "group" AS grp, cobrade, CAST(deaths AS INTEGER) AS deaths FROM r""").fetch_arrow_table()
    store.put_table("corroborate", key, t, {"source": "pegasus_data.load_field(disasters)"})
    return t


def sih_year(year: int) -> pa.Table:
    """SIH-RD admissions of a year by residence × ICD-10 category (3 characters) × in-hospital death."""
    import pegasus_data as pg

    key = {"what": "sih", "year": year, "data": config.data_version(), "v": 1}
    hit = store.get_table("corroborate", key)
    if hit is not None:
        return hit
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.count_events("SIH-RD", "hospitalisation", period=year, geography="BR",
                              by=["MUNIC_RES", "DIAG_PRINC", "MORTE"], root=config.data_root(),
                              allow_partial=False, max_download=8 * 1024**3)
    con = duckdb.connect()
    con.register("r", raw)
    t = con.execute(f"""SELECT CAST({gateway._residence_sql('MUNIC_RES')} AS INTEGER) AS u,
        left(upper(trim(CAST(DIAG_PRINC AS VARCHAR))), 3) AS code,
        CAST(coalesce(TRY_CAST(MORTE AS INTEGER), 0) AS TINYINT) AS dead, CAST(sum(events) AS INTEGER) AS y
        FROM r GROUP BY ALL""").fetch_arrow_table()
    store.put_table("corroborate", key, t, {"source": "pegasus_data.count_events(SIH-RD)", "year": year})
    return t


def sinan_matrix(dataset: str, event: str, places: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Notifications [place, year] of a SINAN system (all strata summed)."""
    out = np.zeros((len(places), len(years)))
    index = {int(u): i for i, u in enumerate(places)}
    for j, year in enumerate(years):
        try:
            counts = gateway.event_counts(dataset, event, int(year), places=pa.array(places.astype(np.int64))).counts
        except NothingPublished:      # the system is not published for the year (chikungunya before 2015): no events
            continue
        u = counts.column("u").to_numpy()
        y = counts.column("y").to_numpy()
        rows = np.array([index.get(int(x), -1) for x in u])
        ok = rows >= 0
        np.add.at(out[:, j], rows[ok], y[ok])
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
        self._cache: dict[Any, np.ndarray] = {}
        self._sih: pa.Table | None = None
        self._s2id: pa.Table | None = None

    def adjacent(self) -> list[np.ndarray]:
        """The neighbours of every place (the graph's adjacency lists), built once."""
        if self._adjacent is None:
            e = np.concatenate([self.edges, self.edges[:, ::-1]])
            order = np.argsort(e[:, 0], kind="stable")
            e = e[order]
            cut = np.searchsorted(e[:, 0], np.arange(len(self.places) + 1))
            self._adjacent = [e[cut[i]:cut[i + 1], 1] for i in range(len(self.places))]
        return self._adjacent

    # -- S2iD
    def s2id(self, typologies: list[str] | None) -> np.ndarray:
        key = ("s2id", tuple(typologies) if typologies else None)
        if key not in self._cache:
            t = s2id_events()
            u, yr, ty = (t.column(c).to_numpy(zero_copy_only=False) for c in ("u", "year", "typology"))
            ok = np.isin(yr, self.years) & (np.isin(ty, typologies) if typologies else True)
            out = np.zeros((len(self.places), len(self.years)))
            ti = {int(y): j for j, y in enumerate(self.years)}
            for a, b in zip(u[ok], yr[ok], strict=True):
                i = self._index.get(int(a))
                if i is not None:
                    out[i, ti[int(b)]] += 1
            self._cache[key] = out
        return self._cache[key]

    # -- SINAN
    def sinan(self, system: tuple[str, str]) -> np.ndarray:
        key = ("sinan", system)
        if key not in self._cache:
            self._cache[key] = sinan_matrix(system[0], system[1], self.places, self.years)
        return self._cache[key]

    # -- SIH
    def _sih_all(self) -> pa.Table:
        if self._sih is None:
            parts = []
            for y in self.years:
                t = sih_year(int(y))
                parts.append(t.append_column("year", pa.array(np.full(t.num_rows, int(y), dtype=np.int16))))
            self._sih = pa.concat_tables(parts)
        return self._sih

    def sih(self, categories: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """(survivors, died in hospital) [place, year] for the 3-character categories."""
        key = ("sih", tuple(sorted(categories)))
        if key not in self._cache:
            t = self._sih_all()
            con = duckdb.connect()
            con.register("s", t)
            con.register("c", pa.table({"code": sorted(categories)}))
            r = con.execute("""SELECT u, year, dead, sum(y) AS y FROM s WHERE code IN (SELECT code FROM c) GROUP BY ALL"""
                            ).fetch_arrow_table()
            alive = np.zeros((len(self.places), len(self.years)))
            dead = np.zeros_like(alive)
            ti = {int(y): j for j, y in enumerate(self.years)}
            for a, b, d, v in zip(*(r.column(c).to_pylist() for c in ("u", "year", "dead", "y")), strict=True):
                i = self._index.get(int(a))
                if i is not None:
                    (dead if d else alive)[i, ti[int(b)]] += float(v)
            self._cache[key] = (alive, dead)
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


def corroborate(fields: Fields, code: str, categories: list[str], rows: np.ndarray, years: list[int], direction: int,
                seed_text: str, replicates: int = 4999, connected: bool = True) -> Corroboration:
    """Is the lead's place set × years unusual in the independent field, against the field's own variation?"""
    rule = rule_for(code)
    if rule is None:
        return Corroboration(False, detail={"reason": "no independent field for this code"})
    if direction <= 0:
        return Corroboration(False, rule["source"], rule["label"], detail={"reason": "a deficit is not corroborated by a field"})
    cols = (fields.years >= years[0]) & (fields.years <= years[-1])
    other = ~cols
    rng = np.random.default_rng(config.seed(seed_text))
    detail: dict[str, Any] = {}

    if rule["source"] == "s2id":
        m = fields.s2id(rule.get("typologies"))
        obs = float((m[rows][:, cols].sum(1) > 0).sum())      # places with a registered disaster in the window

        def null_of(sets: np.ndarray) -> np.ndarray:
            return (m[sets][:, :, cols].sum(2) > 0).sum(1).astype(float)

        detail["unit"] = "places with a registered disaster in the window"
    else:
        if rule["source"] == "sinan":
            y = fields.sinan(rule["system"])
        else:
            alive, dead = fields.sih(categories)
            y = alive
            tot = float(alive[rows][:, cols].sum() + dead[rows][:, cols].sum())
            detail["overlap_upper_bound"] = float(dead[rows][:, cols].sum() / tot) if tot > 0 else 0.0
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
    if rule["source"] == "s2id" and obs == 0:
        p = 1.0
    detail["replicates"] = replicates
    return Corroboration(True, rule["source"], rule["label"], obs, float(np.median(null)), p, detail)


def categories_of(registry, node: str) -> list[str]:
    """The distinct 3-character ICD-10 categories under a node of the SIM code tree."""
    return sorted({c[:3] for c in registry.leaves(node) if re.match(r"^[A-Z]\d\d", c)})
