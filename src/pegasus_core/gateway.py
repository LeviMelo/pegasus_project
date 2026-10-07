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
import pandas as pd
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


ACCOUNT = ("population_account", "population-account-2")   # the modelled product and its pinned version
TENSOR = {"account-3": ("population-account-3", 2000, 2023), "account-4": ("population-account-4", 2000, 2030),
          "account-6": ("population-account-6", 1991, 2030)}   # source: version, years held
POPSVS_EDGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]   # 18 bands, 80+ closes
ACCOUNT_EDGES = list(range(0, 81, 5))   # 17 bands: the account's 0-4 holds ages 0 and 1-4, which POPSVS keeps apart
POPSVS_PLACES = 5570
_Z80 = 1.2815515655446004    # the 80% interval's half-width in standard deviations


#: Exposure modifiers (ARCHITECTURE §4.1, ADR-0020): ``<base>+kappa`` multiplies N by the system's completeness κ_{UF,t},
#: ``<base>+sus`` by the share of the population without private coverage; the source string carries them.
MODIFIERS = {"kappa": ("system_completeness", "system-completeness-2"), "sus": ("population_without_private_coverage", "sus-dependent-2"),
             "confusion": ("race_confusion_infant", "race-confusion-infant-1")}
RACE = {"1": "branca", "2": "preta", "3": "amarela", "4": "parda", "5": "indigena"}   # RACACOR code -> the account's race
RACE_COLUMN = {"SINASC-DN": "RACACORMAE", "SIM.DO": "RACACOR"}    # the mother's declared race; the race recorded on the certificate
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


def age_edges(source: str | None = None) -> list[int]:
    """The lower edges of the age bands a population source supports (the last band is open)."""
    # account-3/4 hold single ages and are summed onto POPSVS's 18 bands
    return list(ACCOUNT_EDGES if split_source(source or config.population_source())[0] in ("account-2", "popsvs-5y") else POPSVS_EDGES)


def population_key(source: str | None = None) -> dict:
    """What an artefact built on a population adds to its key. POPSVS adds nothing (its keys predate the
    switch and the data version already names the series); the account adds its source and model version;
    modifiers add the string and their models' versions."""
    source = source or config.population_source()
    base, mods = split_source(source)
    model = ACCOUNT[1] if base == "account-2" else TENSOR[base][0] if base in TENSOR else TENSOR["account-6"][0] if base == "hybrid" else None
    models = ([] if model is None else [model]) + [MODIFIERS[m][1] for m in mods]
    return {} if source == "popsvs" else {"population": source, **({"population_model": "+".join(models)} if models else {})}


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
    if source != "popsvs":
        raise KeyError(f"unknown population source {source!r}: popsvs, account-3, account-4, account-6, hybrid or account-2 (popsvs-5y: a control)")
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
    key = {"what": "exposure", "version": 3, "base": base, "mods": list(mods), "dataset": dataset, "years": years,
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


def _confusion() -> pd.DataFrame:
    """The infant confusion matrix C(recorded k | declared j) by UF and age band at death, with the posterior's relative sd of p
    (pegasus_data ``race_confusion_infant``; the intervals are 5-95 %)."""
    raw = _modelled("confusion").to_pandas()
    code = {"Branca": "1", "Preta": "2", "Amarela": "3", "Parda": "4", "Indígena": "5"}
    raw = raw[raw.declared.isin(code) & raw.recorded.isin(code)].copy()
    raw["j"], raw["k"] = raw.declared.map(code), raw.recorded.map(code)
    raw["rel"] = (raw.p_hi - raw.p_lo) / (2 * 1.6449) / raw.p.clip(lower=1e-9)
    return raw[["uf", "age_band", "j", "k", "p", "rel"]]


def _infant_age_mix() -> np.ndarray:
    """The share of the perinatal deaths (SIM chapter P, ages under 1) in the matrix's three age bands (0-6 d, 7-27 d,
    28-364 d) over the years the matrix was measured on, from the certificate's IDADE (unit digit then value)."""
    key = {"what": "infant_age_mix", "years": list(CONFUSION_YEARS), "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is None:
        import pegasus_data as pg

        tot = np.zeros(3)
        for y in CONFUSION_YEARS:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = pg.count_events("SIM.DO", "death", period=y, geography="BR", by=["CAUSABAS", "IDADE"],
                                      root=config.data_root(), allow_partial=False, max_download=8 * 1024**3)
            con = duckdb.connect()
            con.register("r", raw)
            for band, n in con.execute("""
                WITH x AS (SELECT lpad(CAST("IDADE" AS VARCHAR), 3, '0') AS a, events FROM r WHERE upper("CAUSABAS") LIKE 'P%')
                SELECT CASE WHEN left(a, 1) IN ('0', '1') THEN 0 WHEN left(a, 1) = '2' THEN
                       (CASE WHEN TRY_CAST(substr(a, 2) AS INTEGER) <= 6 THEN 0 WHEN TRY_CAST(substr(a, 2) AS INTEGER) <= 27 THEN 1 ELSE 2 END)
                       WHEN left(a, 1) = '3' THEN 2 END AS band, sum(events) FROM x GROUP BY 1""").fetchall():
                if band is not None:
                    tot[band] += n
        cached = pa.table({"band": [0, 1, 2], "share": list(tot / tot.sum())})
        store.put_table("gateway", key, cached)
    return np.asarray(cached.column("share").to_pylist())


def _confusion_mixed() -> pd.DataFrame:
    """C(k|j) by UF, the three age bands averaged with the perinatal deaths' age mixture (``_infant_age_mix``); ``rel`` the
    relative sd of the mixed p (the bands' errors taken as shared: the weighted mean)."""
    c, mix = _confusion(), _infant_age_mix()
    c["w"] = c.age_band.map({"0-6 d": mix[0], "7-27 d": mix[1], "28-364 d": mix[2]})
    c["pw"], c["rw"] = c.p * c.w, c.rel * c.p * c.w
    g = c.groupby(["uf", "j", "k"], as_index=False)[["pw", "rw"]].sum()
    return g.assign(p=g.pw, rel=g.rw / g.pw.clip(lower=1e-12))[["uf", "j", "k", "p", "rel"]]


def declared_ratios(base: str = "account-3") -> dict[str, float]:
    """Rate ratios of the infant deaths by *declared* race, Branca = 1, the infant matrix inverted on the national
    UF × year totals: the recorded deaths of race k in UF f year t are Poisson with mean
    rate_{f,t} · Σ_j C(k|j,f) r_j N_{j,f,t,age 0} (the rate profiled out, r_j by maximum likelihood over ``RATIO_YEARS``,
    a N(0, 2²) prior on the log ratios). Five numbers from about 1,350 UF-year-race counts; the exposure of a
    recorded-race group uses them (ARCHITECTURE §4.1)."""
    from scipy.optimize import minimize

    key = {"what": "declared_ratios", "base": base, "years": RATIO_YEARS, "confusion": MODIFIERS["confusion"][1], "data": config.data_version(), "v": 1}
    cached = store.get_table("gateway", key)
    if cached is None:
        c = _confusion_mixed()
        ufs = sorted(c.uf.unique())
        D = np.zeros((len(ufs), len(RATIO_YEARS), 5))
        for yi, y in enumerate(RATIO_YEARS):
            for ki, k in enumerate(RACE):
                t = event_counts("SIM.DO", "death", y, race=k).counts
                con = duckdb.connect()
                con.register("t", t)
                for uf, n in con.execute("SELECT u // 10000, sum(y) FROM t WHERE age = 0 GROUP BY 1").fetchall():
                    D[ufs.index(uf), yi, ki] = n
        Nj = np.zeros((len(ufs), len(RATIO_YEARS), 5))
        for ji, j in enumerate(RACE):
            con = duckdb.connect()
            con.register("n", _tensor_population(RATIO_YEARS, base, RACE[j]))
            for uf, yr, n in con.execute("SELECT u // 10000, year, sum(n) FROM n WHERE age = 0 GROUP BY 1, 2").fetchall():
                Nj[ufs.index(uf), RATIO_YEARS.index(yr), ji] = n
        Cm = np.zeros((len(ufs), 5, 5))      # [uf, j, k]
        for r in c.itertuples():
            Cm[ufs.index(r.uf), int(r.j) - 1, int(r.k) - 1] = r.p
        M = np.einsum("fjk,fyj->fykj", Cm, Nj)            # [f, y, k, j]

        def nll(rho: np.ndarray) -> float:
            lam = np.exp(np.concatenate([[0.0], rho]))
            base_mean = M @ lam                                           # [f, y, k]
            rate = D.sum(2) / np.maximum(base_mean.sum(2), 1e-9)          # profiled
            mean = np.maximum(rate[:, :, None] * base_mean, 1e-9)
            return float((mean - D * np.log(mean)).sum() + 0.5 * (rho ** 2).sum() / 4.0)

        fit = minimize(nll, np.zeros(4), method="L-BFGS-B")
        cached = pa.table({"race": list(RACE), "ratio": [1.0, *np.exp(fit.x).tolist()]})
        store.put_table("gateway", key, cached, {"converged": bool(fit.success), "nll": float(fit.fun)})
    return dict(zip(cached.column("race").to_pylist(), cached.column("ratio").to_pylist(), strict=True))


def _recorded_exposure(years: list[int], base: str, k: str) -> pa.Table:
    """The exposure to being *recorded* as race ``k`` on an infant death certificate (ARCHITECTURE §4.1, groups with race):
    at age 0, N^{rec}_k = Σ_j C(k|j, UF) · r_j · N_j with C the infant confusion matrix averaged over the perinatal deaths'
    age mixture, r_j the declared-race rate ratios (``declared_ratios``) and N_j the account's race-j population, so that
    the expectation of the recorded count is μ^{rec}_k = Σ_j C(k|j) μ_j when the declared races share one shape and differ
    by the ratios. From age 1 the matrix is not measured and the recorded race is the declared one (N_k). ``s`` is the
    quadrature of the races' own sd and the matrix's relative sd (independent cells)."""
    key = {"what": "recorded_exposure", "base": base, "race": k, "years": years, "confusion": MODIFIERS["confusion"][1],
           "data": config.data_version(), "v": 1}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    r, c = declared_ratios(base), _confusion_mixed()
    c = c[c.k == k].copy()
    c["r"] = c.j.map(r)
    con = duckdb.connect()
    con.register("c", pa.Table.from_pandas(c[["uf", "j", "p", "rel", "r"]], preserve_index=False))
    union = " UNION ALL ".join(f"SELECT '{j}' AS j, * FROM n{j}" for j in RACE)
    for j in RACE:
        con.register(f"n{j}", _tensor_population(years, base, RACE[j]))
    con.register("own", _tensor_population(years, base, RACE[k]))
    table = con.execute(f"""
        WITH n AS ({union}),
        z AS (SELECT n.u, n.year, n.sex, n.age, sum(c.p * c.r * n.n) AS m,
                     sqrt(sum(power(c.p * c.r * n.n, 2) * (power(n.s, 2) + power(c.rel, 2)))) AS sd
              FROM n JOIN c ON c.uf = n.u // 10000 AND c.j = n.j WHERE n.age = 0 GROUP BY ALL)
        SELECT CAST(u AS INTEGER) AS u, CAST(year AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex, CAST(age AS SMALLINT) AS age,
               CAST(m AS DOUBLE) AS n, CAST(CASE WHEN m > 0 THEN sd / m ELSE 0.0 END AS DOUBLE) AS s FROM z
        UNION ALL
        SELECT u, year, sex, age, n, s FROM own WHERE age > 0
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
                 places: pa.Array | None = None, survivors_only: bool = False, race: str | None = None) -> EventCounts:
    """One event type's counts for one year, by residence × sex × age × the classifier's code.

    The columns come from pegasus_data's roles (the subject's residence, sex and age as
    strata). ``classifier`` defaults to the event type's primary classifier; an event type
    without one (births, a notifiable disease) has the single code ``*``. A subject without a
    sex stratum takes the sex its entity implies (a mother: 2), or fails. ``places`` is the
    set of valid municipalities (the population's); a residence outside it is unallocated,
    never guessed. ``survivors_only`` (SIH): the admissions that did not end in death (MORTE = 0); the in-hospital
    deaths are SIM records (ARCHITECTURE §8.5), so these share no event with a SIM field.
    ``race`` (a RACACOR code 1-5): only the events of that race, by the mother's declaration (SINASC-DN) or as recorded on
    the certificate (SIM.DO); events with no valid race are unallocated ('race unknown').
    """
    import pegasus_data as pg

    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
    column = classifier or (primary[0] if primary else None)
    strata = _strata(dataset)
    key = {"what": "event_counts", **_places_key(places, year), "dataset": dataset, "event": event, "year": year, "classifier": column,
           "data": config.data_version(), "gateway": 3 if dataset != "SIM.DO" else 1,
           **_df_key(dataset, year), **({"survivors": 1} if survivors_only else {}), **({"race": race} if race else {})}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    by = [strata["residence"], strata["age"]] + ([strata["sex"]] if strata["sex"] else []) + ([column] if column else [])
    if race:
        by = by + [RACE_COLUMN[dataset]]
    alive = ""
    if survivors_only:
        if not dataset.startswith("SIH"):
            raise ValueError("survivors_only is the SIH admissions that did not end in death")
        by = by + ["MORTE"]
        alive = "WHERE coalesce(TRY_CAST(CAST(\"MORTE\" AS VARCHAR) AS INTEGER), 0) = 0"
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
    race_col = f', TRY_CAST(CAST("{RACE_COLUMN[dataset]}" AS VARCHAR) AS INTEGER) AS race' if race else ""
    race_bad = "WHEN race IS NULL OR race NOT BETWEEN 1 AND 5 THEN 'race unknown'" if race else ""
    race_mine = f" AND (race = {int(race)} OR race IS NULL OR race NOT BETWEEN 1 AND 5)" if race else ""
    con.execute(f"""CREATE TEMP TABLE e AS SELECT
            {_residence_sql(strata['residence'])} AS u,
            {sex} AS sex,
            CAST(least(floor(TRY_CAST("{strata['age']}" AS DOUBLE)), {MAX_AGE}) AS SMALLINT) AS age,
            {code} AS code, CAST(events AS INTEGER) AS y{race_col}
        FROM r {alive}""")
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age' {race_bad}
                     WHEN code IS NULL OR code = '' THEN 'code' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year, CAST(sex AS TINYINT) AS sex,
            age, code, CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NULL{" AND race = " + str(int(race)) if race else ""}
            GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(sum(y) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL{race_mine} GROUP BY ALL""").fetch_arrow_table()
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
                   places: pa.Array | None = None, code_list: bool = False) -> EventCounts:
    """Events of one publication year by (u, year, month of the event's date, sex, age, code).
    The month and year come from the event's date (`_when`), so a file's events may fall in the
    year before it (onset in December, notified in January); a missing or unparsable date is
    unallocated with that reason. ``code_list``: the classifier column holds several codes
    concatenated (SINASC's CODANOMAL, "Q02Q690"); an event counts once under each distinct
    category it carries (as `code_list_counts`), and events carrying none are not counted."""
    strata = _strata(dataset)
    spec_class = classifier
    if spec_class is None:
        import pegasus_data as pg

        spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
        primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
        spec_class = primary[0] if primary else None
    when = _when(dataset)
    key = {"what": "monthly_counts", **_places_key(places, year), "dataset": dataset, "event": event, "year": year, "classifier": spec_class,
           "when": when, "data": config.data_version(), "dates": 3, **_df_key(dataset, year),
           **({"code_list": True} if code_list else {})}
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
    # a system of one sex is legitimate when its labels say so (HIV in pregnancy, SINAN HIVG, records only women);
    # what fails is a column no code of which is labelled either sex
    if not any(v in (1, 2) for v in out.values()):
        raise LookupError(f"{dataset}.{column}: pegasus_data labels no male or female code among {codes} "
                          f"(system {system}): {labelled}")
    return out


def _cells_sql(strata: dict, dataset: str, table: pa.Table) -> str:
    return (f'{_residence_sql(strata["residence"])} AS u, '
            f'{_sex_sql(strata, dataset, table)} AS sex, '
            f'CAST(least(floor(TRY_CAST(CAST("{strata["age"]}" AS VARCHAR) AS DOUBLE)), {MAX_AGE}) AS SMALLINT) AS age')


MARK_SHRINK = 10.0   # events: a (diagnosis, procedure group) stratum's case-mix offset is its mean log departure times n/(n + this)
CASEMIX_CHARS = 2    # the procedure's group: the first two digits of a SIGTAP code


def _mark_frame(con, dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float], classifier: str | None,
                places: pa.Array | None, casemix: str | None, facility_effects: str | None, facility: bool = False) -> pa.Table:
    """Registers in ``con`` the table ``adj`` of a year's admissions with a valid mark: (u, sex, age, code, fac, m, lm), ``lm`` the
    log mark less the facility's effect (``facility_effects``: a stored table, `store_facility_effects`) and less the case-mix
    offset of its (diagnosis category, procedure group) stratum when ``casemix`` names the procedure column: the stratum's
    mean log mark above its category's, shrunk by n/(n + MARK_SHRINK). Returns the unallocated (year, reason, code, y)."""
    from .facility import facility_column  # the facility module reads this one: imported where used

    strata = _strata(dataset)
    fcol = facility_column(dataset)[0] if (facility_effects or facility) else None
    cols = [strata["residence"], strata["age"], mark] + ([strata["sex"]] if strata["sex"] else []) + \
        ([classifier] if classifier else []) + ([casemix] if casemix else []) + ([fcol] if fcol else [])
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)))
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    pg = f"coalesce(left(trim(CAST(\"{casemix}\" AS VARCHAR)), {CASEMIX_CHARS}), '')" if casemix else "''"
    fac = f"coalesce(trim(CAST(\"{fcol}\" AS VARCHAR)), '')" if fcol else "''"
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            TRY_CAST(CAST("{mark}" AS VARCHAR) AS DOUBLE) AS m, {pg} AS pg, {fac} AS fac FROM r""")
    con.unregister("r")
    del raw
    reason = f"""CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                      WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                      WHEN code IS NULL OR code = '' THEN 'code' WHEN m IS NULL THEN 'mark missing'
                      WHEN m < {bounds[0]} OR m > {bounds[1]} THEN 'mark out of bounds' END"""
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(count(*) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    if facility_effects:
        fx = store.get_table("gateway", {"what": "mark_facility_effects", "id": facility_effects})
        if fx is None:
            raise LookupError(f"no stored facility effects {facility_effects}")
        con.register("fx", fx)
        con.execute(f"""CREATE TEMP TABLE a AS SELECT u, sex, age, code, pg, fac, m, ln(m) - coalesce(fx.delta, 0) AS lm
                        FROM e LEFT JOIN fx ON fx.facility = e.fac WHERE ({reason}) IS NULL""")
    else:
        con.execute(f"CREATE TEMP TABLE a AS SELECT u, sex, age, code, pg, fac, m, ln(m) AS lm FROM e WHERE ({reason}) IS NULL")
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


def mark_moments(dataset: str, event: str, year: int, mark: str, bounds: tuple[float, float],
                 classifier: str | None = None, places: pa.Array | None = None, casemix: str | None = None,
                 facility_effects: str | None = None) -> EventCounts:
    """Accumulator states of a positive numeric mark per (u, year, sex, age, code): n, Σm, Σm², Σlog m, Σ(log m)²
    (ARCHITECTURE §4.4; handoff §4 asks pegasus_data to serve these). The log moments are of the *adjusted* log mark
    when ``casemix`` (the procedure column) or ``facility_effects`` are given (`_mark_frame`); Σm and Σm² are raw.
    Values outside ``bounds`` (sentinels, impossible values) and missing values are counted
    as unallocated with their reason, never dropped silently."""
    key = {"what": "mark_moments", **_places_key(places, year), "dataset": dataset, "event": event, "year": year, "mark": mark,
           "bounds": list(bounds), "classifier": classifier, "data": config.data_version(), **_df_key(dataset, year),
           **({"casemix": casemix, "shrink": MARK_SHRINK, "chars": CASEMIX_CHARS} if casemix else {}),
           **({"facility_effects": facility_effects} if facility_effects else {})}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    con = duckdb.connect()
    unallocated = _mark_frame(con, dataset, event, year, mark, bounds, classifier, places, casemix, facility_effects)
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(count(*) AS INTEGER) AS n, sum(m) AS s1,
            sum(m * m) AS s2, sum(lm) AS l1, sum(lm * lm) AS l2
        FROM adj GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): moments of {mark}"})
    store.put_table("gateway", {**key, "part": "unallocated"}, unallocated)
    return EventCounts(counts, unallocated, key)


def share_moments(dataset: str, event: str, year: int, indicator: str, success: tuple[str, ...], classifier: str | None = None,
                  places: pa.Array | None = None) -> EventCounts:
    """A binary mark's states per (u, year, sex, age, code): n admissions and k of them with ``indicator`` among the ``success``
    codes (SIH ``MORTE`` = 1: died in hospital). A record whose value is missing is unallocated with its reason."""
    strata = _strata(dataset)
    key = {"what": "share_moments", **_places_key(places, year), "dataset": dataset, "event": event, "year": year,
           "indicator": indicator, "success": list(success), "classifier": classifier, "data": config.data_version(),
           **_df_key(dataset, year)}
    cached = store.get_table("gateway", key)
    cached_un = store.get_table("gateway", {**key, "part": "unallocated"})
    if cached is not None and cached_un is not None:
        return EventCounts(cached, cached_un, key)
    cols = [strata["residence"], strata["age"], indicator] + ([strata["sex"]] if strata["sex"] else []) + \
        ([classifier] if classifier else [])
    con = duckdb.connect()
    raw = _records(dataset, event, year, list(dict.fromkeys(cols)))
    con.register("r", raw)
    valid = places if places is not None else population([year]).column("u").unique()
    con.register("v", pa.table({"u": valid}))
    code = f'upper(trim(CAST("{classifier}" AS VARCHAR)))' if classifier else "'*'"
    yes = ", ".join(f"'{s}'" for s in success)
    con.execute(f"""CREATE TEMP TABLE e AS SELECT {_cells_sql(strata, dataset, raw)}, {code} AS code,
            trim(CAST("{indicator}" AS VARCHAR)) AS x FROM r""")
    reason = """CASE WHEN u IS NULL OR u NOT IN (SELECT u FROM v) THEN 'municipality'
                     WHEN sex IS NULL THEN 'sex' WHEN age IS NULL OR age < 0 THEN 'age'
                     WHEN code IS NULL OR code = '' THEN 'code' WHEN x IS NULL OR x = '' THEN 'value missing' END"""
    counts = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, CAST({year} AS SMALLINT) AS year,
            CAST(sex AS TINYINT) AS sex, age, code, CAST(count(*) AS INTEGER) AS n,
            CAST(sum(CASE WHEN x IN ({yes}) THEN 1 ELSE 0 END) AS INTEGER) AS k
        FROM e WHERE ({reason}) IS NULL GROUP BY ALL ORDER BY code, u, sex, age""").fetch_arrow_table()
    unallocated = con.execute(f"""SELECT CAST({year} AS SMALLINT) AS year, {reason} AS reason, code,
            CAST(count(*) AS INTEGER) AS y FROM e WHERE ({reason}) IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, counts, {"source": f"pegasus_data.query({dataset}): share of {indicator} in {list(success)}"})
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
                          facility_effects: str | None = None, places: pa.Array | None = None) -> pa.Table:
    """A year's residuals of the admissions' adjusted log mark from a fitted location, summed by recording facility:
    (facility, year, n, sr, sr2) with r = lm − ν, ν looked up by (category, residence, sex, age band) in ``nu``
    (columns code3, u, sex, band, nu), the fitted model's cells. Admissions in a cell the fit has none of are left out."""
    import hashlib

    digest = hashlib.sha256(np.ascontiguousarray(nu.column("nu").to_numpy()).tobytes()
                            + np.ascontiguousarray(nu.column("u").to_numpy()).tobytes()).hexdigest()[:16]
    key = {"what": "mark_facility_moments", **_places_key(places, year), "dataset": dataset, "event": event, "year": year,
           "mark": mark, "bounds": list(bounds), "classifier": classifier, "casemix": casemix, "shrink": MARK_SHRINK,
           "facility_effects": facility_effects, "nu": digest, "edges": list(edges), "data": config.data_version(), "v": 1,
           **_df_key(dataset, year)}
    hit = store.get_table("gateway", key)
    if hit is not None:
        return hit
    con = duckdb.connect()
    _mark_frame(con, dataset, event, year, mark, bounds, classifier, places, casemix, facility_effects, facility=True)
    con.register("nu", nu)
    con.register("ab", pa.table({"age": pa.array(range(MAX_AGE + 1), pa.int16()),
                                 "band": pa.array([int(np.searchsorted(edges, a, side="right") - 1) for a in range(MAX_AGE + 1)],
                                                  pa.int16())}))
    out = con.execute(f"""SELECT fac AS facility, CAST({year} AS SMALLINT) AS year, CAST(count(*) AS INTEGER) AS n,
            sum(r) AS sr, sum(r * r) AS sr2
        FROM (SELECT adj.fac, adj.lm - nu.nu AS r FROM adj JOIN ab ON ab.age = adj.age
              JOIN nu ON nu.code3 = left(adj.code, 3) AND nu.u = adj.u AND nu.sex = adj.sex AND nu.band = ab.band)
        GROUP BY fac""").fetch_arrow_table()
    store.put_table("gateway", key, out, {"source": f"residuals of {mark} by facility"})
    return out


def code_list_counts(dataset: str, event: str, year: int, column: str,
                     places: pa.Array | None = None) -> EventCounts:
    """Events per (u, year, sex, age, ICD category) for a column that holds several codes
    concatenated (SINASC's CODANOMAL: "Q02Q690"): an event counts once under each distinct
    category it carries. Events carrying none are the complement, not counted here."""
    strata = _strata(dataset)
    key = {"what": "code_list_counts", **_places_key(places, year), "dataset": dataset, "event": event, "year": year, "column": column,
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


def strata(dataset: str) -> dict:
    """The subject's residence, sex and age columns, their entity, and the sex implied when the strata are another
    person's (SINASC: the mother's), from pegasus_data's roles."""
    return _strata(dataset)


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


def indicator_counts(dataset: str, event: str, year: int, indicators: dict[str, str], places: pa.Array
                     ) -> tuple[pa.Table, dict[tuple[str, str], int]]:
    """Events of a year that satisfy each named SQL predicate over the raw columns (SINASC: weight < 2500 g, a
    caesarean), per residence: a table (u, name, y) with the name '*' for all events, and the records satisfying
    both predicates of every pair (the measured overlap, §8.5). Predicates are written over the columns as
    TRY_CAST numbers (``PESO``, ``SEMAGESTAC``) or text; an event with a null predicate is not counted for it."""
    import re

    strata = _strata(dataset)
    cols = sorted({c for sql in indicators.values() for c in re.findall(r"[A-Z][A-Z0-9_]{2,}", sql)} | {strata["residence"]})
    key = {"what": "indicator_counts", **_places_key(places, year), "dataset": dataset, "event": event, "year": year,
           "indicators": indicators, "data": config.data_version()}
    cached = store.get_table("gateway", key)
    if cached is not None:
        meta = store.manifest("gateway", key) or {}
        return cached, {tuple(k.split("|")): v for k, v in meta.get("overlap", {}).items()}
    raw = _records(dataset, event, year, cols)
    con = duckdb.connect()
    con.register("r", raw)
    con.register("v", pa.table({"u": places}))
    num = {c: f'TRY_CAST(CAST("{c}" AS VARCHAR) AS DOUBLE)' for c in cols}
    exprs = {n: re.sub(r"[A-Z][A-Z0-9_]{2,}", lambda m: num[m.group(0)], sql) for n, sql in indicators.items()}
    sel = ", ".join(f"coalesce(({e}), false) AS \"i_{n}\"" for n, e in exprs.items())
    con.execute(f"CREATE TEMP TABLE e AS SELECT {_residence_sql(strata['residence'])} AS u, {sel} FROM r")
    parts = ["SELECT u, '*' AS name, count(*) AS y FROM e GROUP BY u"] + [
        f"SELECT u, '{n}' AS name, count(*) AS y FROM e WHERE \"i_{n}\" GROUP BY u" for n in indicators]
    table = con.execute(f"""SELECT CAST(u AS INTEGER) AS u, name, CAST(sum(y) AS INTEGER) AS y
                            FROM ({' UNION ALL '.join(parts)}) WHERE u IN (SELECT u FROM v) GROUP BY ALL
                            ORDER BY name, u""").fetch_arrow_table()
    names = list(indicators)
    overlap = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            overlap[(a, b)] = int(con.execute(f'SELECT count(*) FROM e WHERE "i_{a}" AND "i_{b}"').fetchone()[0])
    store.put_table("gateway", key, table, {"overlap": {"|".join(k): v for k, v in overlap.items()}})
    return table, overlap


# ---------------------------------------------------------------------- pass-throughs (the door for modules that need pegasus_data itself)


def package_version() -> str:
    """pegasus_data's package version."""
    import pegasus_data

    return str(pegasus_data.__version__)


def package_dir():
    """The directory of the pegasus_data package (its shipped resources, its repository)."""
    from pathlib import Path

    import pegasus_data

    return Path(pegasus_data.__file__).resolve().parent


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
    import pegasus_data as pg

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pg.count_events(dataset, event, period=year, geography="BR", by=by, root=config.data_root(),
                               allow_partial=False, max_download=8 * 1024**3)


def raw_field(name: str, years: list[int]):
    """``load_field`` of a context field in PegaSUS's data root, as pegasus_data serves it."""
    import pegasus_data as pg

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pg.load_field(name, years=years, settings=pg.load_settings(root=config.data_root()))



def delay_counts(dataset: str, event: str, year: int, report: str, onset: str | None = None) -> pa.Table:
    """The reporting delay of one publication year (phase 4, ADR-0004): events by residence ``u``, the epidemiological
    week of their onset (``onset``; default the event's date, `_when`) and the whole weeks between it and the
    ``report`` date (SINAN's data entry, DT_DIGITA; SIH's processing month; SIM's registration). Rows with either
    date missing or a negative delay are left out and counted in the table's metadata. Columns: u, year, week,
    delay, n."""
    from . import surveillance

    when = onset or _when(dataset)
    key = {"what": "delay_counts", "dataset": dataset, "event": event, "year": year, "onset": when, "report": report,
           "data": config.data_version(), **_df_key(dataset, year)}
    cached = store.get_table("gateway", key)
    if cached is not None:
        return cached
    strata = _strata(dataset)
    raw = _records(dataset, event, year, [strata["residence"], when, report])
    con = duckdb.connect()
    con.register("r", raw)
    t = con.execute(f"""SELECT {_residence_sql(strata["residence"])} AS u, {_date_sql(when)} AS d0,
                        {_date_sql(report)} AS d1 FROM r""").fetch_arrow_table()
    d0 = t.column("d0").to_numpy(zero_copy_only=False).astype("datetime64[D]")
    d1 = t.column("d1").to_numpy(zero_copy_only=False).astype("datetime64[D]")
    u = t.column("u").to_numpy(zero_copy_only=False)
    ok = ~np.isnat(d0) & ~np.isnat(d1) & (d1 >= d0) & np.isfinite(u.astype(float))
    ey, ew = surveillance.epi_week(d0[ok])
    delay = ((d1[ok] - d0[ok]).astype(np.int64) // 7).astype(np.int64)
    df = pd.DataFrame({"u": u[ok].astype(np.int64), "year": ey, "week": ew, "delay": delay})
    out = pa.Table.from_pandas(df.groupby(["u", "year", "week", "delay"]).size().rename("n").reset_index(),
                               preserve_index=False)
    store.put_table("gateway", key, out, {**key, "left_out": int((~ok).sum()), "records": int(len(ok))})
    return out
