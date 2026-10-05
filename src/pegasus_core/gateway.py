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
import pyarrow.compute as pc

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
           "data": config.data_version(), "gateway": 3 if dataset != "SIM.DO" else 1,
           **_df_key(dataset, year)}
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
    sex = _sex_sql(strata, dataset, raw)
    code = f'upper(trim("{column}"))' if column else "'*'"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT
            {_residence_sql(strata['residence'])} AS u,
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


def _residence_sql(column: str) -> str:
    """The residence municipality (6 digits) of a record. The Federal District has one municipality,
    Brasília (530010): SIH-RD writes DF residents' administrative-region codes (530020 … 530180) in
    MUNIC_RES up to 2017, 141,325 admissions in 2017 against 11,297 under 530010 itself, and TabNet
    counts all 152,622 under 530010 (measured 2026-10-05). Any 53xxxx is therefore Brasília."""
    x = f'CAST("{column}" AS VARCHAR)'
    return f"CASE WHEN left({x}, 2) = '53' THEN 530010 ELSE TRY_CAST(left({x}, 6) AS INTEGER) END"


def _df_key(dataset: str, year: int) -> dict:
    """Cache-key part for the DF residence rule: only SIH years before 2018 differ (later years
    hold no administrative-region codes), so only those caches are rebuilt."""
    return {"df_residence": 1} if dataset.startswith("SIH") and year < 2018 else {}


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
    if status.get("column") and status.get("values"):
        table = table.filter(pc.is_in(pc.cast(table[status["column"]], pa.string()),
                                      value_set=pa.array([str(v) for v in status["values"]])))
    if status.get("column") and status.get("excluded"):
        col = pc.cast(table[status["column"]], pa.string())
        table = table.filter(pc.invert(pc.fill_null(pc.is_in(col, value_set=pa.array(
            [str(v) for v in status["excluded"]])), False)))
    return table


def _when(dataset: str) -> str:
    """The event's date column from the roles: onset where declared (the epidemic curve's time),
    else the event's own date, start, or birth date."""
    import pegasus_data as pg

    rows = {r["property"]: r["column"] for r in pg.roles(dataset) if r.get("model") == "when" and r.get("kind") == "date"}
    for prop in ("onset", "date", "start", "birth_date"):
        if prop in rows:
            return rows[prop]
    raise LookupError(f"{dataset}: no event date among its roles")


def _date_sql(column: str) -> str:
    """An event date from raw text in the forms the systems write: ISO 'YYYY-MM-DD' (dates
    pegasus_data types), eight digits YYYYMMDD (SINAN families left raw) and eight digits DDMMYYYY
    (SINASC DTNASC, SIM DTOBITO). Each eight-digit reading is accepted only when it gives a valid
    date in 1990–2035, which no string satisfies under both readings (one of them puts the year
    outside the window or the month above 12). Anything else is NULL, and its event unallocated as
    'date'. Interim: date typing belongs in pegasus_data."""
    x = f'trim(CAST("{column}" AS VARCHAR))'
    return (f"CASE WHEN regexp_full_match({x}, '[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}') THEN TRY_CAST({x} AS DATE) "
            f"WHEN regexp_full_match({x}, '[0-9]{{8}}') AND TRY_CAST(TRY_STRPTIME({x}, '%Y%m%d') AS DATE) "
            f"BETWEEN DATE '1990-01-01' AND DATE '2035-12-31' THEN TRY_CAST(TRY_STRPTIME({x}, '%Y%m%d') AS DATE) "
            f"WHEN regexp_full_match({x}, '[0-9]{{8}}') AND TRY_CAST(TRY_STRPTIME({x}, '%d%m%Y') AS DATE) "
            f"BETWEEN DATE '1990-01-01' AND DATE '2035-12-31' THEN TRY_CAST(TRY_STRPTIME({x}, '%d%m%Y') AS DATE) END")


def monthly_counts(dataset: str, event: str, year: int, classifier: str | None = None,
                   places: pa.Array | None = None) -> EventCounts:
    """Events of one publication year by (u, year, month of the event's date, sex, age, code).
    The month and year come from the event's date (`_when`), so a file's events may fall in the
    year before it (onset in December, notified in January); a missing or unparsable date is
    unallocated with that reason."""
    strata = _strata(dataset)
    spec_class = classifier
    if spec_class is None:
        import pegasus_data as pg

        spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
        primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
        spec_class = primary[0] if primary else None
    when = _when(dataset)
    key = {"what": "monthly_counts", "dataset": dataset, "event": event, "year": year, "classifier": spec_class,
           "when": when, "data": config.data_version(), "dates": 3, **_df_key(dataset, year)}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], strata["age"], when] + ([strata["sex"]] if strata["sex"] else []) +         ([spec_class] if spec_class else [])
    raw = _records(dataset, event, year, cols)
    con = duckdb.connect()
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{spec_class}" AS VARCHAR)))' if spec_class else "'*'"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            {_date_sql(when)} AS d FROM r""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' WHEN d IS NULL THEN 'date' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST(year(d) AS SMALLINT) AS year,
            CAST(month(d) AS TINYINT) AS month, CAST(sex AS TINYINT) AS sex, age, code,
            CAST(count(*) AS INTEGER) AS y
        FROM e WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, year, month""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(count(*) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}) by month of {when}"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def _sex_sql(strata: dict, dataset: str, table: pa.Table) -> str:
    """The sex stratum as 1 (male) / 2 (female), mapped from pegasus_data's labels of the codes
    present, never from assumed codes: SIH writes female as 2 or 3, SIM as 2, SINAN as F. A code
    labelled neither (ignored, blank, undecoded) is unallocated."""
    if strata["sex"] is None:
        return str(strata["implied_sex"])
    codes = sorted({str(c) for c in pc.unique(table.column(strata["sex"])).to_pylist() if c is not None})
    mapping = _sex_codes(dataset, strata["sex"], tuple(codes))
    col = f'CAST("{strata["sex"]}" AS VARCHAR)'
    male = ", ".join(f"'{c}'" for c, v in mapping.items() if v == 1) or "NULL"
    female = ", ".join(f"'{c}'" for c, v in mapping.items() if v == 2) or "NULL"
    return f"CASE WHEN {col} IN ({male}) THEN 1 WHEN {col} IN ({female}) THEN 2 END"


def _sex_codes(dataset: str, column: str, codes: tuple[str, ...]) -> dict[str, int | None]:
    import pegasus_data as pg
    from pegasus_data._request import parse_dataset

    system = {"SIH": "SIHSUS"}.get(parse_dataset(dataset)[0], parse_dataset(dataset)[0])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        labelled = pg.translate(pa.table({column: list(codes)}), system=system).to_pylist()
    out: dict[str, int | None] = {}
    for row in labelled:
        label = str(row.get(f"{column}_label") or "").strip().lower()
        out[str(row[column])] = 1 if label in ("m", "masculino", "male") else 2 if label in ("f", "feminino", "female") \
            else None
    if not any(v == 1 for v in out.values()) or not any(v == 2 for v in out.values()):
        raise LookupError(f"{dataset}.{column}: pegasus_data labels no male and female codes among {codes} "
                          f"(system {system}): {labelled}")
    return out


def _cells_sql(strata: dict, dataset: str, table: pa.Table) -> str:
    return (f'{_residence_sql(strata["residence"])} AS u, '
            f'{_sex_sql(strata, dataset, table)} AS sex, '
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
    raw = _records(dataset, event, year, cols)
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
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
    raw = _records(dataset, event, year, cols)
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)},
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


def context_field(name: str, years: list[int] | None = None) -> pa.Table:
    """A context field (IBGE/SIDRA, INMET, S2iD, ANS, INEP: pegasus_data's `curation/fields.yml`)
    as (u, year, value, status, unit), u 6-digit. Built in PegaSUS's own data root
    (`pegasus-data fields --root`); a field not built raises, never an empty table."""
    import pegasus_data as pg

    key = {"what": "context_field", "name": name, "years": sorted(years) if years else None,
           "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    settings = pg.load_settings(root=config.data_root())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.load_field(name, years=years, settings=settings)
    con = duckdb.connect()
    con.register("r", raw)
    table = con.execute("""SELECT CAST(left(CAST(municipality AS VARCHAR), 6) AS INTEGER) AS u,
            CAST(year AS SMALLINT) AS year, CAST(value AS DOUBLE) AS value,
            CAST(status AS VARCHAR) AS status, CAST(unit AS VARCHAR) AS unit FROM r ORDER BY u, year""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"pegasus_data.load_field({name})"})
    return table
