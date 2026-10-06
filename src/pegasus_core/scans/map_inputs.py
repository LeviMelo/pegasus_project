"""The fields of a dependency map: place effects of SIM and SIH chapters, SINASC indicators and context fields.

Every health field is a count over the window, indirectly standardised on the national rates (SIM, SIH: by year × sex ×
five-year age band; SINASC: the national share of births), its place effect b̂(u) the shrunk Poisson intercept of
``surprise.refit_place`` over that expectation, with its posterior sd (the pair weight is 1/sd², §7.5). SIH is the
admissions that did not end in death: the in-hospital deaths are SIM records (§8.5), so no SIM and SIH field shares an
event. A context is a complete count or a rate over a registered denominator, z-scored, with the constant sd 0.05 the
gate used (it cannot change ρ). A field whose power to see a shared latent of correlation 0.3 is below 0.5 (§8.4, ADR-0022) is left out and reported.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pyarrow as pa

from .. import gateway, surprise
from . import pairs
from .maps import MapInputs

CONTEXT_SD = 0.05
YEARS = list(range(2015, 2020))
SINASC = {"lbw": "PESO > 0 and PESO < 2500", "preterm": "SEMAGESTAC > 0 and SEMAGESTAC < 37", "cesarean": "PARTO = 2",
          "teen_mother": "IDADEMAE < 20", "prenatal_lt7": "CONSULTAS >= 1 and CONSULTAS <= 3",
          "twin": "GRAVIDEZ >= 2 and GRAVIDEZ <= 3", "apgar5_lt7": "APGAR5 < 7"}
SINASC_LABEL = {"lbw": "birth weight < 2,500 g", "preterm": "gestation < 37 weeks", "cesarean": "caesarean delivery",
                "teen_mother": "mother under 20", "prenatal_lt7": "fewer than 7 prenatal visits",
                "twin": "multiple pregnancy", "apgar5_lt7": "Apgar at 5 minutes < 7"}
POWER_REPS = 30        # planted-latent replicates behind a field's admission power (Monte-Carlo se of the power 0.09)


def _population(places: np.ndarray, years: list[int]) -> np.ndarray:
    """[U, T, 2, 17]: persons by place, year, sex, five-year band (POPSVS)."""
    ix = {int(u): i for i, u in enumerate(places)}
    out = np.zeros((len(places), len(years), 2, 17))
    t = gateway.population(years)
    for u, yr, s, a, n in zip(*(t.column(c).to_numpy() for c in ("u", "year", "sex", "age", "n")), strict=True):
        if int(u) in ix and int(s) in (1, 2):
            out[ix[int(u)], years.index(int(yr)), int(s) - 1, min(int(a) // 5, 16)] += n
    return out


def _chapter_map() -> pa.Table:
    tree = gateway.code_structure("ICD10")
    codes = tree.column("code").to_pylist()
    parent = dict(zip(codes, tree.column("parent").to_pylist(), strict=True))
    level = dict(zip(codes, tree.column("level").to_pylist(), strict=True))
    rows = []
    for c in codes:
        if level[c] != "category":
            continue
        x = c
        while parent.get(x) is not None:
            x = parent[x]
        rows.append((c, x))
    return pa.table({"code3": [r[0] for r in rows], "chapter": [r[1] for r in rows]})


def _chapter_counts(system: tuple[str, str], places: np.ndarray, years: list[int], survivors: bool) -> dict[str, np.ndarray]:
    """Events by chapter as [U, T, 2, 17]."""
    ix = {int(u): i for i, u in enumerate(places)}
    chapters = _chapter_map()
    out: dict[str, np.ndarray] = {}
    for k, year in enumerate(years):
        kw = {"survivors_only": True} if survivors else {}
        ec = gateway.event_counts(*system, year, places=pa.array(places.astype(np.int64)), **kw)
        con = duckdb.connect()
        con.register("c", ec.counts)
        con.register("m", chapters)
        rows = con.execute("""SELECT m.chapter, c.u, c.sex, least(c.age // 5, 16) AS band, sum(c.y)
                              FROM c JOIN m ON left(c.code, 3) = m.code3 WHERE c.sex IN (1, 2) GROUP BY ALL""").fetchall()
        for ch, u, s, a, v in rows:
            if u in ix:
                out.setdefault(ch, np.zeros((len(places), len(years), 2, 17)))[ix[u], k, s - 1, a] += v
    return out


def place_effect(y: np.ndarray, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """The shrunk Poisson place intercept over the expectation (B0 for E_b) and its posterior sd."""
    _, b, sd, tau = surprise.refit_place(y[:, None], mu[:, None], np.full((len(y), 1), np.inf), np.ones((1, 1)))
    return b[:, 0], sd[:, 0], float(tau[0])


def _standardised(Y: np.ndarray, PA: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Observed and indirectly standardised expected events per place (national sex × band rates by year)."""
    rate = Y.sum(0) / np.maximum(PA.sum(0), 1e-9)
    return Y.sum((1, 2, 3)), (PA * rate[None]).sum((1, 2, 3))


def _field(places: np.ndarray, rows) -> np.ndarray:
    out = np.full(len(places), np.nan)
    ix = {int(u): i for i, u in enumerate(places)}
    for u, v in rows:
        if int(u) in ix:
            out[ix[int(u)]] = v
    return out


def _census(name: str, year: int, places: np.ndarray) -> np.ndarray:
    t = gateway.context_field(name, years=[year])
    ok = [s in ("value", "zero", "ok") for s in t.column("status").to_pylist()]
    u, v = t.column("u").to_numpy(), t.column("value").to_numpy()
    return _field(places, [(a, b) for a, b, o in zip(u, v, ok, strict=True) if o])


def _stock_rate(name: str, years: list[int], places: np.ndarray, pop: np.ndarray, per: float = 1000.0) -> np.ndarray:
    """Mean over the years of a CNES December stock per ``per`` persons (POPSVS of the year)."""
    t = gateway.context_field(name, years=years)
    ix = {int(u): i for i, u in enumerate(places)}
    stock = np.full((len(places), len(years)), np.nan)
    for u, yr, v, st in zip(t.column("u").to_numpy(), t.column("year").to_numpy(), t.column("value").to_numpy(),
                            t.column("status").to_pylist(), strict=True):
        if int(u) in ix and st == "ok":
            stock[ix[int(u)], years.index(int(yr))] = v
    with np.errstate(all="ignore"):
        return np.nanmean(np.where(pop > 0, stock / pop * per, np.nan), axis=1)


def contexts(places: np.ndarray, years: list[int]) -> dict[str, tuple[np.ndarray, str]]:
    """The context fields as (values, label), transformed to near-symmetric scales, before z-scoring."""
    pop = _population(places, years).sum((2, 3))                    # [U, T]
    c = lambda n, y=2022: _census(n, y, places)                     # noqa: E731
    ratio = lambda a, b: np.where(b > 0, a / np.where(b > 0, b, np.nan), np.nan)    # noqa: E731
    hh, resident = c("households"), c("population_resident_census")
    gdp = c("gdp", 2021)
    pop21 = _population(places, [2021]).sum((1, 2, 3))
    pop22 = _population(places, [2022]).sum((1, 2, 3))
    race_u = c("population_race_universe")
    inc_u = c("persons_income_universe")
    ans = np.full(len(places), np.nan)
    ix = {int(u): i for i, u in enumerate(places)}
    for u, v in zip(*(gateway.context_sum("ans_beneficiaries", 2022, {"coverage": "Médico-hospitalar"}).column(k).to_numpy()
                      for k in ("u", "value")), strict=True):
        if int(u) in ix:
            ans[ix[int(u)]] = v
    enrol = np.full(len(places), np.nan)
    for u, v in zip(*(gateway.context_sum("inep_enrolments", 2022, {"margin": "total", "category": "all"}).column(k).to_numpy()
                      for k in ("u", "value")), strict=True):
        if int(u) in ix:
            enrol[ix[int(u)]] = v
    with np.errstate(all="ignore"):
        out = {
            "sewer_network": (ratio(c("households_sewer_network"), hh), "households on the sewer network, 2022"),
            "water_network": (ratio(c("households_water_network"), hh), "households on the water network, 2022"),
            "no_bathroom": (ratio(c("households_without_bathroom"), hh), "households without a bathroom, 2022"),
            "waste_collected": (ratio(c("households_waste_collected"), hh), "households with waste collection, 2022"),
            "literacy_15plus": (ratio(c("persons_15_plus_literate"), c("persons_15_plus")), "literate share of 15+, 2022"),
            "urban_share": (ratio(c("population_urban"), resident), "urban share of the census population, 2022"),
            "income_over_2sm": (ratio(c("persons_income_over_2_sm"), inc_u), "persons with income over 2 minimum wages, 2022"),
            "black_brown_share": (ratio(c("population_black") + c("population_brown"), race_u), "black or brown share, 2022"),
            "indigenous_share": (np.arcsinh(100 * ratio(c("population_indigenous"), race_u)), "asinh of 100 x indigenous share, 2022"),
            "log_gdp_pc": (np.log(ratio(gdp * 1000, pop21)), "log GDP per capita, 2021"),
            "gva_agriculture_share": (np.arcsinh(10 * ratio(c("gross_value_added_agriculture", 2021), gdp)),
                                      "asinh of 10 x agriculture share of GDP, 2021"),
            "gva_public_admin_share": (ratio(c("gross_value_added_public_administration", 2021), gdp),
                                       "public administration share of GDP, 2021"),
            "school_enrolments_pc": (np.arcsinh(10 * ratio(enrol, pop22)), "asinh of 10 x basic-education enrolments per person, 2022"),
            "ans_plan_coverage": (np.arcsinh(10 * ratio(ans, pop22)), "asinh of 10 x private health-plan links per person, Dec 2022"),
            "beds_sus_per1000": (np.arcsinh(_stock_rate("cnes_beds_sus", years, places, pop)), "asinh SUS beds per 1,000, 2015-19"),
            "beds_icu_sus_per1000": (np.arcsinh(10 * _stock_rate("cnes_beds_icu_sus", years, places, pop)),
                                     "asinh of 10 x SUS ICU beds per 1,000, 2015-19"),
            "physicians_per1000": (np.arcsinh(_stock_rate("cnes_physicians_professionals", years, places, pop)),
                                   "asinh physicians (distinct CNS) per 1,000, 2015-19"),
            "nurses_per1000": (np.arcsinh(_stock_rate("cnes_nurses_professionals", years, places, pop)),
                               "asinh nurses per 1,000, 2015-19"),
            "esf_teams_per10k": (np.arcsinh(_stock_rate("cnes_teams_esf", years, places, pop, 1e4)), "asinh ESF teams per 10,000, 2015-19"),
            "mammography_sus_per100k": (np.arcsinh(_stock_rate("cnes_equipment_mammography_sus", years, places, pop, 1e5)),
                                        "asinh SUS mammographs per 100,000, 2015-19"),
        }
    return out


def build(years: list[int] | None = None, places: np.ndarray | None = None) -> MapInputs:
    years = years or YEARS
    if places is None:
        places = np.sort(gateway.population([years[-1]]).column("u").unique().to_numpy())
    U = len(places)
    PA = _population(places, years)
    names, groups, labels, B, SD, left = [], [], [], [], [], {}
    tree = gateway.code_structure("ICD10")
    title = dict(zip(tree.column("code").to_pylist(), tree.column("label").to_pylist(), strict=True))

    from .. import fields, harness  # imported here: harness imports the scans
    test_basis, gen_basis = pairs.MoranBasis(places), pairs.MoranBasis(places, "knn8")
    powers: dict[str, float] = {}

    def admit(tag: str, y: np.ndarray, mu: np.ndarray, b: np.ndarray, tau: float) -> bool:
        """Admission to the pair scan (§8.4): the power of E_b at its minimum effect to see a latent of correlation
        0.3 shared by this field and a partner of its own spatial spectrum, the field refitted as in production."""
        pw = harness.pair_power(mu, 1 / np.sqrt(tau), b, b, b, gen_basis, test_basis, rhos=(fields.PAIR_RHO,),
                                reps=POWER_REPS, seed=("admission", tag))[fields.PAIR_RHO]["power"]
        powers[tag] = pw
        if pw < fields.MIN_POWER:
            left[tag] = f"power {pw:.2f} at rho {fields.PAIR_RHO} ({y.sum():.0f} events in {int((y > 0).sum())} places)"
        return pw >= fields.MIN_POWER

    for group, system, survivors in (("SIM", ("SIM.DO", "death"), False), ("SIH", ("SIH-RD", "hospitalisation"), True)):
        for ch, Y in sorted(_chapter_counts(system, places, years, survivors).items(), key=lambda kv: _roman(kv[0])):
            y, mu = _standardised(Y, PA)
            b, sd, tau = place_effect(y, mu)
            if not admit(f"{group}:{ch}", y, mu, b, tau):
                continue
            names.append(f"{group}:{ch}")
            groups.append(group)
            labels.append(title.get(ch, ch).split(" - ", 1)[-1][:60] + (" (admissions surviving)" if survivors else " (deaths)"))
            B.append(b)
            SD.append(sd)
    births = np.zeros(U)
    ind = {k: np.zeros(U) for k in SINASC}
    overlap_n: dict[tuple[str, str], int] = {}
    ix = {int(u): i for i, u in enumerate(places)}
    for year in years:
        tb, ov = gateway.indicator_counts("SINASC-DN", "birth", year, SINASC, pa.array(places.astype(np.int64)))
        for n, u, v in zip(tb.column("name").to_pylist(), tb.column("u").to_pylist(), tb.column("y").to_pylist(), strict=True):
            (births if n == "*" else ind[n])[ix[u]] += v
        for k, v in ov.items():
            overlap_n[k] = overlap_n.get(k, 0) + v
    for k in SINASC:
        mu = births * ind[k].sum() / births.sum()
        b, sd, tau = place_effect(ind[k], mu)
        if not admit(f"SINASC:{k}", ind[k], mu, b, tau):
            continue
        names.append(f"SINASC:{k}")
        groups.append("SINASC")
        labels.append(SINASC_LABEL[k])
        B.append(b)
        SD.append(sd)
    for k, (v, label) in contexts(places, years).items():
        z = (v - np.nanmean(v)) / np.nanstd(v)
        names.append(f"ctx:{k}")
        groups.append("context")
        labels.append(label)
        B.append(z)
        SD.append(np.where(np.isfinite(z), CONTEXT_SD, np.nan))
    F = len(names)
    overlap = np.zeros((F, F))
    sin = [i for i, g in enumerate(groups) if g == "SINASC"]
    for a in sin:
        for b in sin:
            if a < b:
                ka, kb = names[a].split(":")[1], names[b].split(":")[1]
                n = overlap_n.get((ka, kb), overlap_n.get((kb, ka)))
                m = min(ind[ka].sum(), ind[kb].sum())
                overlap[a, b] = overlap[b, a] = np.nan if n is None else n / m
    return MapInputs(places, names, groups, labels, np.stack(B, 1), np.stack(SD, 1), overlap,
                     {"years": years, "left_out": left, "admission_power": powers, "missing_context": {n: int(np.isnan(B[i]).sum())
                                                                            for i, n in enumerate(names) if groups[i] == "context"}})


def _roman(x: str) -> int:
    v = {"I": 1, "V": 5, "X": 10}
    t = 0
    for a, b in zip(x, x[1:] + " ", strict=True):
        t += -v[a] if v.get(b, 0) > v[a] else v[a]
    return t
