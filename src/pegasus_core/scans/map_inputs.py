"""The fields of a dependency map: place effects of every fitted field of the plan's systems and the context fields.

Every field is read from the production fits through declarations, nothing named here: a count field's place effect
b̂(u) is the shrunk Poisson intercept of ``surprise.refit_place`` over its tier-B0 expectation (the national rates by
age, sex and period, no place effects) summed over the window, with its posterior sd (the pair weight is 1/sd², §7.5);
a measure's or a share's is its precision-weighted mean residual, shrunk (`gaussian_effect`). Two systems share events
only where a declared link records the same event in both (`same_event`: a death in hospital is an admission and a
certificate); there a field's overlap with the other system is its measured linked share, and past `maps.MAX_OVERLAP`
the field's "not linked to" twin (its events less the expected linked ones) enters instead, sharing nothing (§8.5).
A context is a complete count or a rate over a registered denominator, z-scored, with the constant sd 0.05 the gate
used (it cannot change ρ). Every field with events enters (ADR-0028: no field is left out for power).
"""

from __future__ import annotations

import numpy as np

from .. import gateway, surprise
from .maps import MapInputs

CONTEXT_SD = 0.05
YEARS = list(range(2015, 2020))


def _population(places: np.ndarray, years: list[int]) -> np.ndarray:
    """[U, T, 2, 17]: persons by place, year, sex, five-year band (POPSVS)."""
    ix = {int(u): i for i, u in enumerate(places)}
    out = np.zeros((len(places), len(years), 2, 17))
    t = gateway.population(years)
    for u, yr, s, a, n in zip(*(t.column(c).to_numpy() for c in ("u", "year", "sex", "age", "n")), strict=True):
        if int(u) in ix and int(s) in (1, 2):
            out[ix[int(u)], years.index(int(yr)), int(s) - 1, min(int(a) // 5, 16)] += n
    return out


def place_effect(y: np.ndarray, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """The shrunk Poisson place intercept over the expectation (B0 for E_b) and its posterior sd."""
    _, b, sd, tau = surprise.refit_place(y[:, None], mu[:, None], np.full((len(y), 1), np.inf), np.ones((1, 1)))
    return b[:, 0], sd[:, 0], float(tau[0])


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


#: the event kinds that count care used rather than a health state (pegasus_data `event_types` kind): a place's level of
#: use (access, referral, billing) enters every such field, and the map reads them net of it (`maps.factors`)
CARE_KINDS = ("hospitalisation", "authorisation")


def _window(su, years: list[int], places: np.ndarray) -> tuple[np.ndarray, ...]:
    """A surprise summed over the map's years on the map's places: y, μ [U], and the place weights Σw, Σw·(y − μ) [U]
    (a Gaussian location's precision and residual)."""
    cols = np.isin(np.asarray(su.years), years)
    index = {int(p): i for i, p in enumerate(su.places)}
    rows = np.array([index.get(int(u), -1) for u in places])
    have = rows >= 0
    out = [np.zeros(len(places)) for _ in range(4)]
    y, mu, w = (np.nan_to_num(np.asarray(a, dtype=float)[rows[have]][:, cols]) for a in (su.y, su.mu, su.w))
    out[0][have], out[1][have], out[2][have], out[3][have] = y.sum(1), mu.sum(1), w.sum(1), (w * (y - mu)).sum(1)
    return tuple(out)


def gaussian_effect(sw: np.ndarray, swr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A location field's place effect: each place's precision-weighted mean residual over the window, shrunk toward 0
    by the between-place variance τ² its places show beyond their sampling variance (a moment estimate); its sd."""
    ok = sw > 0
    r = np.where(ok, swr / np.where(ok, sw, 1.0), np.nan)
    v = np.where(ok, 1.0 / np.where(ok, sw, 1.0), np.nan)
    tau2 = max(float(np.nanvar(r) - np.nanmean(v)), 1e-12)
    return np.where(ok, r * tau2 / (tau2 + v), np.nan), np.where(ok, np.sqrt(tau2 * v / (tau2 + v)), np.nan)


def _readers(dataset: str, event: str) -> list[dict]:
    """The readers of a system's fitted fields on the production years: the counts ({}), and every measure, share or
    linked field fitted from its declarations (the reader its fit's key records; race-stratified fits are disparity
    readings, not map fields)."""
    from .. import tools

    out: list[dict] = [{}]
    for k in tools.fitted(dataset, event, years=tools.FIT_YEARS):
        key = k["key"]
        if key.get("source") in (None, "events") or key.get("race") or key.get("grain"):
            continue
        reader = {f: (tuple(v) if f == "bounds" else v) for f, v in key.items() if f in READER_KEYS}
        if reader not in out:
            out.append(reader)
    return out


#: the fields of a fit's key that make up its reader (`monolith.assemble`'s source)
READER_KEYS = ("source", "mark", "bounds", "missing", "classifier", "structure", "casemix", "indicator", "success",
               "link", "side", "anchor", "sign")


def _linked(dataset: str, event: str, link: str, side: str, years: list[int], places: np.ndarray,
            leaves: dict[str, set]) -> dict[str, np.ndarray]:
    """[U] the expected number of each field's events with a partner across ``link`` (Σ p_match, `gateway.linked_counts`
    on the event type's primary classifier), summed over the map's years, by field (``leaves``: its categories)."""
    et = gateway.event_type(dataset, event)
    primary = next((c["column"] for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    index = {int(u): i for i, u in enumerate(places)}
    out = {name: np.zeros(len(places)) for name in leaves}
    for year in years:
        t = gateway.linked_counts(dataset, event, year, link, side, classifier=primary).counts
        code3 = [str(c)[:3] for c in t.column("code").to_pylist()]
        for u, c, k in zip(t.column("u").to_pylist(), code3, t.column("k").to_pylist(), strict=True):
            i = index.get(int(u))
            if i is None or not k:
                continue
            for name, cats in leaves.items():
                if c in cats or "*" in cats:
                    out[name][i] += k
    return out


def build(systems: list[tuple[str, str, list[str]]], years: list[int] | None = None,
          places: np.ndarray | None = None) -> MapInputs:
    """The map's fields (module docstring), from declarations and the production fits: for every (dataset, event,
    blocks) in ``systems``, each chapter field of its count fits and every fitted measure, share or linked field, its
    place effect over ``years`` against tier B0 (`Session.surprise`: the national rates by age, sex and period, no
    place effects); the context fields; and, where a declared link records the same events in two systems
    (`same_event`), each field's measured overlap with the other system, with its "not linked to" field where that
    overlap passes `maps.MAX_OVERLAP` (its events less the expected linked ones: no event shared with the other)."""
    from .. import tools
    from .maps import MAX_OVERLAP

    years = years or YEARS
    if places is None:
        places = np.sort(gateway.population([years[-1]]).column("u").unique().to_numpy())
    names, groups, labels, B, SD = [], [], [], [], []
    cats: list[set] = []            # each field's categories (the overlap of two fields of one system)
    def add(name: str, group: str, label: str, b: np.ndarray, sd: np.ndarray, categories: set) -> None:
        names.append(name)
        groups.append(group)
        labels.append(label)
        B.append(b)
        SD.append(sd)
        cats.append(categories)

    counts: dict[str, tuple[np.ndarray, np.ndarray]] = {}       # a count field's (y, μ) for its linked variant
    kinds: dict[str, str] = {}
    for dataset, event, blocks in systems:
        kinds[dataset] = gateway.event_type(dataset, event).get("kind") or ""
        for reader in _readers(dataset, event):
            s = tools.Session(dataset, event, tools.FIT_YEARS, source=reader)
            tag = "" if not reader else "|" + ":".join(str(reader.get(f)) for f in ("source", "mark", "indicator",
                                                                                   "link", "classifier") if reader.get(f))
            for block in (blocks if not reader else s._blocks()):
                if block not in s._blocks():
                    continue
                node = block
                su = s.surprise(node, "B0")
                y, mu, sw, swr = _window(su, years, places)
                field_cats = set(s.expectations.registry.leaves(node)) if node != "*" else {"*"}
                name = f"{dataset}:{node}{tag}"
                label = (s.expectations.field(node).label or node)[:60] + (f" ({tag[1:]})" if tag else "")
                if surprise.gaussian(su):
                    b, sd = gaussian_effect(sw, swr)
                    if np.isfinite(b).sum() >= 2:
                        add(name, dataset, label, b, sd, field_cats | {tag})
                    continue
                if y.sum() <= 0:
                    continue
                b, sd, _ = place_effect(y, mu)
                add(name, dataset, label, b, sd, field_cats)
                counts[name] = (y, mu)
    # the same events in two systems: measured overlap, and the "not linked to" fields
    shared: dict[tuple[int, str], float] = {}           # (field index, other dataset) -> its events' linked share
    in_map = {ds.upper().replace(".", "-"): (ds, ev) for ds, ev, _ in systems}
    for spec_name, spec in gateway.link_specs().items():
        if not spec.same_event:
            continue
        for side, sd_, other in (("left", spec.left, spec.right), ("right", spec.right, spec.left)):
            mine, theirs = sd_.dataset.upper().replace(".", "-"), other.dataset.upper().replace(".", "-")
            if mine not in in_map or theirs not in in_map or (sd_.group and sd_.where):
                continue
            ds, ev = in_map[mine]
            idx = [i for i, n in enumerate(names) if groups[i] == ds and n in counts]
            linked = _linked(ds, ev, spec_name, side, years, places, {names[i]: cats[i] for i in idx})
            for i in idx:
                y, mu = counts[names[i]]
                k = np.minimum(linked[names[i]], y)
                share = float(k.sum() / max(y.sum(), 1e-12))
                shared[(i, in_map[theirs][0])] = share
                if share <= MAX_OVERLAP:
                    continue
                y2 = y - k
                mu2 = mu * (y2.sum() / max(y.sum(), 1e-12))     # the national share not linked, on B0's expectation
                b, sd, _ = place_effect(y2, mu2)
                add(f"{names[i]}|not linked to {in_map[theirs][0]}", ds,
                    labels[i] + f" (not linked to {in_map[theirs][0]})", b, sd, cats[i] | {f"unlinked:{in_map[theirs][0]}"})
    for k, (v, label) in contexts(places, years).items():
        z = (v - np.nanmean(v)) / np.nanstd(v)
        add(f"ctx:{k}", "context", label, z, np.where(np.isfinite(z), CONTEXT_SD, np.nan), set())
    F = len(names)
    overlap = np.zeros((F, F))
    for a in range(F):
        for b in range(a + 1, F):
            ga, gb = groups[a], groups[b]
            if "context" in (ga, gb):
                continue
            if ga == gb:            # one system: fields share events where their categories meet
                base_a, base_b = names[a].split("|not linked")[0], names[b].split("|not linked")[0]
                ov = 1.0 if (base_a == base_b or (cats[a] & cats[b]) - {""}) else 0.0
            else:
                base = {n: names.index(n.split("|not linked")[0]) for n in (names[a], names[b])}
                ia, ib = base[names[a]], base[names[b]]
                unl_a = f"unlinked:{gb}" in cats[a]
                unl_b = f"unlinked:{ga}" in cats[b]
                sa, sb = shared.get((ia, gb)), shared.get((ib, ga))
                if unl_a or unl_b or (sa is None and sb is None):
                    ov = 0.0        # no declared same-event link, or one side's linked events removed
                else:
                    ov = max(v for v in (sa, sb) if v is not None)
            overlap[a, b] = overlap[b, a] = ov
    return MapInputs(places, names, groups, labels, np.stack(B, 1), np.stack(SD, 1), overlap,
                     {"years": years, "systems": [list(x[:2]) for x in systems], "care": [d for d, k in kinds.items()
                                                                                 if k in CARE_KINDS],
                      "linked_share": {f"{names[i]}->{d}": v for (i, d), v
                                                                                     in shared.items()},
                      "missing_context": {n: int(np.isnan(B[i]).sum()) for i, n in enumerate(names)
                                          if groups[i] == "context"}})
