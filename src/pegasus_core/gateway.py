"""The one door to pegasus_data (ARCHITECTURE §2, §11.1).

Every input of PegaSUS comes through here: populations, event counts, code
structures. Results are Arrow tables, cached in the store under a key that
includes the data version. Nothing is dropped silently: events that cannot be
placed in a cell (unknown municipality, sex or age) are returned beside the
counts as ``unallocated``.

Places are 6-digit IBGE municipality codes (SIM, SIH and SINASC write 6 digits;
POPSVS writes 7, whose last digit is the check digit and is removed).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import duckdb
import numpy as np
import pyarrow as pa

from . import config, store

MAX_AGE = 80  # POPSVS closes at 80+


@dataclass(frozen=True)
class EventCounts:
    """Counts of one event type per (municipality, year, sex, single age, code), non-empty cells only."""

    counts: pa.Table        # u:int32, year:int16, sex:int8, age:int16, code:string, y:int32
    unallocated: pa.Table   # year, reason, code, y
    key: dict


def population(years: range | list[int], series: str = "POPSVS") -> pa.Table:
    """Person-years by (u, year, sex, age 0..80): u 6-digit, sex 1 male / 2 female."""
    import pegasus_data as pg

    years = sorted(set(years))
    key = {"what": "population", "series": series, "years": years, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    raw = pg.load_population(series=series, years=years, by=("municipality", "year", "sex", "age"),
                             root=config.population_root())
    con = duckdb.connect()
    con.register("p", raw)
    table = con.execute(f"""
        SELECT CAST(municipality // 10 AS INTEGER) AS u, CAST(year AS SMALLINT) AS year,
               CAST(sex AS TINYINT) AS sex, CAST(least(age, {MAX_AGE}) AS SMALLINT) AS age,
               CAST(sum(population) AS DOUBLE) AS n
        FROM p WHERE sex IN ('1', '2') GROUP BY ALL ORDER BY u, year, sex, age""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"pegasus_data.load_population({series})"})
    return table


def event_counts(dataset: str, event: str, year: int, classifier: str | None = None,
                 places: pa.Array | None = None) -> EventCounts:
    """One event type's counts for one year, by residence × sex × age × the classifier's code.

    ``classifier`` defaults to the event type's primary classifier. ``places`` is
    the set of valid municipalities (the population's); a residence outside it
    is unallocated, never guessed.
    """
    import pegasus_data as pg

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    column = classifier or next(c["column"] for c in spec["classifiers"] if c["role"] == "primary")
    residence = _residence_column(dataset)
    key = {"what": "event_counts", "dataset": dataset, "event": event, "year": year, "classifier": column,
           "data": config.data_version(), "gateway": 1}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.count_events(dataset, event, period=year, geography="BR",
                              by=[residence, "SEXO", "IDADE_anos", column], root=config.data_root(),
                              allow_partial=False, max_download=4 * 1024**3)
    con = duckdb.connect()
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    con.execute(f"""CREATE TEMP TABLE e AS SELECT
            TRY_CAST("{residence}" AS INTEGER) AS u,
            CASE WHEN "SEXO" IN ('1', 'M') THEN 1 WHEN "SEXO" IN ('2', 'F') THEN 2 END AS sex,
            CAST(least(floor("IDADE_anos"), {MAX_AGE}) AS SMALLINT) AS age,
            upper(trim("{column}")) AS code, CAST(events AS INTEGER) AS y
        FROM r""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex,
            age, code, CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NULL
            GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.count_events({dataset}, {event})"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def code_structure(name: str) -> pa.Table:
    """A code structure as served by pegasus_data (a tree's parent table or a list's memberships)."""
    import pegasus_data as pg

    key = {"what": "code_structure", "name": name, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    table = pg.code_structure(name)
    store.put_table("gateway", key, table)
    return table


def municipality_points(places) -> np.ndarray:
    """(lon, lat) of each municipality's population centre (Census 2022), in the given order."""
    import pegasus_data as pg

    points = [pg.municipality_point(str(int(c)), kind="population") for c in places]
    missing = [int(c) for c, p in zip(places, points, strict=True) if p is None]
    if missing:
        raise LookupError(f"no population point for {len(missing)} municipalities, e.g. {missing[:5]}")
    return np.array(points, dtype=float)


def proximity_graph(kind: str) -> pa.Table:
    """A shipped graph over municipalities: (a, b, weight) with 6-digit codes, both directions.
    ``contiguity`` weights are shared border lengths (km); ``population_distance`` weights
    are distances (km) between population centres."""
    import pegasus_data as pg

    key = {"what": "proximity_graph", "kind": kind, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    raw = pg.proximity_graph(kind)
    con = duckdb.connect()
    con.register("g", raw)
    table = con.execute("""SELECT CAST(CAST("from" AS INTEGER) // 10 AS INTEGER) AS a,
            CAST(CAST("to" AS INTEGER) // 10 AS INTEGER) AS b, CAST(weight AS DOUBLE) AS weight,
            CAST(vintage AS INTEGER) AS vintage FROM g ORDER BY a, b""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"pegasus_data.proximity_graph({kind})"})
    return table


def regions(places, classification: str) -> np.ndarray:
    """The unit of ``classification`` (``ibge_immediate_region``, ``health_region``, ``uf``,
    ``ibge_macroregion``…) each place belongs to, as strings in the given order; a place
    without one raises (never guessed)."""
    import pegasus_data as pg

    out = []
    for c in places:
        m = pg.memberships(str(int(c))).get(classification)
        if m is None:
            raise LookupError(f"municipality {int(c)} has no {classification} membership in pegasus_data")
        out.append(m.member_code)
    return np.array(out)


def field_overlap(dataset: str, event: str, a: dict[str, list[str]], b: dict[str, list[str]],
                  period: object) -> dict:
    """Measured share of events two fields have in common (ARCHITECTURE §8.5), from records."""
    import pegasus_data as pg

    key = {"what": "overlap", "dataset": dataset, "event": event, "a": a, "b": b, "period": str(period),
           "data": config.data_version()}
    cached = store.manifest("gateway", key)
    if cached is not None and "overlap" in cached:
        return cached["overlap"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = pg.field_overlap(dataset, event, a, b, period=period, root=config.data_root())
    store.put_table("gateway", key, pa.table({"x": [0]}), {"overlap": result})
    return result


def _residence_column(dataset: str) -> str:
    import pegasus_data as pg

    for role in pg.roles(dataset):
        if role.get("kind") == "place" and role.get("property") == "residence" and role.get("model") == "stratum":
            return str(role["column"])
    raise LookupError(f"{dataset}: no residence column declared in pegasus_data's roles")
