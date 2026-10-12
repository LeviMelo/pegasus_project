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

import contextlib
import functools
import hashlib
import os
import warnings
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from . import config, control, store

MAX_AGE = 80  # POPSVS closes at 80+
_TREES = ("ICD10", "SIGTAP", "CBO2002", "CNAE20")  # pegasus_data's code_trees.parquet


@dataclass(frozen=True)
class EventCounts:
    """Counts of one event type per (municipality, year, sex, single age, code), non-empty cells only."""

    counts: pa.Table        # u:int32, year:int16, sex:int8, age:int16, code:string, y:int32
    unallocated: pa.Table   # year, reason, code, y
    key: dict
    missing: pa.Table | None = None   # a composition's records whose value is not recorded, by cell (u, year, sex, age, code, m)


ACCOUNT = ("population_account", "population-account-2")   # the modelled product and its pinned version
TENSOR = {"account-3": ("population-account-3", 2000, 2023), "account-4": ("population-account-4", 2000, 2030),
          "account-6": ("population-account-6", 1991, 2030)}   # source: version, years held
POPSVS_EDGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]   # 18 bands, 80+ closes
ACCOUNT_EDGES = list(range(0, 81, 5))   # 17 bands: the account's 0-4 holds ages 0 and 1-4, which POPSVS keeps apart
POPSVS_PLACES = 5570
_Z80 = 1.2815515655446004    # the 80% interval's half-width in standard deviations


#: Exposure modifiers (ARCHITECTURE §4.1, ADR-0020): ``<base>+kappa`` multiplies N by the system's completeness κ_{UF,t},
#: ``<base>+sus`` by the share of the population without private coverage; the source string carries them.
#: The measured confusions of recorded race (pegasus_data's modelled tier; its decisions 0143 and 0149), each where a
#: declared link reaches a person's own declaration: its product, the sex it reaches (None: both) and the account's age
#: bands it reaches, each mapped to the product's band, or to a tuple of its bands mixed by the deaths' age mixture
#: (`_age_mix`). Outside every reach the recorded race is the declared one (ARCHITECTURE §3.4). The women's matrix
#: (race_confusion_women: mothers' SINASC declaration against their death certificate) is not entered: inverted on
#: every woman of 15-49 it gives black women 0.71 of white women's death rate and amarela 0.045, against crude
#: recorded ratios of 1.01 and 0.80 (2022), because its declared axis is the mother's SINASC declaration, not the
#: census's the account carries (2026-10-08; OPEN_QUESTIONS)
CONFUSIONS = {
    "infant": (("race_confusion_infant", "race-confusion-infant-1"), None, {0: ("0-6 d", "7-27 d", "28-364 d")}),
}
MODIFIERS = {"kappa": ("system_completeness", "system-completeness-2"), "sus": ("population_without_private_coverage", "sus-dependent-2"),
             "confusion": ("race_confusion", "+".join(v for (_, v), _, _ in CONFUSIONS.values()))}
RACE = {"1": "branca", "2": "preta", "3": "amarela", "4": "parda", "5": "indigena"}   # RACACOR code -> the account's race
RATIO_YEARS = list(range(2015, 2024))       # the years the declared-race rate ratios are estimated over
CONFUSION_YEARS = (2021, 2022)              # the years the infant matrix was measured on (the age mixture is read there)
SYSTEM = {"SIM.DO": "SIM", "SINASC-DN": "SINASC"}    # the systems with a completeness series; the others read κ = 1
SUS_FIRST, SUS_LAST = 2021, 2023                     # the years the SUS-dependent product holds


def split_source(source: str) -> tuple[str, tuple[str, ...]]:
    """``"hybrid+kappa"`` -> (``"hybrid"``, (``"kappa"``,)): a population source and its exposure modifiers."""
    base, *mods = source.split("+")
    if bad := [m for m in mods if m not in MODIFIERS]:
        raise KeyError(f"unknown exposure modifier {bad}: {sorted(MODIFIERS)}")
    return base, tuple(sorted(mods))


def age_edges(source: str | None = None, dataset: str | None = None, event: str | None = None) -> list[int]:
    """The lower edges of the age bands a population source supports (the last band is open); with ``dataset``, only
    the edges its events' ages also have: an event counted by age band (SINAN-SDTA's grid: 0, 1, 5, 10, 20, 50) is
    read on the coarsest bands both share, never split across the population's."""
    # account-3/4 hold single ages and are summed onto POPSVS's 18 bands
    edges = list(ACCOUNT_EDGES if split_source(source or config.population_source())[0] in ("account-2", "popsvs-5y") else POPSVS_EDGES)
    bands = _strata(dataset, event).get("age_bands") if dataset else None
    return [e for e in edges if e in bands] if bands else edges


def population_key(source: str | None = None) -> dict:
    """What an artefact built on a population adds to its key. POPSVS adds nothing (its keys predate the
    switch and the data version already names the series); the account adds its source and model version;
    modifiers add the string and their models' versions."""
    source = source or config.population_source()
    base, mods = split_source(source)
    model = ACCOUNT[1] if base == "account-2" else TENSOR[base][0] if base in TENSOR else TENSOR["account-6"][0] if base == "hybrid" else None
    models = ([] if model is None else [model]) + [MODIFIERS[m][1] for m in mods]
    return {} if source == "popsvs" else {"population": source, **({"population_model": "+".join(models)} if models else {})}


def valid_places(year: int) -> pa.Array:
    """The municipalities the population holds in ``year``: a reading's valid residences. A year it holds none of
    raises: SIM-DOFET before 2000 (POPSVS starts there) read every death as unallocated by municipality, a count of
    nothing that looked like data (2026-10-11)."""
    u = population([year]).column("u").unique()
    if len(u) == 0:
        raise LookupError(f"no population for {year}: its events cannot be placed against a denominator")
    return u


def population(years: range | list[int], series: str = "POPSVS", source: str | None = None, dataset: str | None = None,
               race: str | None = None) -> pa.Table:
    """Person-years by (u, year, sex, age): u 6-digit, sex 1 male / 2 female.

    ``source`` (default ``config.population_source()``): ``popsvs`` gives single years of age 0..80 (``series``
    names the pegasus_data series). ``account-2`` gives pegasus_data's population account: age is the LOWER EDGE
    of its five-year band (``age_edges``), and the column ``s`` is the standard deviation of log N, read from
    its 80% interval. Not covered by the account (a municipality pooled with others in a comparable area,
    16 of 5570) or before 2010 (years the account holds only for comparable areas): absent or an error.
    ``account-3`` (2000-2023) and ``account-4`` (2000-2030, the forecast beyond 2023) are pegasus_data's complete
    tensor (all 5570 municipalities, single ages 0-100, race; ADR-0151): the race ``total``, single ages 0-79 and
    the 80-100 summed to 80+, then summed onto POPSVS's 18 bands exactly (ages 0 and 1-4 apart); age is the
    band's lower edge (``age_edges``), ``s`` the sd of log N.

    ``<base>+kappa`` / ``<base>+sus`` are the exposure N^{(v)} of ARCHITECTURE §4.1 for ``dataset`` (required then):
    N is multiplied by the completeness κ_{s(dataset),UF,t} (1 for a system without a series) and by the share of
    the population without private coverage (``exposure``)."""
    source = source or config.population_source()
    base, mods = split_source(source)
    if race is not None:
        # a race group (ARCHITECTURE §4.1): the account's race slice; ``+confusion`` turns it into the exposure to being
        # *recorded* as that race on a death certificate (``_recorded_exposure``). Declared-race slices carry no modifier but κ.
        if base not in TENSOR or race not in RACE:
            raise ValueError(f"race {race!r} needs a tensor source (account-3/4/6) and a code in {sorted(RACE)}")
        if "confusion" in mods:
            if dataset != "SIM.DO":
                raise ValueError("+confusion is the recorded-race exposure of SIM.DO deaths")
            rest = tuple(m for m in mods if m != "confusion")
            pop = _recorded_exposure(sorted(set(years)), base, race)
            return _modified(pop, sorted(set(years)), base, rest, dataset) if rest else pop
        pop = _tensor_population(sorted(set(years)), base, RACE[race])
        return _modified(pop, sorted(set(years)), base, mods, dataset) if mods else pop
    if "confusion" in mods:
        raise ValueError("+confusion needs a race group (population(..., race=))")
    if mods:
        if dataset is None:
            raise ValueError(f"{source!r} is the exposure of a dataset: name it (population(..., dataset=))")
        return _modified(population(years, series, base), sorted(set(years)), base, mods, dataset)
    if source in TENSOR:
        return _tensor_population(sorted(set(years)), source)
    if source == "hybrid":
        # POPSVS at every age but 0, the account's age 0 (population-account-6; evaluation 2026-10-05 exposure, hybrid)
        pop, acc = population(years, series, "popsvs"), _tensor_population(sorted(set(years)), "account-6")
        con = duckdb.connect()
        con.register("p", pop)
        con.register("a", acc)
        return con.execute("""
            SELECT CAST(u AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex, CAST(age AS SMALLINT) AS age,
                   CAST(n AS DOUBLE) AS n, CAST(0 AS DOUBLE) AS s FROM p WHERE age > 0
            UNION ALL
            SELECT CAST(u AS INTEGER), CAST(year AS SMALLINT), CAST(sex AS TINYINT), CAST(age AS SMALLINT), n, s
            FROM a WHERE age = 0 AND u IN (SELECT DISTINCT u FROM p)
            ORDER BY u, year, sex, age""").fetch_arrow_table()
    if source == "account-2":
        return _account_population(sorted(set(years)))
    if source == "popsvs-5y":
        # a control for measurements: POPSVS summed into the account's bands, to tell the source from the bands
        pop = population(years, series)
        con = duckdb.connect()
        con.register("p", pop)
        return con.execute("""SELECT u, year, sex, CAST(least(age // 5 * 5, 80) AS SMALLINT) AS age, sum(n) AS n
                              FROM p GROUP BY ALL ORDER BY u, year, sex, age""").fetch_arrow_table()
    if source.startswith("events:"):
        return _events_population(sorted(set(years)), source)
    if source != "popsvs":
        raise KeyError(f"unknown population source {source!r}: popsvs, account-3, account-4, account-6, hybrid, account-2 "
                       "or events:<dataset>:<event>[:codes][;...] (popsvs-5y: a control)")
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


def _events_population(years: list[int], source: str) -> pa.Table:
    """Another field's events as the exposure (ARCHITECTURE §5.2, a ratio field): ``events:<dataset>:<event>`` or
    ``events:<dataset>:<event>:<code>,<code>`` (the events whose classifier code starts with one of them), several
    terms joined by ``;`` summed (total births: ``events:SINASC-DN:birth;SIM-DOFET:foetal_death``), optionally
    ``@<lag>`` (the denominator's events ``lag`` years earlier: deaths over the admissions of the year before), counted by
    place and year into one cell (sex 1, age 0) for every municipality POPSVS holds (0 where the denominator has none).
    The numerator is read in that same cell (`monolith.assemble`), so the field is the numerator's rate per denominator
    event: congenital over gestational toxoplasmosis, admissions per notified case."""
    import pyarrow.compute as pc

    spec, _, lag = source.partition("@")
    lag = int(lag or 0)
    terms = []
    for term in spec.removeprefix("events:").split(";"):
        parts = term.split(":", 2)
        if len(parts) < 2 or not all(parts[:2]):
            raise ValueError(f"{source!r}: write events:<dataset>:<event>[:codes][;<dataset>:<event>[:codes]...][@lag]")
        terms.append((parts[0], parts[1], [c.replace(".", "").upper() for c in parts[2].split(",")] if len(parts) > 2 and parts[2] else []))
    key = {"what": "population", "source": source, "years": years, "data": config.data_version(),
           "declared": [_declared_key(d, e) for d, e, _ in terms]}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    places = population(years, "POPSVS", "popsvs").column("u").unique()
    rows = []
    for dataset, event, codes in terms:      # several event types summed: total births are live births and foetal deaths
        for y in years:
            c = event_counts(dataset, event, y - lag, cell=False).counts
            if codes:
                hit = pc.starts_with(c.column("code"), codes[0])
                for k in codes[1:]:
                    hit = pc.or_(hit, pc.starts_with(c.column("code"), k))
                c = c.filter(pc.fill_null(hit, False))
            rows.append(pa.table({"u": c.column("u"), "year": pa.array([y] * c.num_rows, pa.int16()), "y": c.column("y")}))
    con = duckdb.connect()
    con.register("e", pa.concat_tables(rows) if rows else pa.table({"u": [], "year": [], "y": []}))
    con.register("pl", pa.table({"u": places}))
    con.register("yy", pa.table({"year": pa.array(years, pa.int16())}))
    table = con.execute("""
        SELECT CAST(pl.u AS INTEGER) AS u, CAST(yy.year AS SMALLINT) AS year, CAST(1 AS TINYINT) AS sex,
               CAST(0 AS SMALLINT) AS age, CAST(coalesce(sum(e.y), 0) AS DOUBLE) AS n
        FROM pl CROSS JOIN yy LEFT JOIN e ON e.u = pl.u AND e.year = yy.year
        GROUP BY ALL ORDER BY u, year""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"events of {terms} as an exposure"})
    return table


def _account_population(years: list[int]) -> pa.Table:
    """The population account's municipal rows (P8: a modelled input, read through pegasus_data's modelled
    tier, with its uncertainty): (u, year, sex, age band edge, n, s)."""
    from pathlib import Path
    from types import SimpleNamespace

    from pegasus_data.modelled import read_modelled

    if min(years) < 2010 or max(years) > 2023:
        raise LookupError(f"population-account-2 holds municipalities for 2010-2023 (comparable areas before); asked {years[0]}-{years[-1]}")
    key = {"what": "population", "source": "account-2", "model": ACCOUNT[1], "years": years}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    raw, manifest = read_modelled(ACCOUNT[0], ACCOUNT[1], settings=SimpleNamespace(lake_dir=Path(config.data_root()) / "lake"))
    con = duckdb.connect()
    con.register("a", raw)
    edges = ACCOUNT_EDGES
    table = con.execute(f"""
        SELECT CAST(CAST(unnest(string_split(place, '+')) AS INTEGER) // 10 AS INTEGER) AS u, CAST(year AS SMALLINT) AS year,
               CAST(sex AS TINYINT) AS sex,
               CAST(CASE WHEN age_band = '80+' THEN 80 ELSE CAST(split_part(age_band, '-', 1) AS INTEGER) END AS SMALLINT) AS age,
               CAST(population AS DOUBLE) AS n,
               CASE WHEN population_lo > 0 AND population_hi > population_lo
                    THEN (ln(population_hi) - ln(population_lo)) / (2 * {_Z80}) ELSE 0.0 END AS s
        FROM a WHERE place_kind = 'municipality' AND place NOT LIKE '%+%' AND year IN ({', '.join(map(str, years))})
        ORDER BY u, year, sex, age""").fetch_arrow_table()
    if set(table.column("age").unique().to_pylist()) != set(edges):
        raise ValueError("the account's age bands do not match ACCOUNT_EDGES")
    store.put_table("gateway", key, table, {"source": f"pegasus_data modelled {ACCOUNT[0]}/{ACCOUNT[1]}",
                                            "model": manifest.get("model")})
    return table


def _tensor_population(years: list[int], source: str, race: str = "total") -> pa.Table:
    """population-account-3/4 on the gateway's 18 POPSVS bands: (u, year, sex, age band edge, n, s).

    The bands are the exact sums of the single ages (0 | 1-4 | 5-9 ... 75-79 | 80+). A band's ``s`` (sd of log N) is
    the sum of its ages' sds of N over the band's N, i.e. the ages' errors taken as perfectly correlated: an upper
    bound, as the single ages of a band share one band total (ADR-0151)."""
    from pathlib import Path

    version, first, last = TENSOR[source]
    if min(years) < first or max(years) > last:
        hint = "; account-4 holds the forecast to 2030" if source == "account-3" and max(years) > last else ""
        raise LookupError(f"{version} holds {first}-{last}; asked {years[0]}-{years[-1]}{hint}")
    key = {"what": "population", "source": source, "model": version, "years": years, **({} if race == "total" else {"race": race})}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    path = Path(config.data_root()) / "lake" / "modelled" / ACCOUNT[0] / version / "estimates.parquet"
    con = duckdb.connect()
    table = con.execute(f"""
        WITH a AS (
            SELECT municipality // 10 AS u, year, sex, least(age, {MAX_AGE}) AS age_s, population AS n,
                   CASE WHEN population_lo > 0 AND population_hi > population_lo
                        THEN population * (ln(population_hi) - ln(population_lo)) / (2 * {_Z80}) ELSE 0.0 END AS sd
            FROM read_parquet('{path.as_posix()}')
            WHERE race = '{race}' AND year IN ({', '.join(map(str, years))}))
        SELECT CAST(u AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex,
               CAST(CASE WHEN age_s < 1 THEN 0 WHEN age_s < 5 THEN 1 ELSE age_s // 5 * 5 END AS SMALLINT) AS age,
               CAST(sum(n) AS DOUBLE) AS n, CAST(CASE WHEN sum(n) > 0 THEN sum(sd) / sum(n) ELSE 0.0 END AS DOUBLE) AS s
        FROM a WHERE sex IN (1, 2) GROUP BY ALL ORDER BY u, year, sex, age""").fetch_arrow_table()
    if set(table.column("age").unique().to_pylist()) != set(POPSVS_EDGES):
        raise ValueError(f"{version}: the bands do not match POPSVS_EDGES")
    store.put_table("gateway", key, table, {"source": f"pegasus_data modelled {ACCOUNT[0]}/{version}, race total, bands summed"})
    return table


def _modelled(kind: str) -> pa.Table:
    """A modelled exposure product, pinned to ``MODIFIERS``'s version, through pegasus_data's modelled tier (P8)."""
    from pathlib import Path
    from types import SimpleNamespace

    from pegasus_data.modelled import read_modelled

    return read_modelled(MODIFIERS[kind][0], MODIFIERS[kind][1], settings=SimpleNamespace(lake_dir=Path(config.data_root()) / "lake"))[0]


def completeness(system: str) -> pa.Table:
    """κ_{s,UF,t}: (uf, year, kappa, s) with s the sd of log κ read from the 80 % interval (pegasus_data
    ``system_completeness``, SIM and SINASC by UF, 2000-2023: published ratio to 2011, then a calibrated extension)."""
    raw = _modelled("kappa")
    con = duckdb.connect()
    con.register("c", raw)
    return con.execute(f"""
        SELECT CAST(uf AS INTEGER) AS uf, CAST(year AS SMALLINT) AS year, CAST(least(completeness, 1.0) AS DOUBLE) AS kappa,
               CAST(CASE WHEN completeness_lo > 0 AND completeness_hi > completeness_lo
                         THEN (ln(least(completeness_hi, 1.0 + 1e-9)) - ln(completeness_lo)) / (2 * {_Z80}) ELSE 0.0 END AS DOUBLE) AS s
        FROM c WHERE system = '{system}' ORDER BY uf, year""").fetch_arrow_table()


def sus_share(years: list[int]) -> pa.Table:
    """The share q of the population without private coverage, (u, year, sex, band edge, q, s, extended), on the product's
    17 five-year bands. The product holds 2021-23 (``SUS_FIRST``..``SUS_LAST``); any other year reads the cell's 2021-23 mean
    (``extended``), with the sd of log q grown as a random walk of the annual drift measured on 2021 -> 2023 (population-
    weighted sd of the cells' log changes), so a share held fixed is typed as uncertain, not as observed (P8). ``s`` is the
    sd of the private coverage's interval over q (the population's own error is not in it: it is POPSVS's). A pooled
    comparable area ('a+b') gives each member municipality the pooled share."""
    raw = _modelled("sus")
    con = duckdb.connect()
    con.register("r", raw)
    con.execute(f"""CREATE TEMP TABLE q AS SELECT CAST(CAST(unnest(string_split(place, '+')) AS INTEGER) // 10 AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, CAST(CAST(sex AS INTEGER) AS TINYINT) AS sex,
            CAST(CASE WHEN age_band = '80+' THEN 80 ELSE CAST(split_part(age_band, '-', 1) AS INTEGER) END AS SMALLINT) AS age,
            1.0 - private_coverage AS q, population AS w,
            (private_coverage_hi - private_coverage_lo) / (2 * {_Z80}) / (1.0 - private_coverage) AS s
        FROM r WHERE CAST(sex AS INTEGER) IN (1, 2) AND private_coverage < 1""")
    # a municipality in two areas of different years (pooled once, alone later): one row per cell, their mean share
    con.execute("CREATE TEMP TABLE q1 AS SELECT u, year, sex, age, avg(q) AS q, sum(w) AS w, avg(s) AS s FROM q GROUP BY ALL")
    con.execute("DROP TABLE q")
    con.execute("ALTER TABLE q1 RENAME TO q")
    drift = con.execute(f"""SELECT sqrt(sum(a.w * power(ln(b.q / a.q), 2)) / sum(a.w)) / {SUS_LAST - SUS_FIRST}
        FROM q a JOIN q b USING (u, sex, age) WHERE a.year = {SUS_FIRST} AND b.year = {SUS_LAST} AND a.q > 0 AND b.q > 0
        AND b.year = a.year + {SUS_LAST - SUS_FIRST}""").fetchone()[0]
    ys = ", ".join(f"({y})" for y in years)
    return con.execute(f"""
        WITH m AS (SELECT u, sex, age, avg(q) AS q, avg(s) AS s FROM q GROUP BY ALL),
             y(year) AS (VALUES {ys})
        SELECT m.u, CAST(y.year AS SMALLINT) AS year, m.sex, m.age, CAST(coalesce(h.q, m.q) AS DOUBLE) AS q,
               CAST(CASE WHEN h.q IS NOT NULL THEN h.s
                    ELSE sqrt(power(m.s, 2) + power({drift}, 2) * least(abs(y.year - {SUS_FIRST}), abs(y.year - {SUS_LAST}))) END AS DOUBLE) AS s,
               h.q IS NULL AS extended
        FROM m CROSS JOIN y LEFT JOIN q h ON h.u = m.u AND h.sex = m.sex AND h.age = m.age AND h.year = y.year
        ORDER BY 1, 2, 3, 4""").fetch_arrow_table()


def _modified(pop: pa.Table, years: list[int], base: str, mods: tuple[str, ...], dataset: str) -> pa.Table:
    """``pop`` (a base source) times κ and/or q: N' = κ_{UF(u),t} · q_{u,sex,band,t} · N, s' the quadrature of the parts.
    Places or years a modifier does not cover are dropped, so their events are unallocated, never given a guess."""
    key = {"what": "exposure", "code": config.code_key(_modified), "base": base, "mods": list(mods), "dataset": dataset, "years": years,
           **{m: MODIFIERS[m][1] for m in mods}, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    con = duckdb.connect()
    con.register("p", pop)
    join, mult, var = "", "1.0", "coalesce(p.s, 0) ^ 2" if "s" in pop.column_names else "0.0"
    if "kappa" in mods:
        system = SYSTEM.get(dataset)
        if system is None:
            raise ValueError(f"{dataset} has no completeness series (SIM.DO, SINASC-DN): +kappa would be a silent 1")
        if min(years) < 2000 or max(years) > 2023:
            raise LookupError(f"system-completeness-2 holds 2000-2023; asked {years[0]}-{years[-1]}")
        con.register("k", completeness(system))
        join += " JOIN k ON k.uf = p.u // 10000 AND k.year = p.year"
        mult, var = f"{mult} * k.kappa", f"{var} + k.s ^ 2"
    if "sus" in mods:
        con.register("q", sus_share(years))
        join += " JOIN q ON q.u = p.u AND q.year = p.year AND q.sex = p.sex AND q.age = least(p.age // 5 * 5, 80)"
        mult, var = f"{mult} * q.q", f"{var} + q.s ^ 2"
    table = con.execute(f"""SELECT p.u, p.year, p.sex, p.age, CAST(p.n * {mult} AS DOUBLE) AS n, CAST(sqrt({var}) AS DOUBLE) AS s
        FROM p {join} ORDER BY p.u, p.year, p.sex, p.age""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"{base} x {', '.join(MODIFIERS[m][1] for m in mods)}"})
    return table


def _confusion(pop: str) -> pd.DataFrame:
    """One population's confusion C(recorded k | declared j) by UF and the account's age band it reaches (`CONFUSIONS`),
    with the posterior's relative sd of p (the product's intervals are 5-95 %); a band the product splits finer is their
    mixture by the deaths' age mixture (the bands' errors taken as shared: the weighted mean)."""
    from pathlib import Path
    from types import SimpleNamespace

    from pegasus_data.modelled import read_modelled

    (name, version), _, bands = CONFUSIONS[pop]
    raw = read_modelled(name, version, settings=SimpleNamespace(lake_dir=Path(config.data_root()) / "lake"))[0].to_pandas()
    code = {"Branca": "1", "Preta": "2", "Amarela": "3", "Parda": "4", "Indígena": "5"}
    raw = raw[raw.declared.isin(code) & raw.recorded.isin(code)].copy()
    raw["j"], raw["k"] = raw.declared.map(code), raw.recorded.map(code)
    raw["rel"] = (raw.p_hi - raw.p_lo) / (2 * 1.6449) / raw.p.clip(lower=1e-9)
    parts = []
    for age, band in bands.items():
        if isinstance(band, tuple):
            w = dict(zip(band, _age_mix(pop), strict=True))
            c = raw[raw.age_band.isin(band)]
            c = c.assign(w=c.age_band.map(w))
            c = c.assign(pw=c.p * c.w, rw=c.rel * c.p * c.w).groupby(["uf", "j", "k"], as_index=False)[["pw", "rw"]].sum()
            c = c.assign(p=c.pw, rel=c.rw / c.pw.clip(lower=1e-12))
        else:
            c = raw[raw.age_band == band]
        parts.append(c.assign(age=age)[["uf", "age", "j", "k", "p", "rel"]])
    return pd.concat(parts, ignore_index=True)


def _age_mix(pop: str) -> np.ndarray:
    """The deaths' mixture over a population's finer bands: the infants' perinatal deaths over the three day bands."""
    if pop == "infant":
        return _infant_age_mix()
    raise KeyError(f"no age mixture for {pop!r}")


def _infant_age_mix() -> np.ndarray:
    """The share of the perinatal deaths (SIM chapter P, ages under 1) in the matrix's three age bands (0-6 d, 7-27 d,
    28-364 d) over the years the matrix was measured on: the deaths under the primary classifier's chapter P by the
    subject's age stratum (pegasus_data's decoded fractional years, ``IDADE_anos``) in whole days (its six decimals
    put day 7 at 6.99996: 513 deaths of 2019 crossed the band edge unrounded)."""
    key = {"what": "infant_age_mix", "years": list(CONFUSION_YEARS), "data": config.data_version(), "code": config.code_key(_infant_age_mix)}
    cached = store.get_table("gateway", key)
    if cached is None:
        import pegasus_data as pg

        tot = np.zeros(3)
        coded = _strata("SIM.DO")["age"]
        cause = next(c["column"] for c in event_type("SIM.DO", "death")["classifiers"] if c["role"] == "primary")
        for y in CONFUSION_YEARS:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = pg.count_events("SIM.DO", "death", period=y, geography="BR", by=[cause, coded],
                                      root=config.data_root(), allow_partial=False, max_download=max_download())
            con = duckdb.connect()
            con.register("r", raw)
            for band, n in con.execute(f"""
                WITH x AS (SELECT round(TRY_CAST("{coded}" AS DOUBLE) * 365.25) AS d, events FROM r
                           WHERE upper("{cause}") LIKE 'P%')
                SELECT CASE WHEN d < 7 THEN 0 WHEN d < 28 THEN 1 WHEN d < 365.25 THEN 2 END AS band, sum(events)
                FROM x GROUP BY 1""").fetchall():
                if band is not None:
                    tot[band] += n
        cached = pa.table({"band": [0, 1, 2], "share": list(tot / tot.sum())})
        store.put_table("gateway", key, cached)
    return np.asarray(cached.column("share").to_pylist())


def declared_ratios(pop: str = "infant", base: str = "account-3") -> dict[str, float]:
    """Rate ratios of a population's deaths by *declared* race, Branca = 1, its confusion inverted on the national
    UF × year × age-band totals of its reach: the recorded deaths of race k in UF f, year t, band a are Poisson with
    mean rate_{f,t,a} · Σ_j C(k|j,f,a) r_j N_{j,f,t,a} (the rates profiled out, r_j by maximum likelihood over
    ``RATIO_YEARS``, a N(0, 2²) prior on the log ratios). Five numbers per population; its recorded-race exposure uses
    them (ARCHITECTURE §4.1)."""
    from scipy.optimize import minimize

    (_, version), sex, bands = CONFUSIONS[pop]
    key = {"what": "declared_ratios", "pop": pop, "base": base, "years": RATIO_YEARS, "confusion": version,
           "data": config.data_version(), "code": config.code_key(declared_ratios)}
    cached = store.get_table("gateway", key)
    if cached is None:
        c = _confusion(pop)
        ufs, ages = sorted(c.uf.unique()), sorted(bands)
        where = f"age IN ({', '.join(map(str, ages))})" + (f" AND sex = {sex}" if sex else "")
        D = np.zeros((len(ufs), len(RATIO_YEARS), len(ages), 5))
        for yi, y in enumerate(RATIO_YEARS):
            for ki, k in enumerate(RACE):
                con = duckdb.connect()
                con.register("t", event_counts("SIM.DO", "death", y, race=k).counts)
                for uf, a, n in con.execute(f"SELECT u // 10000, age, sum(y) FROM t WHERE {where} GROUP BY 1, 2").fetchall():
                    D[ufs.index(uf), yi, ages.index(a), ki] = n
        Nj = np.zeros((len(ufs), len(RATIO_YEARS), len(ages), 5))
        for ji, j in enumerate(RACE):
            con = duckdb.connect()
            con.register("n", _tensor_population(RATIO_YEARS, base, RACE[j]))
            for uf, yr, a, n in con.execute(f"SELECT u // 10000, year, age, sum(n) FROM n WHERE {where} GROUP BY 1, 2, 3").fetchall():
                Nj[ufs.index(uf), RATIO_YEARS.index(yr), ages.index(a), ji] = n
        Cm = np.zeros((len(ufs), len(ages), 5, 5))      # [uf, age, j, k]
        for r in c.itertuples():
            Cm[ufs.index(r.uf), ages.index(r.age), int(r.j) - 1, int(r.k) - 1] = r.p
        M = np.einsum("fajk,fyaj->fyakj", Cm, Nj)       # [f, y, a, k, j]

        def nll(rho: np.ndarray) -> float:
            lam = np.exp(np.concatenate([[0.0], rho]))
            base_mean = M @ lam                                            # [f, y, a, k]
            rate = D.sum(3) / np.maximum(base_mean.sum(3), 1e-9)           # profiled per UF, year and band
            mean = np.maximum(rate[..., None] * base_mean, 1e-9)
            return float((mean - D * np.log(mean)).sum() + 0.5 * (rho ** 2).sum() / 4.0)

        fit = minimize(nll, np.zeros(4), method="L-BFGS-B")
        cached = pa.table({"race": list(RACE), "ratio": [1.0, *np.exp(fit.x).tolist()]})
        store.put_table("gateway", key, cached, {"converged": bool(fit.success), "nll": float(fit.fun)})
    return dict(zip(cached.column("race").to_pylist(), cached.column("ratio").to_pylist(), strict=True))


def _recorded_exposure(years: list[int], base: str, k: str) -> pa.Table:
    """The exposure to being *recorded* as race ``k`` on a death certificate (ARCHITECTURE §3.4, §4.1): within each
    measured population's reach (`CONFUSIONS`: infants at age 0, women of 15-49), N^{rec}_k = Σ_j C(k|j, UF, band) ·
    r_j · N_j with r_j that population's declared-race ratios (`declared_ratios`) and N_j the account's race-j
    population, so that the recorded count's expectation is μ^{rec}_k = Σ_j C(k|j) μ_j when the declared races share
    one shape and differ by the ratios; elsewhere the recorded race is the declared one (N_k). ``s`` is the quadrature
    of the races' own sd and the matrix's relative sd (independent cells)."""
    key = {"what": "recorded_exposure", "base": base, "race": k, "years": years, "confusion": MODIFIERS["confusion"][1],
           "data": config.data_version(), "code": config.code_key(_recorded_exposure)}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    parts = []
    for pop, (_, sex, _) in CONFUSIONS.items():
        r, c = declared_ratios(pop, base), _confusion(pop)
        c = c[c.k == k]
        c = c.assign(r=c.j.map(r), sex=sex if sex else -1)
        parts.append(c[["uf", "age", "sex", "j", "p", "rel", "r"]])
    con = duckdb.connect()
    con.register("c", pa.Table.from_pandas(pd.concat(parts, ignore_index=True), preserve_index=False))
    union = " UNION ALL ".join(f"SELECT '{j}' AS j, * FROM n{j}" for j in RACE)
    for j in RACE:
        con.register(f"n{j}", _tensor_population(years, base, RACE[j]))
    con.register("own", _tensor_population(years, base, RACE[k]))
    reach = "c.age = {t}.age AND (c.sex = -1 OR c.sex = {t}.sex)"
    table = con.execute(f"""
        WITH n AS ({union}),
        z AS (SELECT n.u, n.year, n.sex, n.age, sum(c.p * c.r * n.n) AS m,
                     sqrt(sum(power(c.p * c.r * n.n, 2) * (power(n.s, 2) + power(c.rel, 2)))) AS sd
              FROM n JOIN c ON c.uf = n.u // 10000 AND c.j = n.j AND {reach.format(t="n")} GROUP BY ALL)
        SELECT CAST(u AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex, CAST(age AS SMALLINT) AS age,
               CAST(m AS DOUBLE) AS n, CAST(CASE WHEN m > 0 THEN sd / m ELSE 0.0 END AS DOUBLE) AS s FROM z
        UNION ALL
        SELECT u, year, sex, age, n, s FROM own WHERE NOT EXISTS (SELECT 1 FROM c WHERE {reach.format(t="own")})
        ORDER BY u, year, sex, age""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"{base} race slices x {MODIFIERS['confusion'][1]}"})
    return table


def _places_key(places: pa.Array | None, year: int) -> dict:
    """A cache key part for a place set other than POPSVS's 5570 municipalities: counts are filtered to the
    places given (the rest is unallocated), so the account's 5554 must not share an entry with POPSVS's."""
    import hashlib

    if places is None:
        if config.population_source() == "popsvs":
            return {}
        places = population([year]).column("u")
    codes = np.sort(np.asarray(places.to_numpy(zero_copy_only=False) if isinstance(places, pa.Array)
                               else places.to_numpy(), dtype=np.int64))
    return {} if len(codes) == POPSVS_PLACES else {"places": hashlib.sha256(codes.tobytes()).hexdigest()[:10]}


def event_counts(dataset: str, event: str, year: int, classifier: str | None = None,
                 places: pa.Array | None = None, race: str | None = None, cell: bool = True,
                 support: str | None = None, codes: tuple[str, ...] | list[str] = ()) -> EventCounts:
    """One event type's counts for one year, by residence × sex × age × the classifier's code.

    The columns come from pegasus_data's roles (the subject's residence, sex and age as
    strata). ``classifier`` defaults to the event type's primary classifier; an event type
    without one (births, a notifiable disease) has the single code ``*``. A subject without a
    sex stratum takes the sex its entity implies (a mother: 2), or fails. ``places`` is the
    set of valid municipalities (the population's); a residence outside it is unallocated,
    never guessed. Events two systems share are read through their declared link (`linked_counts`), never by a
    system's own column. ``race`` (a race code 1-5): only the events of that race, by the subject's declared race
    stratum (the mother's on a birth); events with no valid race are unallocated ('race unknown').
    ``cell=False``: neither sex nor age is read, every event stands in sex 1, age 0 (a ratio field's numerator and
    denominator, `_events_population`: a foetal death has no age, and an unknown sex is still an event).
    ``support``: another municipality column of the event read in place of the residence (ARCHITECTURE §5.3: the
    place of infection, the notifying municipality, the hospital's, the place of death; `fields.support_sources`);
    a record without it is unallocated by 'municipality'.
    ``codes``: the events whose classifier code starts with one of them are all the caller keeps (a code set); where a
    pegasus_data extract holds them whole for the year (`pegasus_data.extract`: a dataset larger than the lake, read
    file by file), the counts are of the extract's records, and only of those codes.
    """
    control.check_reserved(dataset, [year])      # the confirmation reserve: read by claims only
    import pegasus_data as pg

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
    column = classifier or (primary[0] if primary else None)
    if (published := published_years(dataset)) and int(year) not in published:
        # a year the catalog holds no publication of (SINAN-TOXG before 2019): said, as pegasus_data says it, before
        # the year's roles are read (they have no columns then, and a missing residence read as a schema defect)
        raise nothing_published()(f"{dataset}: no publication for {year} (published: {min(published)}-{max(published)})")
    strata = _strata(dataset, event, year)
    if support:
        if support not in {r["column"] for r in roles(dataset) if r.get("kind") == "place"}:
            raise ValueError(f"{dataset}: {support!r} is no place column of its roles")
        strata = {**strata, "residence": support, "place": support}
    if not cell:
        if race:
            raise ValueError("a race group is a stratum: cell=False reads none")
        strata = {**strata, "age": None, "sex": None, "implied_sex": 1, "implied_age": 0}
    records = None
    if codes and column:
        try:
            records, made = pg.extract_table(dataset, column, list(codes), [int(year)], root=config.data_root())
        except LookupError:
            records = None
    key = {"what": "event_counts", **({"cell": False} if not cell else {}), **({"support": support} if support else {}), **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year, "classifier": column,
           **({"extract": {"filters": made["filters"], "files": len(made["files"])}, "codes": sorted(codes)}
              if records is not None else {}),
           "data": config.data_version(), "code": config.code_key(event_counts),
           **_df_key(dataset, year), **({"race": race} if race else {})}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    by = [strata["residence"], *([strata["age"]] if strata["age"] else [])] + ([strata["sex"]] if strata["sex"] else []) + ([column] if column else [])
    if race:
        if not strata.get("race"):
            raise LookupError(f"{dataset}: no race stratum among pegasus_data's roles")
        by = by + [strata["race"]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.count_events(dataset, event, period=year, geography="BR", by=by, root=config.data_root(),
                              allow_partial=False, max_download=max_download(), records=records)
    con = duckdb.connect()
    con.register("r", raw)
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    sex = _sex_sql(strata, dataset, raw)
    code = f'upper(trim("{column}"))' if column else "'*'"
    race_col = f', TRY_CAST(CAST("{strata["race"]}" AS VARCHAR) AS INTEGER) AS race' if race else ""
    race_bad = "WHEN race IS NULL OR race NOT BETWEEN 1 AND 5 THEN 'race unknown'" if race else ""
    race_mine = f" AND (race = {int(race)} OR race IS NULL OR race NOT BETWEEN 1 AND 5)" if race else ""
    con.execute(f"""CREATE TEMP TABLE e AS SELECT
            {_residence_sql(strata['residence'])} AS u,
            {sex} AS sex,
            {_age_sql(strata)} AS age,
            {code} AS code, CAST(events AS INTEGER) AS y{race_col}
        FROM r""")
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age' {race_bad}
                     WHEN code IS NULL OR code = '' THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex,
            age, code, CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NULL{" AND race = " + str(int(race)) if race else ""}
            GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL AND y > 0{race_mine} GROUP BY ALL""").fetch_arrow_table()
    if "unquantified" in raw.column_names:
        # a weight grid's rows with neither grid nor total: groups whose people were not counted, never zero people;
        # the reason names its unit (rows, not events)
        uncounted = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, 'groups not counted (rows, not events)' AS reason,
                {code} AS code, CAST(sum(unquantified) AS INTEGER) AS y FROM r WHERE unquantified > 0 GROUP BY ALL
                HAVING count(*) > 0""").fetch_arrow_table()
        unallocated = pa.concat_tables([unallocated, uncounted.cast(unallocated.schema)])
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.count_events({dataset}, {event})", "by": by})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def extract_years(dataset: str, column: str, codes: list[str], years: list[int]) -> list[int]:
    """The ``years`` an existing pegasus_data extract of ``dataset`` holds whole for ``codes`` on ``column``
    (`pegasus_data.extract_table`, which refuses a year with a file unread or failed): data already on disk, which a
    scope prices as free (SIA-PA's serology for 2010-2018 had been deferred as 175 GB to download, 2026-10-12)."""
    import pegasus_data as pg

    out = []
    for y in years:
        try:
            pg.extract_table(dataset, column, list(codes), [int(y)], root=config.data_root())
        except (LookupError, OSError, ValueError):
            continue
        out.append(int(y))
    return out


def max_download() -> int:
    """The bytes one read may download (pegasus_data's ``max_download``): 8 GB, or ``PEGASUS_MAX_DOWNLOAD``. A study
    sets 0 once its store is prepared (`study.run`): what its scope priced is on disk, and a reader reaching past it
    fails visibly instead of fetching (SIA-PA's serology fetched a year of SIA-PA's files for its exposure, deep16)."""
    return int(os.environ.get("PEGASUS_MAX_DOWNLOAD", 8 * 1024**3))


@functools.cache
def _declared_key(dataset: str, event: str) -> dict:
    """What an artefact read from pegasus_data's events adds to its key: a hash of the event type's declaration, the
    strata read from the roles, and pegasus_data's functions that turn rows into events (`semantics/event_types.py`). The
    package version alone missed curation and code edits (a weight grid's rule changed, the counts stayed cached)."""
    import inspect
    import json

    import pegasus_data as pg
    from pegasus_data.semantics import event_types as data_events

    try:
        spec = next((e for e in pg.event_types(dataset) if e["name"] == event), None)
    except KeyError:
        spec = None
    try:
        strata = _strata(dataset, event)
    except LookupError:
        strata = None
    # the roles of the columns that make a row its events (status, weight, a grid's cells and totals): their missing
    # codes decide a count (SDTA's NU_TOT 0 is no total)
    grid = (spec or {}).get("grid") or {}
    read = {(spec or {}).get("weight"), ((spec or {}).get("status") or {}).get("column"), grid.get("total"), grid.get("margin"),
            *(c["column"] for c in grid.get("cells") or ())} - {None}
    roles_read = [r for r in pg.roles(dataset) if r["column"] in read] if read else []
    # the functions that make this event's rows events, not the whole module: an unrelated edit there re-keyed every
    # count, and a grid's reader re-keyed events that have none
    work = (data_events.events_of, data_events.count_events,
            *((data_events.event_weights,) if (spec or {}).get("weight") else ()),
            *((data_events.grid_events, data_events._integers) if grid else ()))
    body = json.dumps([spec, strata, roles_read], sort_keys=True, default=str) + "".join(inspect.getsource(f) for f in work)
    return {"declared": hashlib.sha256(body.encode()).hexdigest()[:12]}


def _per_record(dataset: str, event: str, what: str) -> None:
    """Refuse a weighted event where the computation is per record: a weighted row is many events (SIA PA's
    consolidated BPA, up to 95,404 procedures on a row), and its mark (PA_VALAPR) or its link belongs to the row."""
    import pegasus_data as pg

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    if spec.get("weight") or spec.get("grid"):
        raise ValueError(f"{dataset} {event}: a row stands for {spec['weight'] or 'a grid of'} events; {what} is per record")


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


def _records(dataset: str, event: str, year: int, columns: list[str], identity: bool = False,
             rows: dict[str, list[str]] | None = None) -> pa.Table:
    """Raw-coded records of one event type for one year (the event type's status applied); ``identity`` adds each
    record's identity ``_rid`` by pegasus_data's own rule (`linkage.identity.record_ids`, numbered before any filter):
    what its links pair."""
    control.check_reserved(dataset, [year])      # the confirmation reserve: read by claims only
    if rows and identity:
        raise ValueError("record identities are numbered before any filter: read them unfiltered")
    import pegasus_data as pg
    import pyarrow.compute as pc

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    if spec.get("grid"):
        raise ValueError(f"{dataset} {event}: a row is a grid of events by sex and age band, not a record of one")
    status = spec.get("status") or {}
    weight = [spec["weight"]] if spec.get("weight") else []
    wanted = list(dict.fromkeys(columns + ([status["column"]] if status.get("column") else []) + weight))
    # pegasus_data's duplicates rule (its decision 0159): rows compared on every column need every column; the source's
    # own flag (SINAN's NDUPLIC_N) needs that column, which a form or a year may lack
    rule = spec.get("duplicates") or {}
    dups = bool(rule)
    flag = (rule.get("flag") or {}).get("column")
    select = None if "except" in rule else wanted + ([flag] if flag else [])
    # ``rows`` ({column: code prefixes}): only those records, filtered in the lake's scan (pegasus_data `query(rows=)`)
    kwargs = {"root": config.data_root(), "max_download": max_download(), **({"provenance": "all"} if identity else {}),
              **({"rows": rows} if rows else {})}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            table = pg.query(dataset, period=year, geography="BR", select=select, present="codes", **kwargs)
        except Exception as exc:
            if not (flag and f"'{flag}' is not present" in str(exc)):
                raise
            table = pg.query(dataset, period=year, geography="BR", select=wanted, present="codes", **kwargs)
    if identity:
        from pegasus_data.linkage.identity import record_ids

        table = table.append_column("_rid", record_ids(table))
    if dups:
        import dataclasses

        from pegasus_data.semantics.event_types import event_type as data_event_type
        from pegasus_data.semantics.event_types import events_of

        # the duplicates rule alone: the status is applied below, as for every event
        only = dataclasses.replace(data_event_type(dataset, event), status_column=None, consolidation_key=())
        keep = [c for c in dict.fromkeys(wanted + (["_rid"] if identity else [])) if c in table.column_names]
        table = events_of(table, only).select(keep)
    if status.get("column") and status.get("values"):
        table = table.filter(pc.is_in(pc.cast(table[status["column"]], pa.string()),
                                      value_set=pa.array([str(v) for v in status["values"]])))
    if status.get("column") and status.get("excluded"):
        col = pc.cast(table[status["column"]], pa.string())
        table = table.filter(pc.invert(pc.fill_null(pc.is_in(col, value_set=pa.array(
            [str(v) for v in status["excluded"]])), False)))
    if weight:
        # a row of a weighted event stands for its quantity of events (SIA's production rows, pegasus_data OQ 75)
        from pegasus_data.semantics.event_types import event_type as data_event_type
        from pegasus_data.semantics.event_types import event_weights

        table = table.append_column("__w", event_weights(table, data_event_type(dataset, event)))
    return table


#: the properties of the date a record enters its system (SINAN's data entry, SIM's and SINASC's registration, SIH's
#: processing month): when an event becomes known, what a nowcast's delay runs to
ENTRY_PROPERTIES = ("entry_date", "registration_date", "processing_month")


def entry_date(dataset: str) -> str:
    """The column of the date a record enters its system, from pegasus_data's roles (`ENTRY_PROPERTIES`)."""
    by = {r["property"]: r["column"] for r in roles(dataset) if r.get("kind") == "date"}
    hit = next((by[p] for p in ENTRY_PROPERTIES if p in by), None)
    if hit is None:
        raise LookupError(f"{dataset}: no entry date among its roles ({ENTRY_PROPERTIES})")
    return hit


def _when(dataset: str) -> str:
    """The event's date column from the roles: onset where declared (the epidemic curve's time),
    else the event's own date, start, competence (the month of care SIA's production rows give), or birth date."""
    import pegasus_data as pg

    rows = {r["property"]: r["column"] for r in pg.roles(dataset) if r.get("model") == "when" and r.get("kind") == "date"}
    for prop in ("onset", "date", "start", "competence", "birth_date"):
        if prop in rows:
            return rows[prop]
    raise LookupError(f"{dataset}: no event date among its roles")


def _date_sql(column: str) -> str:
    """An event date from raw text in the forms the systems write: ISO 'YYYY-MM-DD' (dates
    pegasus_data types), eight digits YYYYMMDD (SINAN families left raw) and eight digits DDMMYYYY
    (SINASC DTNASC, SIM DTOBITO). Each eight-digit reading is accepted only when it gives a valid
    date in 1990–2035, which no string satisfies under both readings (one of them puts the year
    outside the window or the month above 12). Six digits YYYYMM (SIA's competence) are the month's
    first day: a month, which is all a monthly count reads. Anything else is NULL, and its event
    unallocated as 'date'. Interim: date typing belongs in pegasus_data."""
    x = f'trim(CAST("{column}" AS VARCHAR))'
    return (f"CASE WHEN regexp_full_match({x}, '[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}') THEN TRY_CAST({x} AS DATE) "
            f"WHEN regexp_full_match({x}, '[0-9]{{8}}') AND TRY_CAST(TRY_STRPTIME({x}, '%Y%m%d') AS DATE) "
            f"BETWEEN DATE '1990-01-01' AND DATE '2035-12-31' THEN TRY_CAST(TRY_STRPTIME({x}, '%Y%m%d') AS DATE) "
            f"WHEN regexp_full_match({x}, '[0-9]{{8}}') AND TRY_CAST(TRY_STRPTIME({x}, '%d%m%Y') AS DATE) "
            f"BETWEEN DATE '1990-01-01' AND DATE '2035-12-31' THEN TRY_CAST(TRY_STRPTIME({x}, '%d%m%Y') AS DATE) "
            f"WHEN regexp_full_match({x}, '[0-9]{{6}}') AND TRY_CAST(TRY_STRPTIME({x} || '01', '%Y%m%d') AS DATE) "
            f"BETWEEN DATE '1990-01-01' AND DATE '2035-12-31' THEN TRY_CAST(TRY_STRPTIME({x} || '01', '%Y%m%d') AS DATE) END")


def monthly_counts(dataset: str, event: str, year: int, classifier: str | None = None,
                   places: pa.Array | None = None, code_list: bool = False) -> EventCounts:
    """Events of one publication year by (u, year, month of the event's date, sex, age, code).
    The month and year come from the event's date (`_when`), so a file's events may fall in the
    year before it (onset in December, notified in January); a missing or unparsable date is
    unallocated with that reason. ``code_list``: the classifier column holds several codes
    concatenated (SINASC's CODANOMAL, "Q02Q690"); an event counts once under each distinct
    category it carries (as `code_list_counts`), and events carrying none are not counted."""
    control.check_reserved(dataset, [year])      # the confirmation reserve: read by claims only
    strata = _strata(dataset, event)
    spec_class = classifier
    if spec_class is None:
        import pegasus_data as pg

        spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
        primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
        spec_class = primary[0] if primary else None
    when = _when(dataset)
    key = {"what": "monthly_counts", "code": config.code_key(monthly_counts), **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year, "classifier": spec_class,
           "when": when, "data": config.data_version(), "dates": 3, **_df_key(dataset, year),
           **({"code_list": True} if code_list else {})}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else []), when] + ([strata["sex"]] if strata["sex"] else []) +         ([spec_class] if spec_class else [])
    raw = _records(dataset, event, year, cols)
    con = duckdb.connect()
    con.register("r", raw)
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{spec_class}" AS VARCHAR)))' if spec_class else "'*'"
    where = ""
    if code_list:
        code = (f"""unnest(list_distinct(list_transform(regexp_extract_all(upper(CAST("{spec_class}" AS VARCHAR)),
                '[A-Z][0-9]{{2}}[0-9X]?'), x -> left(x, 3))))""")
        where = f""" WHERE "{spec_class}" IS NOT NULL AND trim(CAST("{spec_class}" AS VARCHAR)) <> ''"""
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            {_date_sql(when)} AS d FROM r{where}""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' WHEN d IS NULL THEN 'date' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST(year(d) AS SMALLINT) AS year,
            CAST(month(d) AS TINYINT) AS month, CAST(sex AS TINYINT) AS sex, age, code,
            CAST(sum(wt) AS INTEGER) AS y
        FROM e WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, year, month""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(wt) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}) by month of {when}"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def _sex_sql(strata: dict, dataset: str, table: pa.Table) -> str:
    """The sex stratum as 1 (male) / 2 (female), mapped from pegasus_data's labels of the codes
    present, never from assumed codes: SIH writes female as 2 or 3, SIM as 2, SINAN as F. A code
    labelled neither (ignored, blank, undecoded) is unallocated."""
    if strata["sex"] is None:
        return str(strata["implied_sex"])
    if strata.get("sex_canonical"):     # a weight grid's sex: 1 male, 2 female, null unknown (pegasus_data GRID_SEX)
        return f'CASE WHEN "{strata["sex"]}" IN (1, 2) THEN CAST("{strata["sex"]}" AS INTEGER) END'
    codes = sorted({str(c) for c in pc.unique(table.column(strata["sex"])).to_pylist() if c is not None})
    mapping = _sex_codes(dataset, strata["sex"], tuple(codes))
    col = f'CAST("{strata["sex"]}" AS VARCHAR)'
    male = ", ".join(f"'{c}'" for c, v in mapping.items() if v == 1) or "NULL"
    female = ", ".join(f"'{c}'" for c, v in mapping.items() if v == 2) or "NULL"
    return f"CASE WHEN {col} IN ({male}) THEN 1 WHEN {col} IN ({female}) THEN 2 END"


def _sex_codes(dataset: str, column: str, codes: tuple[str, ...]) -> dict[str, int | None]:
    import pegasus_data as pg
    from pegasus_data._request import parse_dataset

    system = parse_dataset(dataset)[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        labelled = pg.translate(pa.table({column: list(codes)}), system=system).to_pylist()
    out: dict[str, int | None] = {}
    for row in labelled:
        label = str(row.get(f"{column}_label") or "").strip().lower()
        out[str(row[column])] = 1 if label in ("m", "masculino", "male") else 2 if label in ("f", "feminino", "female") \
            else None
    # a system of one sex is legitimate when its labels say so (HIV in pregnancy, SINAN HIVG, records only women);
    # what fails is a column no code of which is labelled either sex
    if not any(v in (1, 2) for v in out.values()):
        raise LookupError(f"{dataset}.{column}: pegasus_data labels no male or female code among {codes} "
                          f"(system {system}): {labelled}")
    return out


def _age_sql(strata: dict) -> str:
    """The subject's age in whole years, capped at MAX_AGE; a code the age stratum's roles declare missing (SIA PA's 999
    'idade não exigida', 998 'informada com erro') is no age, never the oldest band."""
    if strata["age"] is None:           # a group (an outbreak): no age, its events in band 0 (`_strata`)
        return f"CAST({int(strata.get('implied_age', 0))} AS SMALLINT)"
    x = f'trim(CAST("{strata["age"]}" AS VARCHAR))'
    # DuckDB's least() skips NULLs (least(NULL, 80) is 80): an absent age must stay absent, not become 80+
    years = f"floor(TRY_CAST({x} AS DOUBLE))"
    age = f"CAST(CASE WHEN {years} IS NULL THEN NULL ELSE least({years}, {MAX_AGE}) END AS SMALLINT)"
    missing = strata.get("age_missing") or ()
    if not missing:
        return age
    codes = ", ".join("'" + str(c).replace("'", "''") + "'" for c in missing)
    return f"CASE WHEN {x} IN ({codes}) THEN NULL ELSE {age} END"


def _cells_sql(strata: dict, dataset: str, table: pa.Table) -> str:
    """A record's cell (u, sex, age) and ``wt``, the events it stands for: its event type's weight (`_records`), else 1."""
    wt = '"__w"' if "__w" in table.column_names else "1"
    return (f'{_residence_sql(strata["residence"])} AS u, '
            f'{_sex_sql(strata, dataset, table)} AS sex, '
            f'{_age_sql(strata)} AS age, {wt} AS wt')


MARK_SHRINK = 10.0   # events: a (diagnosis, procedure group) stratum's case-mix offset is its mean log departure times n/(n + this)
CASEMIX_CHARS = 2    # the procedure's group: the first two digits of a SIGTAP code


def _mark_frame(con, dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float], classifier: str | None,
                places: pa.Array | None, casemix: str | None, facility_effects: str | None, facility: bool = False,
                missing: tuple[str, ...] = (), anchor: str | None = None, sign: int = 1) -> pa.Table:
    """Registers in ``con`` the table ``adj`` of a year's admissions with a valid mark: (u, sex, age, code, fac, m, lm), ``lm`` the
    log mark less the facility's effect (``facility_effects``: a stored table, `store_facility_effects`) and less the case-mix
    offset of its (diagnosis category, procedure group) stratum when ``casemix`` names the procedure column: the stratum's
    mean log mark above its category's, shrunk by n/(n + MARK_SHRINK). With ``anchor`` (the event's date column) the
    mark is an interval: the days from the anchor to the ``mark`` date times ``sign``, plus one (the calendar days
    spanned, so a same-day date is 1 and the log is defined). Returns the unallocated (year, reason, code, y)."""

    strata = _strata(dataset, event)
    _per_record(dataset, event, "a mark's moments")
    fcol = facility_column(dataset)[0] if (facility_effects or facility) else None
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else []), mark] + ([anchor] if anchor else []) + \
        ([strata["sex"]] if strata["sex"] else []) + \
        ([classifier] if classifier else []) + ([casemix] if casemix else []) + ([fcol] if fcol else [])
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)))
    con.register("r", raw)
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    pg = f"coalesce(left(trim(CAST(\"{casemix}\" AS VARCHAR)), {CASEMIX_CHARS}), '')" if casemix else "''"
    fac = f"coalesce(trim(CAST(\"{fcol}\" AS VARCHAR)), '')" if fcol else "''"
    value = (f"CAST({int(sign)} * date_diff('day', {_date_sql(anchor)}, {_date_sql(mark)}) + 1 AS DOUBLE)" if anchor
             else f'TRY_CAST(CAST("{mark}" AS VARCHAR) AS DOUBLE)')
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            trim(CAST("{mark}" AS VARCHAR)) AS mraw, {value} AS m, {pg} AS pg,
            {fac} AS fac FROM r""")
    miss = ", ".join("'" + str(v).replace("'", "''") + "'" for v in missing) or "NULL"
    con.unregister("r")
    del raw
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                      WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                      WHEN code IS NULL OR code = '' THEN 'code' WHEN mraw IN ({miss}) THEN 'mark not recorded'
                      WHEN m IS NULL THEN 'mark missing' WHEN m < {bounds[0]} OR m > {bounds[1]} THEN 'mark out of bounds'
                      END"""
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(wt) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    if facility_effects:
        fx = store.get_table("gateway", {"what": "mark_facility_effects", "id": facility_effects})
        if fx is None:
            raise LookupError(f"no stored facility effects {facility_effects}")
        con.register("fx", fx)
        con.execute(f"""CREATE TEMP TABLE a AS SELECT u, sex, age, code, pg, fac, m,
                            CASE WHEN m > 0 THEN ln(m) END - coalesce(fx.delta, 0) AS lm
                        FROM e LEFT JOIN fx ON fx.facility = e.fac WHERE ({reason}) IS NULL""")
    else:
        # a count mark admits 0 (its log is undefined: lm NULL, the count family reads Σm and Σm² only)
        con.execute(f"CREATE TEMP TABLE a AS SELECT u, sex, age, code, pg, fac, m, CASE WHEN m > 0 THEN ln(m) END AS lm "
                    f"FROM e WHERE ({reason}) IS NULL")
    con.execute("DROP TABLE e")
    if casemix:
        con.execute(f"""CREATE TEMP TABLE cm AS SELECT left(a.code, 3) AS c3, a.pg,
                sum(a.lm - b.base) / (count(*) + {MARK_SHRINK}) AS off
            FROM a JOIN (SELECT left(code, 3) AS c3, avg(lm) AS base FROM a GROUP BY 1) b ON b.c3 = left(a.code, 3)
            WHERE a.pg <> '' GROUP BY 1, 2""")
        con.execute("""CREATE TEMP TABLE adj AS SELECT a.u, a.sex, a.age, a.code, a.fac, a.m, a.lm - coalesce(cm.off, 0) AS lm
                       FROM a LEFT JOIN cm ON cm.c3 = left(a.code, 3) AND cm.pg = a.pg""")
        con.execute("DROP TABLE a")
    else:
        con.execute("ALTER TABLE a RENAME TO adj")
    return unallocated


def mark_quantiles(dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float], classifier: str | None = None,
                   missing: tuple[str, ...] | list = (), anchor: str | None = None, sign: int = 1,
                   codes: tuple[str, ...] | list = ()) -> pa.Table:
    """A mark's own distribution by state and nationally (state 0) for one year: n, the median and the 90th percentile
    of the raw mark (an interval's: days + 1, `_mark_frame`) over the events whose code starts with one of ``codes``
    (all events without). What a study's descriptive table reports: the cells' log moments are the model's location,
    and a delay is no log-normal (SINAN-TOXG 2019 onset to closure: median 103 days, the moments' exp(mean log) 61)."""
    key = {"what": "mark_quantiles", "code": config.code_key(mark_quantiles), "dataset": dataset, "event": event,
           **_declared_key(dataset, event), "year": year, "mark": mark, "bounds": list(bounds), "missing": list(missing),
           "classifier": classifier, "anchor": anchor, "sign": sign, "codes": sorted(codes), "data": config.data_version(),
           **_df_key(dataset, year)}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    con = duckdb.connect()
    _mark_frame(con, dataset, event, year, mark, tuple(bounds), classifier, None, None, None, missing=tuple(missing),
                anchor=anchor, sign=sign)
    where = " OR ".join(f"starts_with(code, '{c}')" for c in codes) or "TRUE"
    table = con.execute(f"""SELECT CAST(coalesce(u // 10000, 0) AS INTEGER) AS state, CAST(count(*) AS INTEGER) AS n,
            quantile_cont(m, 0.5) AS q50, quantile_cont(m, 0.9) AS q90
        FROM adj WHERE {where} GROUP BY ROLLUP (u // 10000) ORDER BY state""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"quantiles of {dataset} {mark}"})
    return table


def mark_moments(dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float],
                 classifier: str | None = None, places: pa.Array | None = None, casemix: str | None = None,
                 facility_effects: str | None = None, missing: tuple[str, ...] | list = (), anchor: str | None = None,
                 sign: int = 1) -> EventCounts:
    """Accumulator states of a positive numeric mark per (u, year, sex, age, code): n, Σm, Σm², Σlog m, Σ(log m)²
    (ARCHITECTURE §4.4; handoff §4 asks pegasus_data to serve these). The log moments are of the *adjusted* log mark
    when ``casemix`` (the procedure column) or ``facility_effects`` are given (`_mark_frame`); Σm and Σm² are raw.
    Values outside ``bounds`` (sentinels, impossible values) and missing values are counted
    as unallocated with their reason, never dropped silently."""
    key = {"what": "mark_moments", "code": config.code_key(mark_moments), **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year, "mark": mark,
           "bounds": list(bounds), "missing": list(missing), "classifier": classifier, "data": config.data_version(), **_df_key(dataset, year),
           **({"casemix": casemix, "shrink": MARK_SHRINK, "chars": CASEMIX_CHARS} if casemix else {}),
           **({"facility_effects": facility_effects} if facility_effects else {}),
           **({"anchor": anchor, "sign": sign} if anchor else {})}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    con = duckdb.connect()
    unallocated = _mark_frame(con, dataset, event, year, mark, bounds, classifier, places, casemix, facility_effects,
                              missing=tuple(missing), anchor=anchor, sign=sign)
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(count(*) AS INTEGER) AS n, sum(m) AS s1,
            sum(m * m) AS s2, sum(lm) AS l1, sum(lm * lm) AS l2
        FROM adj GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): moments of {mark}"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


#: composition columns counted from one read of a year's records: one column a read went over SIH's 11 million admissions
#: of a year once per column (12 s each; over an hour for 2010-2023 at the first code set, 2026-10-11), all at once held
#: every column (26 s, and the machine's free memory to zero beside the other jobs); a few at a time bounds both
COMPOSITION_BATCH = 4


def _composition_key(dataset: str, event: str, year: int, column: str, missing, classifier: str | None,
                     places: pa.Array | None, codes=None) -> dict:
    return {"what": "composition_counts", "code": config.code_key(composition_counts, _composition_tables),
            **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event),
            "year": year, "column": column, "missing": sorted(missing), "classifier": classifier,
            **({"codes": sorted(codes)} if codes else {}), "data": config.data_version(), **_df_key(dataset, year)}


def _composition_cached(key: dict) -> EventCounts | None:
    parts = [store.get_table("gateway", key), store.get_table("gateway", {**key, "part": "unallocated"}),
             store.get_table("gateway", {**key, "part": "missing"})]
    return None if any(x is None for x in parts) else EventCounts(parts[0], parts[1], key, parts[2])


def composition_counts(dataset: str, event: str, year: int, column: str, missing: tuple[str, ...] | list = (),
                       classifier: str | None = None, places: pa.Array | None = None,
                       codes: list[str] | tuple[str, ...] | None = None) -> EventCounts:
    """A category column's composition per (u, year, sex, age, code, value): the events carrying each value. A value
    among the column's declared ``missing`` codes (pegasus_data roles) is unallocated as 'value not recorded', a blank
    one as 'value missing'; their count by cell is kept too (``missing``: what a share's 'not recorded' level reads in
    stage E, S4.3). One read serves every share of the column (`share_moments`), and up to `COMPOSITION_BATCH` of the
    event type's group columns not yet counted for the year are counted from the same read, each stored on its own.
    ``codes`` (prefixes of the ``classifier``) reads only a code set's records, filtered in the lake: B58's few hundred
    admissions a year, not a table of 6.9 million cells per column and year filtered afterwards (2026-10-11)."""
    codes = tuple(codes) if codes and classifier else None
    key = _composition_key(dataset, event, year, column, missing, classifier, places, codes)
    hit = _composition_cached(key)
    if hit is not None:
        return hit
    from .tools import group_columns

    batch = {column: tuple(missing)}
    try:
        siblings = group_columns(dataset, event)
    except Exception:  # noqa: BLE001 - without the list of siblings the column is counted alone
        siblings = {}
    for col, miss in siblings.items():
        if len(batch) >= COMPOSITION_BATCH:
            break
        if col not in batch and _composition_cached(_composition_key(dataset, event, year, col, miss, classifier, places,
                                                                     codes)) is None:
            batch[col] = tuple(miss)
    strata = _strata(dataset, event)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else []), *batch] +         ([strata["sex"]] if strata["sex"] else []) + ([classifier] if classifier else [])
    con = duckdb.connect()
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)), rows={classifier: list(codes)} if codes else None)
    con.register("r", raw)
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    xs = ", ".join(f'trim(CAST("{c}" AS VARCHAR)) AS "x_{i}"' for i, c in enumerate(batch))
    con.execute(f"""CREATE TEMP TABLE e0 AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code, {xs} FROM r""")
    del raw
    out = None
    for i, (col, miss) in enumerate(batch.items()):
        k = _composition_key(dataset, event, year, col, miss, classifier, places, codes)
        ec = _composition_tables(con, f"x_{i}", year, miss, k, dataset, col)
        if col == column:
            out = ec
    return out


def _composition_tables(con, x: str, year: int, missing, key: dict, dataset: str, column: str) -> EventCounts:
    """One column's counts, unallocated and missing cells from the read table ``e0`` (`composition_counts`), stored."""
    miss = ", ".join("'" + str(v).replace("'", "''") + "'" for v in missing) or "NULL"
    con.execute(f'CREATE OR REPLACE TEMP VIEW e AS SELECT *, "{x}" AS x FROM e0')
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' WHEN x IS NULL OR x = '' THEN 'value missing'
                     WHEN x IN ({miss}) THEN 'value not recorded' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, x AS value, CAST(sum(wt) AS INTEGER) AS n
        FROM e WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(wt) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    missing_cells = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(sum(wt) AS INTEGER) AS m
        FROM e WHERE ({reason}) IN ('value missing', 'value not recorded') GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): composition of {column}"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    store.put_table("gateway", {**key, "part": "missing"}, missing_cells)
    return EventCounts(counts, unallocated, key, missing_cells)


def composition_facility(dataset: str, event: str, year: int, indicator: str, success: tuple[str, ...],
                         missing: tuple[str, ...] | list = (), classifier: str | None = None) -> pa.Table:
    """A share's records of ``year`` by recording facility, residence and category: (facility, u, code, n, k), n the
    records with ``indicator`` recorded and k those with a value among ``success``; a record naming no facility is
    ''. One read of the year serves every lead's facility reading in stage E (S4.3)."""
    strata = _strata(dataset, event)
    fac = facility_column(dataset)[0]
    key = {"what": "composition_facility", "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year, "indicator": indicator,
           "success": sorted(success), "missing": sorted(missing), "classifier": classifier, "data": config.data_version(),
           "code": config.code_key(composition_facility), **_df_key(dataset, year)}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    cols = [strata["residence"], indicator, fac] + ([classifier] if classifier else [])
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)))
    con = duckdb.connect()
    con.register("r", raw)
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    miss = ", ".join("'" + str(v).replace("'", "''") + "'" for v in missing) or "NULL"
    yes = ", ".join("'" + str(s).replace("'", "''") + "'" for s in success)
    wt = '"__w"' if "__w" in raw.column_names else "1"
    out = con.execute(f"""SELECT coalesce(trim(CAST("{fac}" AS VARCHAR)), '') AS facility,
            {_residence_sql(strata["residence"])} AS u, {code} AS code,
            CAST(sum({wt}) AS INTEGER) AS n, CAST(sum(CASE WHEN x IN ({yes}) THEN {wt} ELSE 0 END) AS INTEGER) AS k
        FROM (SELECT *, trim(CAST("{indicator}" AS VARCHAR)) AS x FROM r)
        WHERE x IS NOT NULL AND x <> '' AND x NOT IN ({miss}) GROUP BY ALL HAVING u IS NOT NULL""").fetch_arrow_table()
    store.put_table("gateway", key, out, {"source": f"pegasus_data.query({dataset}): {indicator} by {fac}"})
    return out


def share_moments(dataset: str, event: str, year: int, indicator: str, success: tuple[str, ...] = (), classifier: str | None = None,
                  places: pa.Array | None = None, missing: tuple[str, ...] | list = (), quality: bool = False,
                  codes: list[str] | tuple[str, ...] | None = None) -> EventCounts:
    """A share's states per (u, year, sex, age, code): n events with ``indicator`` recorded and k of them with a value
    among ``success`` (SIH ``MORTE`` = 1: died in hospital), from the column's composition (`composition_counts`).
    ``quality``: the column's quality field (ARCHITECTURE §5.3) instead: n every event, k those whose value is blank or
    among the column's declared ``missing`` codes ('ignorado'); a code not declared missing is a value, never guessed."""
    comp = composition_counts(dataset, event, year, indicator, missing, classifier, places, codes=codes)
    con = duckdb.connect()
    if quality:
        con.register("c", comp.counts)
        con.register("m", comp.missing)
        counts = con.execute("""
            WITH a AS (SELECT u, year, sex, age, code, sum(n) AS n, 0 AS k FROM c GROUP BY ALL
                       UNION ALL SELECT u, year, sex, age, code, sum(m) AS n, sum(m) AS k FROM m GROUP BY ALL)
            SELECT u, year, sex, age, code, CAST(sum(n) AS INTEGER) AS n, CAST(sum(k) AS INTEGER) AS k
            FROM a GROUP BY u, year, sex, age, code ORDER BY code, u, sex, age""").fetch_arrow_table()
        kept = comp.unallocated.filter(pc.invert(pc.is_in(comp.unallocated.column("reason"),
                                                          pa.array(["value missing", "value not recorded"]))))
        return EventCounts(counts, kept, {**comp.key, "what": "quality_moments"})
    con.register("c", comp.counts)
    yes = ", ".join("'" + str(s).replace("'", "''") + "'" for s in success)
    counts = con.execute(f"""SELECT u, year, sex, age, code, CAST(sum(n) AS INTEGER) AS n,
            CAST(sum(CASE WHEN value IN ({yes}) THEN n ELSE 0 END) AS INTEGER) AS k
        FROM c GROUP BY u, year, sex, age, code ORDER BY code, u, sex, age""").fetch_arrow_table()
    return EventCounts(counts, comp.unallocated, {**comp.key, "what": "share_moments", "success": list(success)})


#: IBGE's place codes nest by prefix: the digits of a residence municipality's code (6) each code system's codes are,
#: so a place in a coarser system is compared with the residence at that level (a state of birth with the state)
PLACE_PREFIX = {"BR_MUNICIPALFA": 6, "UF_BR": 2}


def away_counts(dataset: str, event: str, year: int, place: str, classifier: str | None = None,
                places: pa.Array | None = None, width: int = 6) -> EventCounts:
    """Place fields as a share per (u, year, sex, age, code), u the residence: n events with ``place`` recorded (a
    municipality where the event happened: the hospital, the place of death or birth, the place of infection; or a
    place of the person) and k of them away from the residence, compared at the place's level (``width``: the digits
    of the residence's code it holds, `PLACE_PREFIX`). A place not recorded is unallocated ('place not recorded')."""
    strata = _strata(dataset, event)
    key = {"what": "away_counts", "code": config.code_key(away_counts), **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year,
           "place": place, "classifier": classifier, "data": config.data_version(), **_df_key(dataset, year),
           **({"width": width} if width != 6 else {})}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else []), place] + ([strata["sex"]] if strata["sex"] else []) + \
        ([classifier] if classifier else [])
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)))
    con = duckdb.connect()
    con.register("r", raw)
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    div = 10 ** (6 - width)
    w_sql = _residence_sql(place) if width == 6 else f'TRY_CAST(left(CAST("{place}" AS VARCHAR), {width}) AS INTEGER)'
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            {w_sql} AS w FROM r""")
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code'
                     WHEN w IS NULL OR w NOT IN (SELECT DISTINCT u // {div} FROM v) THEN 'place not recorded' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(sum(wt) AS INTEGER) AS n,
            CAST(sum(CASE WHEN w <> u // {div} THEN wt ELSE 0 END) AS INTEGER) AS k
        FROM e WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(wt) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): {place} against residence"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def store_facility_effects(table: pa.Table) -> str:
    """Stores a (facility, delta) table of log-mark effects and returns the id `mark_moments` reads it by (a digest of its content)."""
    import hashlib

    t = table.select(["facility", "delta"]).sort_by("facility")
    h = hashlib.sha256(np.ascontiguousarray(t.column("delta").to_numpy()).tobytes() + "|".join(t.column("facility").to_pylist()).encode())
    ident = h.hexdigest()[:16]
    store.put_table("gateway", {"what": "mark_facility_effects", "id": ident}, t, {"facilities": t.num_rows})
    return ident


def mark_facility_moments(dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float], nu: pa.Table,
                          edges: list[int], classifier: str | None = None, casemix: str | None = None,
                          facility_effects: str | None = None, places: pa.Array | None = None,
                          missing: tuple[str, ...] | list = (), anchor: str | None = None, sign: int = 1,
                          cells: bool = False) -> pa.Table:
    """A year's residuals of the admissions' adjusted log mark from a fitted location, summed by recording facility:
    (facility, year, n, sr, sr2) with r = lm − ν, ν looked up by (category, residence, sex, age band) in ``nu``
    (columns code3, u, sex, band, nu), the fitted model's cells. Admissions in a cell the fit has none of are left out.
    ``cells`` keeps the residence and the category too (facility, u, code3, ...): one read of the year serves every
    lead's places and codes (a read per lead and year took hours for 646 leads, S4.3)."""
    import hashlib

    digest = hashlib.sha256(np.ascontiguousarray(nu.column("nu").to_numpy()).tobytes()
                            + np.ascontiguousarray(nu.column("u").to_numpy()).tobytes()).hexdigest()[:16]
    key = {"what": "mark_facility_moments", **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year,
           "mark": mark, "bounds": list(bounds), "classifier": classifier, "casemix": casemix, "shrink": MARK_SHRINK,
           "facility_effects": facility_effects, "nu": digest, "edges": list(edges), "data": config.data_version(), "code": config.code_key(mark_facility_moments),
           **_df_key(dataset, year), **({"anchor": anchor, "sign": sign} if anchor else {}), **({"cells": 1} if cells else {})}
    hit = store.get_table("gateway", key)
    if hit is not None:
        return hit
    con = duckdb.connect()
    _mark_frame(con, dataset, event, year, mark, bounds, classifier, places, casemix, facility_effects, facility=True,
                missing=tuple(missing), anchor=anchor, sign=sign)
    con.register("nu", nu)
    con.register("ab", pa.table({"age": pa.array(range(MAX_AGE + 1), pa.int16()),
                                 "band": pa.array([int(np.searchsorted(edges, a, side="right") - 1) for a in range(MAX_AGE + 1)],
                                                  pa.int16())}))
    by = "fac, u, code3" if cells else "fac"
    keep = ", u, code3" if cells else ""
    out = con.execute(f"""SELECT fac AS facility{keep}, CAST({year} AS SMALLINT) AS year, CAST(count(*) AS INTEGER) AS n,
            sum(r) AS sr, sum(r * r) AS sr2
        FROM (SELECT adj.fac, adj.u, nu.code3, adj.lm - nu.nu AS r FROM adj JOIN ab ON ab.age = adj.age
              JOIN nu ON nu.code3 = left(adj.code, 3) AND nu.u = adj.u AND nu.sex = adj.sex AND nu.band = ab.band)
        GROUP BY {by}""").fetch_arrow_table()
    store.put_table("gateway", key, out, {"source": f"residuals of {mark} by facility"})
    return out


def cooccurrence(dataset: str, event: str, year: int, columns: list[str], seeds: list[str]) -> pa.Table:
    """Code co-occurrence on the same record (BACKLOG 4.2): per stratum (sex × age band) and ICD category, the records
    carrying the category (``n_code``) and those of them also carrying a seed code (``n_both``), with the stratum's
    records (``n``) and its records carrying a seed (``n_seed``). A record's codes are every code its ``columns`` hold
    (a certificate's lines, an admission's diagnoses, a birth's anomaly list), the seeds matched on the full code (P37.1
    is not P37) and the related codes read at their category; the seed's own categories are left out."""
    seeds = sorted({s_.replace(".", "").upper() for s_ in seeds})
    key = {"what": "cooccurrence", "code": config.code_key(cooccurrence), "dataset": dataset, "event": event,
           **_declared_key(dataset, event), "year": year, "columns": list(columns), "seeds": seeds,
           "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    strata = _strata(dataset, event, year)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else []), *columns] + ([strata["sex"]] if strata["sex"] else [])
    con = duckdb.connect()
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)))
    con.register("r", raw)
    text = "concat_ws(' ', " + ", ".join(f"coalesce(CAST(\"{c}\" AS VARCHAR), '')" for c in columns) + ")"
    seed_hit = " OR ".join(f"list_contains(list_transform(codes, x -> starts_with(x, '{s_}')), true)" for s_ in seeds) or "false"
    seed_cat = ", ".join(f"'{s_[:3]}'" for s_ in seeds) or "''"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)},
            list_distinct(regexp_extract_all(upper({text}), '[A-Z][0-9]{{2}}[0-9X]?')) AS codes FROM r""")
    con.execute(f"""CREATE TEMP TABLE f AS SELECT sex, CAST(least(age // 10, 8) AS SMALLINT) AS band, codes,
            ({seed_hit}) AS seed FROM e WHERE sex IS NOT NULL AND age IS NOT NULL AND age >= 0""")
    table = con.execute(f"""
        WITH s AS (SELECT sex, band, count(*) AS n, sum(CASE WHEN seed THEN 1 ELSE 0 END) AS n_seed FROM f GROUP BY ALL),
             c AS (SELECT sex, band, cat, count(*) AS n_code, sum(CASE WHEN seed THEN 1 ELSE 0 END) AS n_both
                   FROM (SELECT sex, band, seed, unnest(list_distinct(list_transform(codes, x -> left(x, 3)))) AS cat FROM f)
                   WHERE cat NOT IN ({seed_cat}) GROUP BY ALL)
        SELECT c.sex, c.band, c.cat AS code, c.n_code, c.n_both, s.n, s.n_seed FROM c JOIN s USING (sex, band)""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"co-occurrence of {seeds} in {dataset} {columns} {year}"})
    return table


def code_list_counts(dataset: str, event: str, year: int, column: str | list[str],
                     places: pa.Array | None = None, classifier: str | None = None) -> EventCounts:
    """Events per (u, year, sex, age, ICD category) for a column that holds several codes
    concatenated (SINASC's CODANOMAL: "Q02Q690"), or several columns read together (the lines of a
    death certificate: every cause it mentions): an event counts once under each distinct
    category it carries. Events carrying none are the complement, not counted here. ``classifier`` names the field's
    family (a declared group's role) and reads nothing."""
    columns = [column] if isinstance(column, str) else list(column)
    strata = _strata(dataset, event)
    key = {"what": "code_list_counts", "code": config.code_key(code_list_counts), **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year, "column": column,
           "data": config.data_version()}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else []), *columns] + ([strata["sex"]] if strata["sex"] else [])
    con = duckdb.connect()
    raw = _records(dataset, event, year, cols)
    con.register("r", raw)
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    text = "concat_ws(' ', " + ", ".join(f"coalesce(CAST(\"{c}\" AS VARCHAR), '')" for c in columns) + ")"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)},
            list_distinct(list_transform(regexp_extract_all(upper({text}),
                '[A-Z][0-9]{{2}}[0-9X]?'), x -> left(x, 3))) AS codes
        FROM r WHERE trim({text}) <> ''""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN len(codes) = 0 THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(sum(wt) AS INTEGER) AS y
        FROM (SELECT u, sex, age, wt, unnest(codes) AS code FROM e WHERE ({reason}) IS NULL)
        GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, NULL AS code,
            CAST(sum(wt) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): {columns} exploded"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def strata(dataset: str, event: str | None = None) -> dict:
    """The subject's residence, sex and age columns, their entity, and the sex implied when the strata are another
    person's (SINASC: the mother's), from pegasus_data's roles."""
    return _strata(dataset, event)


def _strata(dataset: str, event: str | None = None, year: int | None = None) -> dict:
    """The subject's residence, sex, age and race columns, from pegasus_data's roles (race: the subject's declared
    race stratum, the mother's on a birth, None where none is declared). ``event`` names the event type when its rows
    are not persons: a grid of people (SINAN-SDTA's ``case``) or a group (its ``outbreak``); without it, a dataset
    whose events count a grid reads the grid's strata. A role held by another column in another layout generation
    (SIM-DOFET's residence: MUNIRES to 1995, CODMUNRES from 1996) is read in ``year``'s column; without a year, in the
    latest generation's (keyed by the last row, the alphabetical MUNIRES failed every DOFET year since 1996)."""
    import pegasus_data as pg

    rs = pg.roles(dataset) if year is None else pg.roles(dataset, period=year)
    rows = sorted((r for r in rs if r.get("model") == "stratum"),
                  key=lambda r: (r.get("last_year") or 9999, r.get("first_year") or 0))
    by_prop = {r["property"]: r for r in rows}
    specs = pg.event_types(dataset) if _has_events(dataset) else []
    spec = next((e for e in specs if e["name"] == event), None) if event else next((e for e in specs if e.get("grid")), None)
    grid = (spec or {}).get("grid")

    def place(entity: str | None) -> dict:
        # a group has no residence: its place is the municipality of the entity it is (the outbreak's, where the group
        # fell ill; not the notification's)
        where = [r for r in rs if r.get("model") == "where" and r.get("property") == "municipality" and r["entity"] == entity]
        if len(where) != 1:
            raise LookupError(f"{dataset}: a group event needs one municipality of its entity {entity!r}, has {len(where)}")
        return {"residence": where[0]["column"], "place": "event", "entity": entity, "race": None}

    if grid:
        # a row counts a group of people by sex and age band (pegasus_data's weight grid): the grid's own columns are
        # the strata, its bands the ages, and the place is that of the entity its cells count
        return {**place({r["column"]: r["entity"] for r in rs}.get(grid["cells"][0]["column"])), "age": grid["age"],
                "age_missing": (), "age_bands": tuple(grid["bands"]), "sex": grid["sex"], "sex_canonical": True,
                "implied_sex": None}
    if spec is not None and spec.get("persons") is False:
        # a row is a group, not a person (an outbreak, pegasus_data `persons: false`): no sex or age; its events stand in
        # one cell (sex 1, age 0) and the whole population of the place is exposed there (`monolith._assemble`)
        return {**place(spec["kind"]), "age": None, "age_missing": (), "sex": None, "implied_sex": 1, "implied_age": 0,
                "persons": False}
    if "residence" not in by_prop:
        raise LookupError(f"{dataset}: no residence stratum in pegasus_data's roles")
    age = by_prop.get("age_years") or by_prop.get("age")
    if age is None:
        raise LookupError(f"{dataset}: no age stratum in pegasus_data's roles")
    entity = by_prop["residence"]["entity"]
    implied = {"mother": 2}.get(entity)
    if "sex" not in by_prop and implied is None:
        raise LookupError(f"{dataset}: no sex stratum, and entity {entity!r} implies none")
    return {"residence": by_prop["residence"]["column"], "place": "residence", "age": age["column"],
            "age_missing": tuple(age.get("missing") or ()),
            "sex": by_prop["sex"]["column"] if "sex" in by_prop else None, "implied_sex": implied, "entity": entity,
            "race": by_prop["race"]["column"] if "race" in by_prop else None}


def _has_events(dataset: str) -> bool:
    import pegasus_data as pg

    try:
        pg.event_types(dataset)
    except KeyError:
        return False
    return True


CANONICAL_LEVELS = ("chapter", "group", "category", "subcategory")


@functools.cache
def code_tree(name: str) -> pa.Table:
    """A classifier tree with its levels in the roles the model reads (``level``: chapter, the roots; category, the
    level above the leaves, the model's leaves; subcategory, the leaves; group, every level between) and the
    structure's own name kept (``native_level``). The roles follow from the tree's depth, never from its names: ICD-10's
    levels are already these; SIGTAP's group, subgroup, form and procedure become chapter, group, category and
    subcategory. ``width`` is the category codes' length (3 for ICD-10, 6 for SIGTAP)."""
    t = code_structure(name)
    code, parent, level = (t.column(c).to_pylist() for c in ("code", "parent", "level"))
    up = dict(zip(code, parent, strict=True))

    def depth(c: str) -> int:
        d = 0
        while up.get(c) is not None:
            c, d = up[c], d + 1
        return d

    by_level: dict[str, list[int]] = {}
    for c, lv in zip(code, level, strict=True):
        by_level.setdefault(lv, []).append(depth(c))
    order = sorted(by_level, key=lambda lv: float(np.median(by_level[lv])))
    role = {lv: ("chapter" if i == 0 else "subcategory" if i == len(order) - 1 and len(order) > 2
                 else "category" if i == len(order) - 2 or len(order) == 2 else "group") for i, lv in enumerate(order)}
    cats = [c for c, lv in zip(code, level, strict=True) if role[lv] == "category"]
    width = int(np.median([len(c) for c in cats])) if cats else 3
    return (t.set_column(t.column_names.index("level"), "level", pa.array([role[lv] for lv in level]))
            .append_column("native_level", pa.array(level))
            .replace_schema_metadata({"width": str(width)}))


def category_width(name: str) -> int:
    return int(code_tree(name).schema.metadata[b"width"])


@functools.cache
def token_rule(dataset: str, column: str) -> dict | None:
    """How a column packs several codes into a cell, from pegasus_data's curation (`describe`: ``multi_valued``,
    ``token_rule``), None for a column of one code a cell."""
    import re

    import pegasus_data as pg

    parts = re.split(r"[-.]", dataset, maxsplit=1)          # "SIH-RD" -> SIH, RD; "SIM.DO" -> SIM, DO
    system, series = parts[0], (parts[1] if len(parts) > 1 else None)
    for args in ((system, series), (system, None)):
        try:
            d = pg.describe(*args, field=column)
        except Exception:  # noqa: BLE001 - a spelling the catalog does not know: try the next
            continue
        return dict(d.token_rule) if d.multi_valued and d.token_rule else None
    raise LookupError(f"{dataset}.{column}: pegasus_data describes no such field")


@functools.cache
def column_name(dataset: str, column: str) -> str:
    """A column's name as its source documents it (pegasus_data `describe`: the official name, else the curated
    English one), else the column itself."""
    import re

    import pegasus_data as pg

    parts = re.split(r"[-.]", dataset, maxsplit=1)
    for args in ((parts[0], parts[1] if len(parts) > 1 else None), (parts[0], None)):
        try:
            d = pg.describe(*args, field=column, root=config.data_root())
        except Exception:  # noqa: BLE001 - a spelling the catalog does not know: try the next
            continue
        return str(d.official_name or d.translated_name or column)
    return column


@functools.cache
def value_labels(dataset: str, event: str, column: str, years: tuple[int, ...]) -> dict[str, str]:
    """``code -> label`` for a group column (a composition or the race stratum), labelled as pegasus_data labels a
    query (`pg.levels`), weighed on every value the column holds in ``years``: a subset can choose another table
    (SINAN-TOXC's CRITERIO with one stray code read as meningitis's criteria). A code no table decodes is absent."""
    import pegasus_data as pg

    from .tools import group_columns

    missing = group_columns(dataset, event).get(column)
    codes: set[str] = set()
    if missing is not None and column != _strata(dataset, event).get("race"):
        primary = next((c["column"] for c in event_type(dataset, event).get("classifiers") or []
                        if c["role"] == "primary"), None)
        for y in years:
            try:
                c = composition_counts(dataset, event, int(y), column, missing, primary)
            except Exception:  # noqa: BLE001 - a year that does not hold the column labels nothing
                continue
            if c.counts is not None and "value" in c.counts.column_names:
                codes |= {str(v) for v in pc.unique(c.counts.column("value")).to_pylist() if v is not None}
    elif column == _strata(dataset, event).get("race"):
        codes = {str(k) for k in range(10)}       # the race stratum's codes: one digit
    else:
        # any other column, by the codes its records hold: weighed on 0-9, SINAN-TOXC's CLASSI_FIN (1, 2, 8) took
        # polio's table, "Confirmado Poliovírus Selvagem" for 1 (2026-10-12)
        for y in years:
            try:
                raw = _records(dataset, event, int(y), [column])
            except Exception:  # noqa: BLE001 - a year that does not hold the column labels nothing
                continue
            codes |= {str(v).strip() for v in pc.unique(raw.column(column)).to_pylist() if v not in (None, "")}
    if not codes:
        return {}
    return pg.levels(dataset, column, sorted(codes), root=config.data_root())


def has_code_structure(name: str) -> bool:
    """Whether pegasus_data serves a code tree of this name (`_TREES`)."""
    return name in _TREES


def event_types(dataset: str) -> list[dict]:
    """The event types pegasus_data declares for ``dataset``."""
    import pegasus_data as pg

    return list(pg.event_types(dataset))


def event_datasets() -> list[str]:
    """Every dataset pegasus_data declares event types for: what a survey of the whole store runs over."""
    from pegasus_data.semantics.event_types import load_event_types

    return sorted(load_event_types())


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


def code_attributes(structure: str = "ICD10") -> pa.Table:
    """Each code's attributes as pegasus_data serves them (`pegasus_data.code_attributes`: the DATASUS CID-10 release's
    dual role, sex restriction, underlying-cause eligibility; the external-cause axes)."""
    import pegasus_data as pg

    key = {"what": "code_attributes", "structure": structure, "data": config.data_version(),
           "resource": config.resource_version("code_attributes.parquet")}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    table = pg.code_attributes(structure)
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


_REGIONS: dict = {}


def regions(places, classification: str) -> np.ndarray:
    """The unit of ``classification`` (``ibge_immediate_region``, ``health_region``, ``uf``,
    ``ibge_macroregion``…) each place belongs to, as strings in the given order; a place
    without one raises (never guessed). Kept per place set (in the process and the store): one
    lookup per municipality took 20 s of a field's question pass (2026-10-08)."""
    import hashlib

    import pegasus_data as pg

    codes = np.asarray([int(c) for c in places], dtype=np.int64)
    digest = hashlib.sha256(codes.tobytes()).hexdigest()[:16]
    mem = (classification, digest)
    if mem not in _REGIONS:
        key = {"what": "regions", "classification": classification, "places": digest, "data": config.data_version(),
               "code": config.code_key(regions)}
        cached = store.get_table("gateway", key)
        if cached is None:
            out = []
            for c in codes:
                m = pg.memberships(str(int(c))).get(classification)
                if m is None:
                    raise LookupError(f"municipality {int(c)} has no {classification} membership in pegasus_data")
                out.append(m.member_code)
            cached = pa.table({"u": codes, "unit": pa.array(out, pa.string())})
            store.put_table("gateway", key, cached, {"source": f"pegasus_data.memberships: {classification}"})
        _REGIONS[mem] = np.asarray(cached.column("unit").to_pylist())
    return _REGIONS[mem].copy()


def field_overlap(dataset: str, event: str, a: dict[str, list[str]], b: dict[str, list[str]],
                  period: object) -> dict:
    """Measured share of events two fields have in common (ARCHITECTURE §8.5), from records."""
    import pegasus_data as pg

    key = {"what": "overlap", "dataset": dataset, "event": event, **_declared_key(dataset, event), "a": a, "b": b, "period": str(period),
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


def context_sum(name: str, year: int, where: dict[str, str] | None = None) -> pa.Table:
    """A context field whose rows are strata (ANS beneficiaries by sex × age × coverage, INEP enrolments by margin):
    (u, value) summed over the rows with ``where`` (column = value) for one year, u 6-digit."""
    import pegasus_data as pg

    key = {"what": "context_sum", "name": name, "year": year, "where": where or {}, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.load_field(name, years=[year], settings=pg.load_settings(root=config.data_root()))
    con = duckdb.connect()
    con.register("r", raw)
    cond = " AND ".join(f"CAST(\"{c}\" AS VARCHAR) = '{v}'" for c, v in (where or {}).items()) or "true"
    table = con.execute(f"""SELECT CAST(left(CAST(municipality AS VARCHAR), 6) AS INTEGER) AS u, sum(CAST(value AS DOUBLE)) AS value
                            FROM r WHERE {cond} AND year = {year} GROUP BY 1 ORDER BY 1""").fetch_arrow_table()
    store.put_table("gateway", key, table, {"source": f"pegasus_data.load_field({name}) summed"})
    return table


def declared_fields() -> dict:
    """pegasus_data's declared context fields (`curation/fields.yml`): each one's source, unit, years and declarations
    (``over``, ``icd10``, ``harm``)."""
    from pegasus_data.fields import declared_fields as declared

    return declared()


def _context_entry(entry: str | dict) -> tuple[list[str], dict | None, str | None, list[int]]:
    """A context entry's numerator fields (``a+b`` summed), its strata filter, its one denominator (pegasus_data
    `fields.yml` ``over``: another field, or ``population``) and its declared years."""
    from pegasus_data.fields import _years

    spec_of = declared_fields()
    names = entry["field"].split("+") if isinstance(entry, dict) else entry.split("+")
    # a field whose rows are strata declares the rows that make it one value per place (ANS's medical-hospital
    # plans, INEP's total margin); read by name without them it failed on a missing status (the survey, 2026-10-11)
    where = entry.get("where") if isinstance(entry, dict) else (spec_of[names[0]].get("where") if len(names) == 1 else None)
    if isinstance(entry, dict) and "over" in entry:
        # an entry's own denominator: a stratum of a field (a medicine's sales of all medicines sold) is a rate of
        # something the whole field is not
        over = {entry["over"]}
    else:
        over = {spec_of[n].get("over") for n in names}
    if len(over) != 1:
        raise ValueError(f"{entry}: the summed fields declare different denominators {sorted(map(str, over))}")
    return names, where, over.pop(), sorted(set(_years(str(spec_of[names[0]]["years"]))))


def context_name(entry: str | dict) -> str:
    """A context entry's name in tables and reports: its own ``name``, else its fields (and their filter)."""
    if isinstance(entry, str):
        return entry
    return entry.get("name") or entry["field"] + (f" [{entry['where']}]" if entry.get("where") else "")


def rated(contexts: list) -> list:
    """The context entries that are rates (a declared or an entry's own denominator): a count with none would rank
    places by their size alone."""
    out = []
    for c in contexts:
        try:
            if _context_entry(c)[2]:
                out.append(c)
        except (KeyError, ValueError):
            continue
    return out


def condition_codes(dataset: str) -> list[str]:
    """The ICD-10 codes ``dataset``'s records carry as their condition (pegasus_data `condition_codes`: a SINAN
    agravo's ID_AGRAVO), any year."""
    import pegasus_data as pg

    t = pg.condition_codes(root=config.data_root())
    return sorted({str(c).replace(".", "").upper() for d, c in zip(t.column("dataset").to_pylist(),
                                                                   t.column("code").to_pylist(), strict=True)
                   if c and same_dataset(d, dataset)})


def treatments(codes: list[str]) -> list[dict]:
    """pegasus_data's declared treatments of ICD-10 ``codes`` (`pegasus_data.treatments`): medicines an official
    document gives for them, each with the declared fields that count it."""
    import pegasus_data as pg

    return pg.treatments(codes)


def _context_counts(names: list[str], where: dict | None, over: str | None, year: int,
                    places: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One year of a context on ``places``: its numerator and its denominator (residents for ``population``, the
    ``over`` field, else 1), NaN where a place has none."""
    index = {int(u): i for i, u in enumerate(places)}

    def values(name: str, rows_where=None) -> np.ndarray:
        out = np.full(len(places), np.nan)
        if rows_where is not None:
            # a stratum is 0 where the field has rows that year and none of the stratum's: SNGPC's pharmacies of a
            # municipality sold no spiramycin. Left NaN, the mean was of the 2,097 places that sold any (2026-10-11).
            # A place the field has no rows for that year stays unknown.
            for u in context_sum(name, year).column("u").to_pylist():
                i = index.get(int(u))
                if i is not None:
                    out[i] = 0.0
            t = context_sum(name, year, rows_where)
            pairs_ = zip(t.column("u").to_pylist(), t.column("value").to_pylist(), strict=True)
        else:
            t = context_field(name, years=[year])
            ok = [s in ("value", "zero", "ok") for s in t.column("status").to_pylist()]
            pairs_ = ((u, v) for u, v, o in zip(t.column("u").to_pylist(), t.column("value").to_pylist(), ok,
                                                 strict=True) if o)
        for u, v in pairs_:
            i = index.get(int(u))
            if i is not None and v is not None:
                out[i] = float(v)
        return out

    num = sum(values(n, where) for n in names)
    if over == "population":
        tot = population([year]).group_by("u").aggregate([("n", "sum")])     # once: group order is not stable
        den = np.full(len(places), np.nan)
        for u, n in zip(tot.column("u").to_pylist(), tot.column("n_sum").to_pylist(), strict=True):
            if int(u) in index:
                den[index[int(u)]] = n
    elif over:
        den = values(over)
    else:
        den = np.ones(len(places))
    return num, den


def context_value(entry: str | dict, years: list[int], places: np.ndarray) -> tuple[np.ndarray, str]:
    """A context on ``places`` over the window ``years`` (`dependency`): a declared field's value over its declared
    denominator (pegasus_data `fields.yml` ``over``: another field, or ``population``, the residents), the mean of its
    years in the window, or of the declared year nearest the window's end when it has none there (a census). ``entry``
    is a field's name, numerators of one denominator summed (``a+b``), or {field, where} for a field whose rows are
    strata (`context_sum`). Returns the values (NaN where a place has none) and a label."""
    names, where, over, declared = _context_entry(entry)
    inside = [y for y in declared if years[0] <= y <= years[-1]]
    chosen = inside or [min(declared, key=lambda y: (abs(y - years[-1]), -y))]
    per_year = []
    for year in chosen:
        num, den = _context_counts(names, where, over, year, places)
        with np.errstate(all="ignore"):
            per_year.append(np.where(den > 0, num / den, np.nan))
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        value = np.nanmean(np.stack(per_year), axis=0)
    label = context_name(entry) + (f" over {over}" if over else "") +         f", {chosen[0]}" + (f"-{chosen[-1]}" if len(chosen) > 1 else "")
    return value, label


def context_series(entry: str | dict, years: list[int], places: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[int], str]:
    """A time-varying context on ``places`` year by year (ARCHITECTURE §8.2): its numerator and denominator [U, T] over
    the declared years inside ``years``, and its family: ``binomial`` where the denominator is a field the numerator
    is part of (samples with E. coli present of those assessed: never above it), ``poisson`` on residents or on a
    field it is a rate of. A context with no denominator, or with fewer than three declared years in the window, has
    no series (a census is read by `context_value`)."""
    names, where, over, declared = _context_entry(entry)
    inside = [y for y in declared if years[0] <= y <= years[-1]]
    if not over or len(inside) < 3:
        raise ValueError(f"{entry}: no denominator or fewer than three years in {years[0]}-{years[-1]}: not a series")
    parts = [_context_counts(names, where, over, y, places) for y in inside]
    # a declared year the lake holds nothing of is not a year of the series (SNGPC is declared 2014-2026 and built for
    # 2019-2021): its columns would be all unknown
    held = [j for j, p in enumerate(parts) if np.isfinite(p[0]).any()]
    if len(held) < 3:
        raise ValueError(f"{entry}: data in {len(held)} of its years in {years[0]}-{years[-1]}: not a series")
    inside, parts = [inside[j] for j in held], [parts[j] for j in held]
    k, n = np.stack([p[0] for p in parts], 1), np.stack([p[1] for p in parts], 1)
    ok = np.isfinite(k) & np.isfinite(n) & (n > 0)
    family = "binomial" if over != "population" and ok.any() and bool((k[ok] <= n[ok] + 1e-9).all()) else "poisson"
    return k, n, inside, family



def nothing_published() -> type[Exception]:
    """The exception pegasus_data raises when a system publishes nothing for the requested period."""
    from pegasus_data._request import NothingPublished

    return NothingPublished


def roles(dataset: str) -> list[dict]:
    """pegasus_data's roles of a dataset's columns."""
    import pegasus_data as pg

    return pg.roles(dataset)


def event_type(dataset: str, event: str) -> dict:
    """pegasus_data's declaration of one event type (its classifiers and marks)."""
    import pegasus_data as pg

    return next(e for e in pg.event_types(dataset) if e["name"] == event)


def raw_event_counts(dataset: str, event: str, year: int, by: list[str]):
    """``count_events`` for a whole year, Brazil, by the given raw columns (complete: no partial answer, 8 GiB ceiling)."""
    control.check_reserved(dataset, [year])      # the confirmation reserve: read by claims only
    import pegasus_data as pg

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pg.count_events(dataset, event, period=year, geography="BR", by=by, root=config.data_root(),
                               allow_partial=False, max_download=max_download())


def raw_field(name: str, years: list[int]):
    """``load_field`` of a context field in PegaSUS's data root, as pegasus_data serves it."""
    import pegasus_data as pg

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pg.load_field(name, years=years, settings=pg.load_settings(root=config.data_root()))



def delay_counts(dataset: str, event: str, year: int, report: str, onset: str | None = None,
                 codes: tuple[str, ...] | list = (), classifier: str | None = None) -> pa.Table:
    """The reporting delay of one publication year (phase 4, ADR-0004): events by residence ``u``, the epidemiological
    week of their onset (``onset``; default the event's date, `_when`) and the whole weeks between it and the
    ``report`` date (SINAN's data entry, DT_DIGITA; SIH's processing month; SIM's registration). Rows with either
    date missing or a negative delay are left out and counted in the table's metadata. ``codes``: only the events whose
    ``classifier`` code (default the primary) starts with one of them, a field's (SIM chapter IX's known deaths, not
    every death against IX's baseline: 3.5 times the alarms, 2026-10-10). Columns: u, the onset day ``onset``, its
    epidemiological ``year`` and ``week``, ``delay_days``, ``delay`` (whole weeks) and n: days, so a reading as of any
    day counts what was reported by then (a Wednesday as-of had discarded four days, 2026-10-11)."""
    when = onset or _when(dataset)
    codes = sorted({str(c).replace(".", "").upper() for c in codes})
    if codes and classifier is None:
        classifier = next((c["column"] for c in event_type(dataset, event).get("classifiers") or [] if c["role"] == "primary"), None)
        if classifier is None:
            raise ValueError(f"{dataset} {event}: codes need a classifier, and the event type has none")
    key = {"what": "delay_counts", "code": config.code_key(delay_counts), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year, "onset": when, "report": report,
           "data": config.data_version(), **_df_key(dataset, year), **({"codes": codes, "classifier": classifier} if codes else {})}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    strata = _strata(dataset, event)
    raw = _records(dataset, event, year, [strata["residence"], when, report] + ([classifier] if codes else []))
    con = duckdb.connect()
    con.register("r", raw)
    where = ("WHERE " + " OR ".join(f"starts_with(upper(trim(CAST(\"{classifier}\" AS VARCHAR))), '{c}')" for c in codes)
             if codes else "")
    t = con.execute(f"""SELECT {_residence_sql(strata["residence"])} AS u, {_date_sql(when)} AS d0,
                        {_date_sql(report)} AS d1 FROM r {where}""").fetch_arrow_table()
    d0 = t.column("d0").to_numpy(zero_copy_only=False).astype("datetime64[D]")
    d1 = t.column("d1").to_numpy(zero_copy_only=False).astype("datetime64[D]")
    u = t.column("u").to_numpy(zero_copy_only=False)
    ok = ~np.isnat(d0) & ~np.isnat(d1) & (d1 >= d0) & np.isfinite(u.astype(float))
    days = (d1[ok] - d0[ok]).astype(np.int64)
    df = pd.DataFrame({"u": u[ok].astype(np.int64), "onset": d0[ok], "delay_days": days})
    df = df.groupby(["u", "onset", "delay_days"]).size().rename("n").reset_index()
    ey, ew = epi_week(df["onset"].to_numpy().astype("datetime64[D]"))
    df["year"], df["week"], df["delay"] = ey, ew, df["delay_days"] // 7
    out = pa.Table.from_pandas(df[["u", "onset", "year", "week", "delay_days", "delay", "n"]], preserve_index=False)
    store.put_table("gateway", key, out, {**key, "left_out": int((~ok).sum()), "records": int(len(ok))})
    return out


#: an establishment's facts read for an institutional finding (ARCHITECTURE §9.1): pegasus_data's CNES.ST attributes
#: (`_query_engine.planner.CNES_ATTRIBUTE_FIELDS`), as the establishment was registered in the month read
ESTABLISHMENT_FACTS = ("CNES.TYPE", "CNES.CARE_LEVEL", "CNES.SUS_LINK", "CNES.MANAGEMENT", "CNES.SURGICAL_BEDS",
                       "CNES.CLINICAL_BEDS", "CNES.HAS_OBSTETRIC_CENTRE", "CNES.HAS_NEONATAL_UNIT", "CNES.HAS_EMERGENCY")


def establishment_facts(codes: list[str], year: int, month: int = 12) -> dict[str, dict[str, str]]:
    """Each CNES code's registration in ``year``-``month`` (CNES.ST, national, labelled: the establishment's name and its
    `ESTABLISHMENT_FACTS`); a code absent that month is absent from the result (not yet open, or closed). One national
    month is read once and kept in the store."""
    import pegasus_data as pg
    from pegasus_data._query_engine.planner import CNES_ATTRIBUTE_FIELDS

    cols = ["CNES", "CODUFMUN", *(CNES_ATTRIBUTE_FIELDS[f] for f in ESTABLISHMENT_FACTS)]
    key = {"what": "establishment_facts", "year": int(year), "month": int(month), "columns": cols,
           "data": config.data_version()}
    table = store.get_table("gateway", key)
    if table is None:
        raw = pg.query("CNES.ST", period=f"{int(year)}-{int(month):02d}", geography="BR", select=cols,
                       root=config.data_root())
        names = {f"({c})": c for c in cols}
        table = raw.rename_columns([next((v for k, v in names.items() if n.endswith(k)), n) for n in raw.column_names])
        store.put_table("gateway", key, table, {"source": f"pegasus_data.query(CNES.ST, {year}-{month:02d})"})
    want = {str(c).strip() for c in codes}
    out = {}
    for r in table.to_pylist():
        label = str(r.get("CNES") or "")
        code = label.rsplit("(", 1)[-1].rstrip(")") if label.endswith(")") else label
        if code in want:
            out[code] = r
    return out


def municipality_names() -> dict[str, dict[str, str]]:
    """Every municipality's name, state and macro-region by its six-digit code (pegasus_data's geography)."""
    from pegasus_data import geography

    return geography.municipalities()


def epi_week(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(epidemiological year, week) of each date (datetime64[D]): weeks run Sunday to Saturday, and week 1 of year
    Y is the week holding 4 January of Y, so a week belongs to the year of its Wednesday."""
    d = np.asarray(dates, dtype="datetime64[D]")
    dow = (d.astype(np.int64) + 4) % 7                   # 1970-01-01 was a Thursday: 0 = Sunday
    start = d - dow.astype("timedelta64[D]")
    year = (start + np.timedelta64(3, "D")).astype("datetime64[Y]").astype(np.int64) + 1970
    jan4 = (np.array(year - 1970, dtype="datetime64[Y]").astype("datetime64[D]") + np.timedelta64(3, "D"))
    first = jan4 - ((jan4.astype(np.int64) + 4) % 7).astype("timedelta64[D]")
    week = ((start - first).astype(np.int64) // 7 + 1).astype(np.int64)
    return year.astype(np.int64), week


def code_groups(dataset: str) -> dict[str, list[str]]:
    """The columns pegasus_data declares to be read together as one set of codes (its linkage roles of type
    ``codes``: every diagnosis of an admission, every cause a death certificate mentions), by role."""
    from pegasus_data.linkage.roles import load_roles

    spec = next((v for k, v in load_roles().items() if same_dataset(k, dataset)), None)
    if spec is None:
        return {}
    return {name: [r.column, *r.also] for name, r in spec.roles.items() if getattr(r, "type", "") == "codes"}


#: the disk a lake build leaves free at least (GB): the lake is a cache of the published files, never worth the disk
LAKE_MIN_FREE_GB = 15


def ensure_lake(dataset: str, years: list[int], log=print) -> dict:
    """pegasus_data's lake over ``dataset``'s ``years`` in PegaSUS's data root (`pegasus_data.build_lake`, without
    labels): every raw read after it is a Parquet scan. Without it each process decoded the DBC files again: a national
    CIHA year took 30-60 min, from the lake 12 s (2026-10-09). Refused when the disk would fall under
    `LAKE_MIN_FREE_GB`."""
    import shutil

    import pegasus_data as pg

    free = shutil.disk_usage(config.data_root()).free / 1024**3
    if free < LAKE_MIN_FREE_GB:
        raise OSError(f"{free:.0f} GB free, under the {LAKE_MIN_FREE_GB} GB a lake build leaves")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # the downloaded files go once their verified partitions hold them: kept, each gigabyte a deep study may
        # download (40) cost disk twice, against 19 GB free (2026-10-11); a rebuild fetches them again
        counts = pg.build_lake(dataset, years, root=config.data_root(), release=True)
    freed = (counts.get("released") or {}).get("bytes", 0) / 1024**3
    log(f"lake {dataset} {years[0]}-{years[-1]}: {counts.get('files', 0)} files decoded, "
        f"{counts.get('partitions', 0)} partitions written, {counts.get('partitions_reused', 0)} kept, "
        f"{freed:.1f} GB of downloads released")
    return counts


@functools.cache
def published_years(dataset: str) -> frozenset[int]:
    """The years pegasus_data's catalog holds a publication of ``dataset`` for (`pegasus_data.availability`)."""
    import pegasus_data as pg

    return frozenset(int(y) for y in pg.availability(dataset, root=config.data_root()).published_years)


def link_specs() -> dict:
    """pegasus_data's declared links (`curation/links.yml`): each spec's left and right sides."""
    from pegasus_data.linkage.engine import load_links

    return load_links()


#: whether a link absent from the store is computed (a national probabilistic linkage: hours per year) or refused;
#: ``PEGASUS_COMPUTE_LINKS=1`` opts in. Reading stored runs only is the default: a reading never launches one silently
COMPUTE_LINKS = os.environ.get("PEGASUS_COMPUTE_LINKS", "") == "1"


class LinkNotStored(LookupError):
    """A declared link's run for a year is not in the store, and computing it was not asked for."""


def stored_pairs(link: str, year: int, compute: bool | None = None) -> pa.Table:
    """A declared link's national probabilistic pairs for ``year``: the stored run (pegasus_data's link store in
    PegaSUS's data root), computed when ``compute`` (by default `COMPUTE_LINKS`) allows; else `LinkNotStored`, which a
    reading reports. `update` computes the runs a plan reads as a declared step (S2.2)."""
    import pegasus_data as pg
    from pegasus_data.linkage import store as link_store
    from pegasus_data.linkage.engine import link_method, stored_key

    spec = link_specs().get(link)
    for sd in (spec.left, spec.right) if spec else ():
        # a run's pairs carry its sides' records of its years: one touching the confirmation reserve is a claim's
        before, after = tuple(getattr(sd, "pad_years", None) or (0, 0))
        control.check_reserved(sd.dataset, range(year - before, year + after + 1))
    method = link_method(link)                 # probabilistic where declared; deterministic keys only otherwise
    settings = pg.load_settings(root=config.data_root())
    hit = link_store.load(settings, stored_key(link, method, year, "BR"))
    if hit is not None:
        return hit[0]
    if not (COMPUTE_LINKS if compute is None else compute):
        raise LinkNotStored(f"{link} {year}: no stored run (set PEGASUS_COMPUTE_LINKS=1, or `pegasus-data link "
                            f"{link} --period {year} --geo BR --method {method}`)")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pg.link(link, period=year, geography="BR", method=method, root=config.data_root()).pairs


def link_report(link: str, year: int) -> dict | None:
    """The report of ``link``'s stored national run for ``year`` without reading its pairs (None when not stored): what
    a scope checks and prices a run by (`study._link_runs_needed`)."""
    import json

    import pegasus_data as pg
    from pegasus_data.linkage import store as link_store
    from pegasus_data.linkage.engine import link_method, stored_key

    key = stored_key(link, link_method(link), year, "BR")
    path = link_store.links_dir(pg.load_settings(root=config.data_root())) / key.spec / f"{key.stem}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.with_suffix(".parquet").exists() else None


def covering_runs(link: str, side: str, year: int) -> list[int]:
    """The years of the runs whose scope holds ``side``'s records of ``year``: a side padded by (before, after) years
    is read by run z for its years z − before … z + after, so its records of ``year`` by runs year − after … year +
    before. A birth of December 2021 whose baby died in January 2022 is paired in run 2022 (S2.1)."""
    spec = link_specs()[link]
    before, after = tuple(getattr(spec.left if side == "left" else spec.right, "pad_years", None) or (0, 0))
    return list(range(year - after, year + before + 1))


def side_pairs(link: str, side: str, year: int, compute: bool | None = None) -> pa.Table:
    """Every pair of ``link`` that can hold ``side``'s records of ``year``: the stored runs `covering_runs` names (one
    run read alone missed the follow-up that crosses a year). A missing covering run raises `LinkNotStored`: the
    year's follow-up is incomplete, and a reading says so rather than counting it short."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parts = [stored_pairs(link, z, compute) for z in covering_runs(link, side, year)]
    return pa.concat_tables(parts, promote_options="default") if len(parts) > 1 else parts[0]


def link_sensitivity(link: str, year: int) -> pa.Table:
    """(u, n, k) for one stored run of ``link``: the records of its declared sensitivity side (`sensitivity`: every one
    should find a partner, as every infant death has its birth) by residence, and the expected number paired
    (pegasus_data `side_counts`), a partner found through any route of the scope's persons counting (S2.4(e): an
    infant death the direct link missed that an admission and its certificate reached). k/n is the link's sensitivity
    there; a run not stored raises `LinkNotStored`."""
    import hashlib
    import inspect

    from pegasus_data.linkage.engine import side_counts

    spec = link_specs()[link]
    side = getattr(spec, "sensitivity", "")
    if not side:
        raise ValueError(f"{link} declares no sensitivity side")
    sd = spec.left if side == "left" else spec.right
    res_col = _strata(sd.dataset)["residence"]
    role = next(r["role"] for r in roles(sd.dataset) if r["column"] == res_col)
    key = {"what": "link_sensitivity", "link": link, "year": year, "data": config.data_version(),
           "code": config.code_key(link_sensitivity), "runs": _scope_runs(year),
           # pegasus_data's reader is not in PegaSUS's code key: its own source keys what it counts
           "side_counts": hashlib.sha256(inspect.getsource(side_counts).encode()).hexdigest()[:12]}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    stored_pairs(link, year)                      # raises LinkNotStored when the run is absent
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = side_counts(link, period=year, side=side, by=role, root=config.data_root(), persons=persons(year))
    con = duckdb.connect()
    con.register("r", raw)
    out = con.execute(f"""SELECT {_residence_sql("unit")} AS u, CAST(sum(n) AS DOUBLE) AS n, sum(k) AS k
        FROM r GROUP BY 1 HAVING u IS NOT NULL ORDER BY 1""").fetch_arrow_table()
    store.put_table("gateway", key, out, {"source": f"pegasus_data side_counts({link}, {side})"})
    return out


def link_completeness(link: str, side: str, year: int) -> dict[int, float]:
    """The link's sensitivity for ``side``'s records of ``year`` by residence: the sensitivity side's records over the
    runs that hold them (`covering_runs`: a birth's infant death falls in its year or the next), shrunk to its state's
    by an empirical-Bayes beta (method of moments over the state's municipalities). A share of births followed by an
    infant death is the death rate times this: 20 of its first 23 departures were the link's holes (S2.3)."""
    parts = [link_sensitivity(link, z) for z in covering_runs(link, side, year)]
    con = duckdb.connect()
    for i, prt in enumerate(parts):
        con.register(f"p{i}", prt)
    tab = con.execute("SELECT u, sum(n) AS n, sum(k) AS k FROM (" + " UNION ALL ".join(f"SELECT * FROM p{i}" for i in range(len(parts)))
                      + ") GROUP BY u").fetch_arrow_table()
    u = tab.column("u").to_numpy().astype(np.int64)
    n = tab.column("n").to_numpy().astype(float)
    k = np.minimum(tab.column("k").to_numpy().astype(float), n)
    uf = u // 10000
    out: dict[int, float] = {}
    for s in np.unique(uf):
        m = uf == s
        cbar = float(k[m].sum() / max(n[m].sum(), 1e-9))
        c = k[m] / np.maximum(n[m], 1e-9)
        # between-place variance of the sensitivity beyond the binomial's (method of moments), so θ = c̄(1 − c̄)/τ² − 1
        w = n[m] / max(n[m].sum(), 1e-9)
        total = float(np.sum(w * (c - cbar) ** 2))
        binom = float(np.sum(w * cbar * (1 - cbar) / np.maximum(n[m], 1.0)))
        tau2 = max(total - binom, 1e-6)
        theta = max(cbar * (1 - cbar) / tau2 - 1.0, 0.0)
        for uu, kk, nn in zip(u[m], k[m], n[m], strict=True):
            out[int(uu)] = float((kk + theta * cbar) / (nn + theta)) if nn + theta > 0 else cbar
        out[-int(s)] = cbar                       # a place without records: its state's
    return out


def _group_columns(dataset: str, sd) -> list[str]:
    """The columns of a link side's ``group`` roles (pegasus_data's roles), or [] for an ungrouped side."""
    if not sd.group:
        return []
    if getattr(sd, "latest", None) or sd.where:
        raise NotImplementedError("a grouped side with a filter or a 'latest' order is not read yet")
    by_role = {r["role"]: r["column"] for r in roles(dataset)}
    missing = [g for g in sd.group if g not in by_role]
    if missing:
        raise LookupError(f"{dataset}: group roles {missing} name no column")
    return [by_role[g] for g in sd.group]


def _rep_sql(group: list[str]) -> str:
    """A record's identity as its link pairs it: its own, or its group's (the smallest identity of the group, the
    engine's representative); a record missing any key is its own group, as in the engine (pegasus_data `_prepare`)."""
    if not group:
        return '"_rid"'
    anynull = " OR ".join(f'"{c}" IS NULL' for c in group)
    keys = f'CASE WHEN {anynull} THEN "_rid" END, ' + ", ".join(f'"{c}"' for c in group)
    return f'min("_rid") OVER (PARTITION BY {keys})'


def link_runs_key(link: str) -> str:
    """The content of ``link``'s stored runs (their reports, which name the pairs' identity and counts), as a key: a
    reader of the link carries it, so its assemblies and fits follow a run added, rerun or relabelled. Keyed on the
    data version alone, a fit made on pairs that matched nothing outlived their relabelling (2026-10-10)."""
    import hashlib
    from pathlib import Path

    h = hashlib.sha256()
    for report in sorted((Path(config.data_root()) / "lake" / "links" / link).glob("*.json")):
        h.update(report.name.encode())
        h.update(report.read_bytes())
    return h.hexdigest()[:12]


def linked_counts(dataset: str, event: str, year: int, link: str, side: str, classifier: str | None = None,
                  places: pa.Array | None = None, runs: str | None = None) -> EventCounts:
    """The events of one side of a declared link per (u, year, sex, age, code): n, kv the variance of the linked count
    (Σ p(1 − p), the linkage's own uncertainty), and k the expected number with a
    partner on the other side (each record's largest `p_match`; pegasus_data's probabilistic linkage, its stored
    national run). The share k/n is an outcome after the event on a cohort's side (births followed by an infant
    death) and a recording measure on the other (deaths that found their birth). A side filtered by its spec (`where`)
    keeps the event type's denominator: its records outside the filter are unlinked by construction. A side whose
    records the spec groups (the live births of one delivery) pairs one record per group, the smallest identity, as
    pegasus_data's engine chooses it: every member takes its group's partner. A side exploded into days pairs the
    record itself."""
    control.check_reserved(dataset, [year])      # the confirmation reserve: read by claims only

    spec = link_specs()[link]
    sd = spec.left if side == "left" else spec.right
    if not same_dataset(sd.dataset, dataset):
        raise ValueError(f"{link}: its {side} side is {sd.dataset}, not {dataset}")
    group = _group_columns(dataset, sd)
    strata = _strata(dataset, event)
    _per_record(dataset, event, "a link's pairs")
    key = {"what": "linked_counts", **_places_key(places, year), "dataset": dataset, "event": event, **_declared_key(dataset, event), "year": year,
           "link": link, "side": side, "classifier": classifier, "data": config.data_version(), "ids": 2,
           "runs": runs or link_runs_key(link),
           **_df_key(dataset, year), "code": config.code_key(linked_counts)}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    pairs = side_pairs(link, side, year)
    ids = pairs.column("l" if side == "left" else "r")
    p = pairs.column("p_match") if "p_match" in pairs.column_names else pa.array([1.0] * pairs.num_rows)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else [])] + ([strata["sex"]] if strata["sex"] else []) + \
        ([classifier] if classifier else []) + group
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)), identity=True)
    con = duckdb.connect()
    con.register("r", raw)
    con.register("pm", pa.table({"rid": ids, "p": p}))
    valid = places if places is not None else valid_places(year)
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            {_rep_sql(group)} AS rid FROM r""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(count(*) AS INTEGER) AS n,
            CAST(sum(coalesce(m.p, 0)) AS DOUBLE) AS k,
            CAST(sum(coalesce(m.p, 0) * (1 - coalesce(m.p, 0))) AS DOUBLE) AS kv
        FROM e LEFT JOIN (SELECT rid, max(p) AS p FROM pm GROUP BY rid) m USING (rid)
        WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(wt) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    if pairs.num_rows and not con.execute("SELECT count(*) FROM e JOIN pm USING (rid)").fetchone()[0]:
        # pairs that name none of the side's records name them another way (runs stored under the fallback identity
        # read zero everywhere until pegasus_data relabelled them, 2026-10-10): an empty share must not look measured
        raise LookupError(f"{link}: {pairs.num_rows} pairs, none naming a {dataset} record of {year}")
    sens = getattr(spec, "sensitivity", "")
    if sens and sens != side:
        # the other side's records should all find a partner: its linked share by residence is the link's sensitivity,
        # and this side's share (births followed by an infant death) is the outcome times it. The trials become the
        # records the link would have seen an outcome for, n × sensitivity (S2.3, OPEN_QUESTIONS 11)
        comp = link_completeness(link, side, year)
        uu = counts.column("u").to_numpy().astype(np.int64)
        c = np.array([comp.get(int(x), comp.get(-(int(x) // 10000), 1.0)) for x in uu])
        counts = counts.set_column(counts.schema.get_field_index("n"), "n",
                                   pa.array(counts.column("n").to_numpy().astype(float) * c))
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.link({link}): {side} side of {dataset}"
                                                       + (" (trials × the link's sensitivity)" if sens and sens != side else ""),
                                            "pairs": pairs.num_rows})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)



def cohort_records(dataset: str, event: str, year: int, columns: list[str]) -> tuple[pa.Table, pa.Array]:
    """One event type's records of ``year`` as persons (`tools.cohort`): on the lattice (u, sex, age class) with
    ``columns`` raw-coded, and each record's identity by pegasus_data's rule (what its links and persons name)."""
    control.check_reserved(dataset, [year])      # the confirmation reserve: read by claims only
    strata = _strata(dataset, event)
    cols = [strata["residence"], *([strata["age"]] if strata["age"] else [])] + ([strata["sex"]] if strata["sex"] else []) + columns
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)), identity=True)
    con = duckdb.connect()
    con.register("r", raw)
    keep = ", ".join(f'trim(CAST("{c}" AS VARCHAR)) AS "{c}"' for c in columns)
    t = con.execute(f"""SELECT {_cells_sql(strata, dataset, raw)}, {keep + ', ' if keep else ''}{_rep_sql([])} AS rid
        FROM r""").fetch_arrow_table()          # no attribute column: the cells and the identity alone
    if config.study_area() is not None:         # the study's area's persons (identities numbered before, nationally)
        t = t.filter(pa.array(config.in_area(np.nan_to_num(t.column("u").to_numpy(zero_copy_only=False)
                                                            .astype(float)).astype(np.int64))))
    return t, t.column("rid")


@functools.cache
def dataset_key(dataset: str) -> str:
    """A dataset's one name whatever its spelling (pegasus_data's `parse_dataset`: SIH-RD, SIH.RD and SIHSUS-RD are
    SIHSUS-RD). The event types, the roles and the links each spell some datasets their own way; compared by their
    spelling, SIH's every-diagnosis reader and its links were never found for SIHSUS-RD (2026-10-10)."""
    from pegasus_data._request import parse_dataset

    system, series = parse_dataset(dataset)
    return f"{system}-{series or system}".upper()


def same_dataset(a: str, b: str) -> bool:
    return dataset_key(a) == dataset_key(b)


def data_code(dataset: str) -> str:
    """pegasus_data's code of a dataset as its links and persons name it (SIHSUS-RD -> SIH-RD, SIM.DO -> SIM-DO)."""
    named = {dataset_key(sd.dataset): sd.dataset for spec in link_specs().values() for sd in (spec.left, spec.right)}
    return named.get(dataset_key(dataset), dataset.upper().replace(".", "-"))


def run_touches_reserve(link: str, year: int) -> bool:
    """Whether a run of ``link`` for ``year`` reads a side's year held in the confirmation reserve (`control.reserved`):
    a run reads its own year and its padded ones (before, after) of each side. Such a run is a claim's to read, never a
    plan's, a study's persons or a linked field's (SIM 2024's deaths reached SIH admissions and TOXC cohorts, 2026-10-11)."""
    spec = link_specs().get(link)
    if spec is None:
        return False
    for sd in (spec.left, spec.right):
        before, after = tuple(getattr(sd, "pad_years", None) or (0, 0))
        if set(control.reserved(sd.dataset)) & set(range(int(year) - before, int(year) + after + 1)):
            return True
    return False


def link_year_reserved(link: str, side: str, year: int) -> bool:
    """Whether ``side``'s records of ``year`` are paired by a run touching the confirmation reserve (`covering_runs`,
    `run_touches_reserve`): SIH 2023's admissions reach SIM through run 2023, whose SIM side is padded into 2024."""
    return any(run_touches_reserve(link, z) for z in covering_runs(link, side, year))


def reserved_links(year: int) -> frozenset[str]:
    """The declared links whose run of ``year`` touches the confirmation reserve (`run_touches_reserve`)."""
    return frozenset(name for name in link_specs() if run_touches_reserve(name, year))


def links_outside(datasets) -> frozenset[str]:
    """The declared links with a side outside ``datasets`` (any spelling; None: none is outside): a study's persons are
    made from the links among its own datasets, routes through them included (TOXC → SIH → SIM), never from every link
    of the year (the smoke study decoded other systems' records to build its TOXC cohort, 2026-10-11)."""
    if datasets is None:
        return frozenset()
    from pegasus_data._request import parse_dataset

    def canon(x):
        try:
            return parse_dataset(x)
        except Exception:  # noqa: BLE001 - a name pegasus_data does not parse is compared as written
            return (x, None)

    mine = {canon(d) for d in datasets}
    return frozenset(name for name, sp in link_specs().items()
                     if canon(sp.left.dataset) not in mine or canon(sp.right.dataset) not in mine)


def persons(year: int, draw: int | None = None, datasets=None, seeds=None):
    """The persons of one scope: every viable stored national run of ``year`` merged (pegasus_data `build_entities`,
    strongest evidence first, under a person's constraints); ``draw`` merges one plausible link set (each edge kept
    with its p_match). PegaSUS reads persons, not one link's pairs (S2.4)."""
    import pegasus_data as pg
    from pegasus_data.linkage.entities import build_entities

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # ``seeds`` (dataset, role, ids): only the components that hold those records (pegasus_data `build_entities`)
        return build_entities(period=year, geography="BR", settings=pg.load_settings(root=config.data_root()), draw=draw,
                              exclude=reserved_links(year) | links_outside(datasets), seeds=seeds)


def _scope_runs(year: int) -> list[str]:
    """The stored runs of a scope (their report files): a reading over its persons is current while they are."""
    from pathlib import Path

    return sorted(p.name for p in (Path(config.data_root()) / "lake" / "links").rglob(f"*_BR_{year}*.json"))


def person_quality(year: int, datasets=None, seeds=None) -> dict:
    """What one scope's persons rest on (S2.4(d)): per link, the edges merged, already one person and refused under a
    person's constraints (pegasus_data `build_entities`), and its triangles, its pairs against the persons the other
    links make (`entities.triangles`: the same partner or another). A reading over persons carries it."""
    import json

    import pegasus_data as pg
    from pegasus_data.linkage.entities import triangles

    key = {"what": "person_quality", "year": year, "data": config.data_version(), "code": config.code_key(person_quality),
           "runs": _scope_runs(year), **({"datasets": sorted(datasets)} if datasets is not None else {}),
           **({"seeds": [seeds[0], seeds[1], hashlib.sha256("|".join(map(str, sorted(seeds[2]))).encode()).hexdigest()[:16]]}
              if seeds is not None else {})}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return json.loads(cached.column("json")[0].as_py())
    # ``seeds``: what a cohort's persons rest on, its own components (a national merge kept 539,411 deaths-to-admissions
    # pairs for a cohort of 6,593, 2026-10-12); the triangles stay the links' own, over the year
    ent = persons(year, datasets=datasets, seeds=seeds)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tri = triangles(period=year, geography="BR", settings=pg.load_settings(root=config.data_root()),
                        exclude=reserved_links(year) | links_outside(datasets))
    out = {name: {**stats, "triangles": tri.get(name)} for name, stats in ent.by_spec.items()}
    store.put_table("gateway", key, pa.table({"json": [json.dumps(out)]}), {"source": "pegasus_data entities, triangles"})
    return out


def person_records(entities, kind: tuple[str, str], other: tuple[str, str]) -> set[str]:
    """The records of ``kind`` (pegasus_data dataset code, person role) whose person also has a record of ``other``."""
    from pegasus_data.linkage.entities import person_pairs

    return set(person_pairs(entities, kind, other).column("l").to_pylist())


def direct_reach(kind: tuple[str, str], other: tuple[str, str], year: int) -> list[dict]:
    """The declared links pairing ``kind``'s persons with ``other``'s directly, each with its runs covering ``year``
    and their verdicts: a run stored "not viable" merges no pair (pegasus_data `build_entities`), so the outcome is then
    reached only through other routes, and a cohort says so rather than count it as zero (SINAN-TOXC's deaths in SIM,
    2022: chance pairs up to 29%, 2026-10-12)."""
    from pegasus_data.linkage.engine import links_file
    from pegasus_data.semantics.curation import read_yaml

    raw = read_yaml(links_file()).get("links") or {}
    out = []
    for name, spec in link_specs().items():
        person = list((raw.get(name) or {}).get("person") or [])
        if len(person) != 2:
            continue
        sides = [(spec.left.dataset, person[0]), (spec.right.dataset, person[1])]
        if sides not in ([kind, other], [other, kind]):
            continue
        side = "left" if sides[0] == kind else "right"
        runs = []
        for z in covering_runs(name, side, year):
            rep = link_report(name, z)
            runs.append({"run": z, "verdict": "reserved" if run_touches_reserve(name, z) else
                         (rep or {}).get("verdict", "not stored"),
                         "chance_upper95_percent": (rep or {}).get("chance_upper95_percent")})
        out.append({"link": name, "runs": runs})
    return out


def person_scopes(kind: tuple[str, str], year: int) -> list[int]:
    """The scopes whose runs hold ``kind``'s records of ``year``: every declared link with a person of that kind on a
    side, over the runs that cover the side's year (`covering_runs`: a birth's infant death is in its year's run or
    the next)."""
    from pegasus_data.linkage.engine import links_file
    from pegasus_data.semantics.curation import read_yaml

    raw = read_yaml(links_file()).get("links") or {}
    out: set[int] = set()
    for name, spec in link_specs().items():
        person = list((raw.get(name) or {}).get("person") or [])
        for k, (side, sd) in enumerate((("left", spec.left), ("right", spec.right))):
            if len(person) > k and (sd.dataset, person[k]) == kind:
                out.update(z for z in covering_runs(name, side, year) if not run_touches_reserve(name, z))
    return sorted(out)


@contextlib.contextmanager
def machine_slot(pool: str, slots: int, label: str):
    """One of ``slots`` machine-wide slots of ``pool`` (OS file locks under the temporary directory), entered when one
    is free and memory allows: pegasus_data's decode admission (`pegasus_data.decode.admission.admitted`) on its own
    slot directory, so job slots and decode slots are separate pools. The environment it reads is restored as soon as
    the slot is held, so this process's own decodes keep their pool (`jobs.slot`)."""
    import tempfile

    from pegasus_data.decode.admission import admitted

    names = ("PEGASUS_DECODE_SLOT_DIR", "PEGASUS_DECODE_SLOTS", "PEGASUS_MIN_FREE_GB", "PEGASUS_ADMISSION_WAIT")
    saved = {k: os.environ.get(k) for k in names}
    os.environ.update(PEGASUS_DECODE_SLOT_DIR=os.path.join(tempfile.gettempdir(), pool), PEGASUS_DECODE_SLOTS=str(slots),
                      PEGASUS_MIN_FREE_GB=os.environ.get("PEGASUS_HEAVY_MIN_FREE_GB", "4"),
                      PEGASUS_ADMISSION_WAIT=os.environ.get("PEGASUS_HEAVY_WAIT", "86400"))
    held = admitted(label)
    try:
        held.__enter__()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    try:
        yield
    finally:
        held.__exit__(None, None, None)


def facility_column(dataset: str) -> tuple[str, str | None]:
    """(facility column, the facility's own municipality column or None) from pegasus_data's roles."""
    rs = roles(dataset)
    fac = [r for r in rs if r.get("model") == "institution" and r.get("property") == "facility"]
    if not fac:
        raise LookupError(f"{dataset}: no facility among its institution roles")
    where = [r for r in rs if r.get("model") == "where" and r.get("property") in ("facility_municipality", "municipality")]
    return fac[0]["column"], where[0]["column"] if where else None
