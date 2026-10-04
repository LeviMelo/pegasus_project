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
_TREES = ("ICD10", "SIGTAP", "CBO2002", "CNAE20")  # pegasus_data's code_trees.parquet


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

    The columns come from pegasus_data's roles (the subject's residence, sex and age as
    strata). ``classifier`` defaults to the event type's primary classifier; an event type
    without one (births, a notifiable disease) has the single code ``*``. A subject without a
    sex stratum takes the sex its entity implies (a mother: 2), or fails. ``places`` is the
    set of valid municipalities (the population's); a residence outside it is unallocated,
    never guessed.
    """
    import pegasus_data as pg

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
    column = classifier or (primary[0] if primary else None)
    strata = _strata(dataset)
    key = {"what": "event_counts", "dataset": dataset, "event": event, "year": year, "classifier": column,
           "data": config.data_version(), "gateway": 2 if dataset != "SIM.DO" else 1}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    by = [strata["residence"], strata["age"]] + ([strata["sex"]] if strata["sex"] else []) + ([column] if column else [])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.count_events(dataset, event, period=year, geography="BR", by=by, root=config.data_root(),
                              allow_partial=False, max_download=8 * 1024**3)
    con = duckdb.connect()
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    sex = (f"""CASE WHEN "{strata['sex']}" IN ('1', 'M') THEN 1 WHEN "{strata['sex']}" IN ('2', 'F') THEN 2 END"""
           if strata["sex"] else str(strata["implied_sex"]))
    code = f'upper(trim("{column}"))' if column else "'*'"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT
            TRY_CAST(left(CAST("{strata['residence']}" AS VARCHAR), 6) AS INTEGER) AS u,
            {sex} AS sex,
            CAST(least(floor(TRY_CAST("{strata['age']}" AS DOUBLE)), {MAX_AGE}) AS SMALLINT) AS age,
            {code} AS code, CAST(events AS INTEGER) AS y
        FROM r""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex,
            age, code, CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NULL
            GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.count_events({dataset}, {event})", "by": by})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def _records(dataset: str, event: str, year: int, columns: list[str]) -> pa.Table:
    """Raw-coded records of one event type for one year (the event type's status applied)."""
    import pegasus_data as pg
    import pyarrow.compute as pc

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    status = spec.get("status") or {}
    wanted = list(dict.fromkeys(columns + ([status["column"]] if status.get("column") else [])))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = pg.query(dataset, period=year, geography="BR", select=wanted, present="codes",
                         root=config.data_root(), max_download=8 * 1024**3)
    if status.get("column"):
        table = table.filter(pc.is_in(pc.cast(table[status["column"]], pa.string()),
                                      value_set=pa.array([str(v) for v in status["values"]])))
    return table


def _sex_sql(strata: dict) -> str:
    if strata["sex"] is None:
        return str(strata["implied_sex"])
    col = f'CAST("{strata["sex"]}" AS VARCHAR)'
    return f"CASE WHEN {col} IN ('1', 'M') THEN 1 WHEN {col} IN ('2', 'F') THEN 2 END"


def _cells_sql(strata: dict) -> str:
    return (f'TRY_CAST(left(CAST("{strata["residence"]}" AS VARCHAR), 6) AS INTEGER) AS u, {_sex_sql(strata)} AS sex, '
            f'CAST(least(floor(TRY_CAST(CAST("{strata["age"]}" AS VARCHAR) AS DOUBLE)), {MAX_AGE}) AS SMALLINT) AS age')


def mark_moments(dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float],
                 classifier: str | None = None, places: pa.Array | None = None) -> EventCounts:
    """Accumulator states of a positive numeric mark per (u, year, sex, age, code): n, Σm, Σm²,
    Σlog m, Σ(log m)² (ARCHITECTURE §4.4; handoff §4 asks pegasus_data to serve these).
    Values outside ``bounds`` (sentinels, impossible values) and missing values are counted
    as unallocated with their reason, never dropped silently."""
    strata = _strata(dataset)
    key = {"what": "mark_moments", "dataset": dataset, "event": event, "year": year, "mark": mark,
           "bounds": list(bounds), "classifier": classifier, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], strata["age"], mark] + ([strata["sex"]] if strata["sex"] else []) + \
        ([classifier] if classifier else [])
    con = duckdb.connect()
    con.register("r", _records(dataset, event, year, cols))
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata)}, {code} AS code,
            TRY_CAST(CAST("{mark}" AS VARCHAR) AS DOUBLE) AS m FROM r""")
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                      WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                      WHEN code IS NULL OR code = '' THEN 'code' WHEN m IS NULL THEN 'mark missing'
                      WHEN m < {bounds[0]} OR m > {bounds[1]} THEN 'mark out of bounds' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(count(*) AS INTEGER) AS n, sum(m) AS s1,
            sum(m * m) AS s2, sum(ln(m)) AS l1, sum(ln(m) * ln(m)) AS l2
        FROM e WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(count(*) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): moments of {mark}"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def code_list_counts(dataset: str, event: str, year: int, column: str,
                     places: pa.Array | None = None) -> EventCounts:
    """Events per (u, year, sex, age, ICD category) for a column that holds several codes
    concatenated (SINASC's CODANOMAL: "Q02Q690"): an event counts once under each distinct
    category it carries. Events carrying none are the complement, not counted here."""
    strata = _strata(dataset)
    key = {"what": "code_list_counts", "dataset": dataset, "event": event, "year": year, "column": column,
           "data": config.data_version()}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], strata["age"], column] + ([strata["sex"]] if strata["sex"] else [])
    con = duckdb.connect()
    con.register("r", _records(dataset, event, year, cols))
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata)},
            list_distinct(list_transform(regexp_extract_all(upper(CAST("{column}" AS VARCHAR)),
                '[A-Z][0-9]{{2}}[0-9X]?'), x -> left(x, 3))) AS codes
        FROM r WHERE "{column}" IS NOT NULL AND trim(CAST("{column}" AS VARCHAR)) <> ''""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN len(codes) = 0 THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(count(*) AS INTEGER) AS y
        FROM (SELECT u, sex, age, unnest(codes) AS code FROM e WHERE ({reason}) IS NULL)
        GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, NULL AS code,
            CAST(count(*) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): {column} exploded"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def _strata(dataset: str) -> dict:
    """The subject's residence, sex and age columns, from pegasus_data's roles."""
    import pegasus_data as pg

    rows = [r for r in pg.roles(dataset) if r.get("model") == "stratum"]
    by_prop = {r["property"]: r for r in rows}
    if "residence" not in by_prop:
        raise LookupError(f"{dataset}: no residence stratum in pegasus_data's roles")
    age = by_prop.get("age_years") or by_prop.get("age")
    if age is None:
        raise LookupError(f"{dataset}: no age stratum in pegasus_data's roles")
    entity = by_prop["residence"]["entity"]
    implied = {"mother": 2}.get(entity)
    if "sex" not in by_prop and implied is None:
        raise LookupError(f"{dataset}: no sex stratum, and entity {entity!r} implies none")
    return {"residence": by_prop["residence"]["column"], "age": age["column"],
            "sex": by_prop["sex"]["column"] if "sex" in by_prop else None, "implied_sex": implied, "entity": entity}


def code_structure(name: str) -> pa.Table:
    """A code structure as served by pegasus_data (a tree's parent table or a list's memberships)."""
    import pegasus_data as pg

    key = {"what": "code_structure", "name": name, "data": config.data_version(),
           "resource": config.resource_version("code_trees.parquet" if name in _TREES else "code_lists.parquet")}
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

    key = {"what": "proximity_graph", "kind": kind, "data": config.data_version(),
           "resource": config.resource_version("proximity.parquet")}
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
