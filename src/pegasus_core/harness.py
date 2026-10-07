"""The validation harness (ARCHITECTURE §10): the test suite of a statistical search.

- Known positives: signals the literature and the surveillance record establish,
  each with the lens that should find it, its locus and a pass criterion.
- Planted signals: y' = y + Poisson((θ − 1)·μ_S) over a known locus S (v0, against a
  fixed μ; superseded by the grid, which refits).
- Null surrogates: y* ~ NB(μ̂, φ̂), independent across fields; whatever a lens
  finds there is its false-lead rate.
- Negative controls for pairs: surrogates that keep each field's dependence and
  remove the relation. Between places, Moran spectral randomisation (Wagner &
  Dray 2015) on the symmetric-normalised graph (``pairs.MoranBasis``): the
  field's coordinates in the Moran eigenvectors get random signs, so its
  spectrum is kept exactly. The raw weight matrix is not used: its eigenvectors
  localise and the surrogates lose long-range structure (evaluation 2026-10-05).
  Within places, the field's series shifted by k ≥ 2 years.
- The designed grid (§10.3, O5): planted departures by locus kind, shape and size in
  worlds drawn from the fit and refitted, read by the production lenses; each lens's
  power surface and the false leads of null worlds characterise it. Nothing gates
  (ARCHITECTURE §10.5): the gate of v0 was retired with ADR-0023's revision.

Results are tables in the store (``harness``), written up as evaluation entries.
"""

from __future__ import annotations

import gc
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
import pyarrow as pa
from scipy import special, stats

from . import config, store, surprise
from .scans import maps, pairs, subset

Q = 0.05


EVENT_CRITERION = "a finding whose years overlap the event's, with half its places or more in its area, of the question's shape"


@dataclass(frozen=True)
class Positive:
    name: str
    dataset: str
    event: str
    node: str                       # field: a node of the classifier tree
    lens: str
    tier: str
    places: str                     # a classification and its codes: "uf:13" or "ibge_macroregion:2"
    years: tuple[int, int]
    criterion: str = "locus Jaccard ≥ 0.5 and effect sign"
    grain: str = "year"
    note: str = ""

    @property
    def question(self) -> str:
        """The question it is a positive for (`questions`): its declared lens's (`LENS_QUESTION`), or the question a
        later declaration names directly in the lens's place."""
        return LENS_QUESTION.get(self.lens, self.lens)


# the v0 lens of each declaration and the question it asked; the declarations stay as made (their commit order is the
# evidence), the record reads them through the questions
LENS_QUESTION = {"space_time": "excess", "outbreak": "excess", "change_point": "step", "trend_divergence": "trend",
                 "spatial_cluster": "cluster", "group_disparity": "group", "E_w": "relation", "E_b": "relation",
                 "E_b|Z": "relation", "explain_away": "explanation"}


POSITIVES: tuple[Positive, ...] = (
    # declared 2026-10-07 before their first run (data/real_events.py; evaluation 2026-10-07, real events), each by the
    # question it is a positive for
    Positive("Yellow fever deaths, the 2017–18 sylvatic outbreak", "SIM.DO", "death", "A95", "excess", "B1",
             "uf:31,32,35,33", (2017, 2018), criterion=EVENT_CRITERION),
    Positive("Measles admissions, Roraima and Amazonas 2018–19", "SIH-RD", "hospitalisation", "B05", "excess", "B1",
             "uf:14,13", (2018, 2019), criterion=EVENT_CRITERION, note="importation from Venezuela"),
    Positive("Chikungunya and other arboviral fevers, the Northeast 2016–17", "SIH-RD", "hospitalisation", "A92",
             "excess", "B1", "ibge_macroregion:2", (2016, 2017), criterion=EVENT_CRITERION),
    Positive("Accidental deaths, Brumadinho 2019", "SIM.DO", "death", "V01-X59", "excess", "B1", "mun:310900",
             (2019, 2019), criterion=EVENT_CRITERION, note="the dam collapse of 25 January 2019"),
    Positive("COVID-19 deaths in the North 2020–21, relative to Brazil", "SIM.DO", "death", "B25-B34", "excess", "B1",
             "ibge_macroregion:1", (2020, 2021), criterion=EVENT_CRITERION),
    Positive("COVID-19 deaths, Amazonas", "SIM.DO", "death", "B34", "space_time", "B2", "uf:13",
             (2020, 2021), note="SIM codes COVID-19 as underlying cause B34.2 (U07.1 only as a marker); "
                                "Manaus, January 2021; national 2020–21"),
    Positive("COVID-19 respiratory excess", "SIM.DO", "death", "J00-J99", "space_time", "B2", "ibge_macroregion:1",
             (2020, 2021), note="ill-coded COVID deaths in the respiratory chapter, North"),
    Positive("Chagas disease geography", "SIM.DO", "death", "B57", "spatial_cluster", "B0", "uf:52,31,29,17",
             (2010, 2023), note="central endemic belt: GO, MG, BA, TO"),
    Positive("Schistosomiasis geography", "SIM.DO", "death", "B65", "spatial_cluster", "B0", "uf:26,27,28,29,31",
             (2010, 2023), note="PE, AL, SE, BA, MG"),
    Positive("Leptospirosis after the floods", "SINAN.LEPT", "notification", "A27", "space_time", "B2", "uf:43",
             (2024, 2024), grain="month", note="May–July 2024"),
    Positive("Microcephaly", "SINASC", "birth", "Q02", "space_time", "B2", "ibge_macroregion:2", (2015, 2016)),
    Positive("Dengue epidemics", "SINAN.DENG", "notification", "A90", "outbreak", "B2s", "uf:*", (2010, 2024),
             grain="month"),
    Positive("Winter respiratory admissions", "SIH.RD", "admission", "J00-J99", "outbreak", "B2s",
             "ibge_macroregion:3,4", (2010, 2024), grain="month"),
    # lenses that had no declared positive (evaluation 2026-10-05-lens-positives); criterion "recovery" below
    Positive("Violent deaths of undetermined cause, São Paulo 2018", "SIM.DO", "death", "Y10-Y34", "change_point", "B2",
             "uf:35", (2010, 2019), criterion="excess-weighted recall ≥ 0.5, window start within 1 year, sign up",
             note="Atlas da Violência 2020 ch.1: Brazil 12,310 (+25.6%); São Paulo 4,255 (+62.5%), information not "
                  "reaching the health secretariat (Cerqueira, Brasil de Fato 2020-08-30). Fitted 2010–2019 so the "
                  "shift is recent: a persistent step older than ~3 years is absorbed by B2's trend"),
    Positive("Violent deaths of undetermined cause, Rio de Janeiro, Acre, Rondônia 2019", "SIM.DO", "death", "Y10-Y34",
             "change_point", "B2", "uf:33,12,11", (2010, 2019),
             criterion="excess-weighted recall ≥ 0.5, window start within 1 year, sign up",
             note="Atlas da Violência 2021: 2018→2019 +232% (RJ), +185% (AC), +178% (RO), Brazil 12,310→16,648"),
    Positive("Municipalities installed in 2013", "SINASC-DN", "birth", "*", "trend_divergence", "B2",
             "mun:150475,421265,422000,500627,431454", (2010, 2023),
             criterion="recall ≥ 0.5 of the documented municipalities, sign up",
             note="IBGE: Mojuí dos Campos PA, Pescaria Brava SC, Balneário Rincão SC, Pinto Bandeira RS, Paraíso das "
                  "Águas MS installed in 2013 (5,570 municipalities); births are recorded under the new code only "
                  "from 2013, the parent's before. A boundary (recording) divergence, an observation-lens positive"),
    Positive("Female homicide, Roraima", "SIM.DO", "death", "X85-Y09", "group_disparity", "B0", "uf:14", (2010, 2023),
             criterion="a finding in the locus; locus female share above the national pattern's",
             note="Atlas da Violência 2019 and 2021: Roraima has the highest female homicide rate of the UFs. The "
                  "national pattern (young men) is the lens's reference, so the young-male excess itself cannot be "
                  "a positive"),
    # declared BEFORE the lens ran (commit order is the evidence; loci derived by scripts/declare_positives.py from the
    # Atlas da Violência UF tables alone). Pass: weighted recall (weight: estimated deaths) >= 0.5 with the sign; Jaccard reported
    Positive("Homicide trend divergence across UF borders", "SIM.DO", "death", "X85-Y09", "trend_divergence", "B2",
             "declare_positives:trend_divergence (30 municipalities)", (2010, 2023),
             criterion="excess-weighted recall >= 0.5 of the documented municipalities, sign of d_u",
             note="Atlas da Violência 2019 Table 2.1 (2010-12) and 2025 Table 2.1 (2013-23), IPEA/FBSP: UF rates; "
                  "a municipality's documented divergence is its UF's log-rate slope less its contiguity neighbours' UFs' mean; "
                  "documented where |d| >= ln 1.5/13 per year"),
    # a second estimand of the trend lens, declared in a later commit than the first round and before its national run was
    # scored (the national run had been looked at once against the neighbours' loci: 4 UFs found; these loci follow from the Atlas
    # tables alone): trend against the national course
    Positive("Homicide trend divergence from the national course", "SIM.DO", "death", "X85-Y09", "trend_divergence", "B2",
             "declare_positives:trend_divergence_national (2,289 municipalities of 14 UFs)", (2010, 2023),
             criterion="excess-weighted recall >= 0.5 of the documented municipalities, sign of d_u; reference=national",
             note="Atlas da Violência 2019 Table 2.1 and 2025 Table 2.1: a municipality's documented divergence is its UF's "
                  "log-rate slope (2010-23) less Brazil's; documented where |d| >= ln 1.5 / 13 per year"),
    Positive("Women's share of homicide victims, by UF", "SIM.DO", "death", "X85-Y09", "group_disparity", "B0",
             "declare_positives:group_women (UFs RO RR AP RN AL SE SP SC RS MS)", (2013, 2023),
             criterion="excess-weighted recall >= 0.5; sign of (observed / expected female share - 1) as documented",
             note="Atlas da Violência 2025 Tables 5.1 / 2.2: women's share of homicides 2013-2023 as a ratio to Brazil's "
                  "(7.9%), documented where >= 1.25 or <= 0.8"),
    Positive("Young men's share of homicide victims, by UF", "SIM.DO", "death", "X85-Y09", "group_disparity", "B0",
             "declare_positives:group_young_men (UFs RO RR AP SP MS)", (2013, 2023),
             criterion="excess-weighted recall >= 0.5; sign of (observed / expected male 15-29 share - 1) as documented",
             note="Atlas da Violência 2025 Tables 4.3 / 2.2: men aged 15-29 share of homicides 2013-2023 as a ratio to "
                  "Brazil's (49.2%), documented where >= 1.25 or <= 0.8"),
    Positive("Cold months and respiratory admissions", "SIH-RD+INMET", "hospitalisation", "X", "E_w", "B2s",
             "municipalities with a station", (2010, 2023), grain="month",
             criterion="ρ(cold anomaly → admissions) < −δ at lag 0–1, absent in the 5-year-shifted control",
             note="Requia et al., Environ Res 2023;231:116231, low temperature and respiratory admissions in Brazil, "
                  "RR 1.07 (1.01–1.14)"),
    # declared BEFORE any CNES field was read against these outcomes (commit order is the evidence). E_b positives and an
    # explain-away test with the CNES supply fields (ADR-0150 of pegasus_data); constants and rules fixed here
    Positive("Roemer's law: SUS admissions and SUS beds", "SIH-RD+CNES", "hospitalisation", "*", "E_b", "B0",
             "5,570 municipalities", (2015, 2019),
             criterion="rho > 0 and p <= 0.05 at delta_E = 0.03 (E_b), and rho > 0 and p <= 0.05 at delta_E|Z = 0.05 with "
                       "Z = [log GDP pc 2021, urban share]; both required",
             note="Outcome: all-cause SIH-RD admissions by residence, 2015-2019 (before COVID), indirectly standardised on the "
                  "national sex x 5-year-age rates of each year, Poisson shrunk place effect (surprise.refit_place, T=1, as the "
                  "diarrhoea outcome). Context: cnes_beds_sus (December stocks) per 1,000 residents of POPSVS, mean of 2015-2019 "
                  "yearly rates, asinh; z-scored with constant sd 0.05, a municipality without a CNES record carries no weight. "
                  "Roemer MI 1961 Hospitals 35:36-42 ('a bed built is a bed filled'); Delamater et al. 2013 PLoS ONE 8(2):e54900 "
                  "doi:10.1371/journal.pone.0054900 (Michigan ZIP codes, spatial SAR, positive, standardised 0.21). Beds are placed "
                  "where demand is, and residents of bedless towns are admitted in the hub: E_b cannot separate supply-induced "
                  "demand from demand-placed supply"),
    Positive("Primary care coverage and infant mortality", "SIM.DO+SINASC-DN+CNES", "death", "age0", "E_b|Z", "B0",
             "5,570 municipalities", (2018, 2022),
             criterion="rho < 0 and p <= 0.05 at delta_E|Z = 0.05 given log GDP pc 2021",
             note="Context: ESF coverage = min(1, 3,450 x cnes_teams_esf / POPSVS population), mean of December 2018-2022. "
                  "Outcome as the census positives (infant deaths 2018-22 over SINASC births, shrunk). Aquino, Oliveira & "
                  "Barreto 2009 AJPH 99:87-93 (Family Health Program and infant mortality, Brazilian municipalities, "
                  "doi:10.2105/AJPH.2007.127480); Rasella et al. 2013 Lancet 382:57-64 (doi:10.1016/S0140-6736(13)60715-1). "
                  "Those are panel designs; the cross-section is confounded by indication (ESF reached the poorest first)"),
    Positive("Sanitation and infant mortality survive adjustment for primary care", "SIM.DO+SINASC-DN+CENSO+CNES", "death",
             "age0", "E_b|Z", "B0", "5,570 municipalities", (2018, 2022),
             criterion="of IM-no_bathroom, IM-water, DIA-no_bathroom (the pairs admitted at delta_E|Z given log GDP pc, "
                       "pairs-gate entry): sign kept in 3 of 3 and p <= 0.05 at delta_E|Z in at least 2 of 3, with "
                       "Z = [log GDP pc, ESF coverage, community health agents per 1,000 (asinh)]",
             note="Census 2022 shares and the outcomes as the E_b gate (scripts/gate_eb.py inputs); ESF coverage as above, agents "
                  "= cnes_community_health_agents_professionals per 1,000, mean December 2018-2022. A mediator of sanitation "
                  "through primary care would shrink rho; a confounder would too"),
    Positive("Sao Borja acute MI (I21) from 2018: a supply step", "SIM.DO+CNES", "death", "I21", "explain_away", "B2",
             "mun:431800", (2018, 2023),
             criterion="explained by supply when, in one of six CNES fields (beds_total, beds_icu_total, equipment_ct, "
                       "facilities_hospital_sus, physicians_professionals, teams_esf), the log ratio of the mean of the lead's "
                       "first two years to the mean of the two before exceeds the 99th percentile of the same log ratio over the "
                       "5,570 municipalities, at the same place; explain_away over the lead's places across all years reported",
             note="Lead-triage entry item 14: I21 112 against 20 a year, neighbours flat, ill-defined share 8.0% -> 1.8%. The "
                  "same rule applies to the other leads in the 'unexplained' top 15 of that entry; the supply fields are "
                  "2008-2023 December stocks. A supply step explains a detection or recording change, not incidence"),
    # SINAN breadth wave 1: declared BEFORE the families were fitted or surveyed (commit order is the evidence)
    Positive("Congenital syphilis rise of the 2010s", "SINAN.SIFC", "notification", "*", "outbreak", "BPA", "uf:*",
             (2014, 2023),
             criterion="alarm baseline fitted to 2010-2013: national observed/expected in 2018 >= 1.5 and at least 20 of the "
                       "27 UFs flagged (outbreak lens, state level) in 2018",
             note="Ministry of Health syphilis bulletins (SINAN): congenital syphilis incidence 2.4 per 1,000 live births in "
                  "2010, 9.0 in 2018 (26,219 notifications); read through secondary articles that cite the bulletins, not at "
                  "the source. A national rise, so a prospective positive: B2 absorbs a trend"),
    Positive("Visceral leishmaniasis geography", "SINAN.LEIV", "notification", "*", "spatial_cluster", "B0",
             "uf:21,31,15,23,29", (2010, 2023),
             criterion="as the Chagas and schistosomiasis positives: observed/expected above 1 in each named UF; every spatial "
                       "cluster inside the named UFs (precision >= 0.8); share of the named UFs' excess captured reported",
             note="Ministry of Health, visceral leishmaniasis cases by UF 2018-2022: Maranhão, Minas Gerais, Pará, Ceará, Bahia "
                  "each above 1,000 (read through a search summary of the Ministry's table and of a 2007-2021 review, not at the "
                  "source)"),
    Positive("Chikungunya epidemic, Ceará 2017", "SINAN.CHIK", "case", "*", "space_time", "B1", "uf:23", (2017, 2017),
             grain="month",
             criterion="as the leptospirosis positive: the space-time findings of 2017 lie inside Ceará (>= 80% of in-window "
                       "findings) and capture >= 50% of Ceará's 2017 excess",
             note="Ceará reported the largest chikungunya epidemic of 2017 (105,232 confirmed cases in the state, 61,718 in "
                  "Fortaleza; Fortaleza and state bulletins, read through search summaries, not at the source)"),
    # Re-test of the arbovirus -> microcephaly pair (its first test, E_w at region-month, did not admit a lag: evaluation
    # 2026-10-05). Declared before the coarse-grain, prewhitened run (data/positive_lagged_microcephaly.py)
    Positive("Dengue notifications lead microcephaly births, Northeast 2015-16", "SINAN.DENG -> SINASC.DN",
             "probable_case -> birth", "* -> Q02", "E_w", "BP", "uf:*", (2015, 2017), grain="month",
             criterion="state scale, each series prewhitened by its own pooled AR(2), lags 0-12, delta_E 0.1: the largest "
                       "dengue->Q02 rho is at a lag in 5..9 with p < 0.05/13; dengue->Q90 (Down syndrome, control) admits no "
                       "lag at p < 0.05/13; Q02->dengue admits no lag in 5..9",
             note="Q02 births in the Northeast 2,371 against 94 expected in 2015-16, 6-7 months after the dengue-like surge "
                  "(the Zika epidemic, notifiable only from 2016); Brazil's microcephaly emergency, Nov 2015"),
)


def recovery(found: set, documented: set, weight: dict | None = None) -> dict[str, float]:
    """Locus recovery (§10.1): Jaccard, precision and recall over a set of units, and the recall weighted by the
    documented excess (``weight``: unit → events), the figure the criterion uses for sparse per-place lenses."""
    hit = found & documented
    w = weight or dict.fromkeys(documented, 1.0)
    total = sum(w.get(u, 0.0) for u in documented)
    return {"jaccard": len(hit) / len(found | documented) if found | documented else 0.0,
            "precision": len(hit) / len(found) if found else 0.0,
            "recall": len(hit) / len(documented) if documented else 0.0,
            "weighted_recall": sum(w.get(u, 0.0) for u in hit) / total if total else 0.0}


# ---------------------------------------------------------------------- surrogates


def surrogate(s: surprise.Surprise, seed_parts: tuple) -> surprise.Surprise:
    """The same field with y ~ NB(μ, φ): a world where the model is true."""
    rng = np.random.default_rng(config.seed(*seed_parts))
    return with_counts(s, surprise.replicate_correlated(s.mu, s.phi, s.noise, rng), seed_parts)


def with_counts(s: surprise.Surprise, y: np.ndarray, seed_parts: tuple) -> surprise.Surprise:
    """The field with other counts y (a surrogate, a planted signal): its PIT redrawn and, at B2,
    its place trends refitted."""
    u, z = surprise.randomised_pit(y, s.mu, s.phi, config.seed(*seed_parts, "pit"))
    extras = s.extras
    if "beta" in s.extras:
        # B2's place trends must be the surrogate's own, refitted around the B2 expectation (so a
        # trend lens tests the null, not the real data's trends again)
        yrs = s.years.astype(float)
        st = (yrs - yrs.mean()) / max(yrs.std(), 1e-9)
        # τ as learned from the field's real data: re-estimating it from null-but-one data shrinks
        # every trend to zero (the first trend power curve was 0 at θ = 2, 2026-10-04)
        _, b, sd, tau = surprise.refit_place(y, s.mu, s.phi, np.stack([np.ones_like(st), st], axis=1),
                                             tau=s.extras["tau"])
        extras = {**s.extras, "alpha": b[:, 0], "beta": b[:, 1], "alpha_sd": sd[:, 0], "beta_sd": sd[:, 1],
                  "tau": tau, "offset": s.mu}     # the trends are departures from the generating mean
    return surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, u, z, s.w, s.flags,
                             s.calibration, extras, noise=s.noise)


DELTA_GRID = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.1)


def pair_negatives(outcome: tuple[np.ndarray, np.ndarray], contexts: dict[str, np.ndarray | tuple], test_basis: pairs.MoranBasis,
                   gen_basis: pairs.MoranBasis, draws: int = 200, context_sd: float = 0.05,
                   Z: np.ndarray | None = None, seed: tuple = ("pair-negatives",)) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """E_b negative controls (§10.2): the real outcome effect (b̂, sd) against Moran-randomised surrogates of each
    real context field. The surrogates come from ``gen_basis``, a basis other than the one that tests them, so
    the test is not judged by its own randomisation. With an adjustment design Z [n, q] (E_b|Z), the part of the
    context explained by Z is kept and only its residual is randomised, so the null is x ⟂ outcome given Z.
    A context is its field x, or (x, sd) when it carries its own noise (another outcome's place effects).
    Returns, per context, (ρ̂, n_eff) over the draws."""
    out = {}
    for name, spec in contexts.items():
        x, sd = spec if isinstance(spec, tuple) else (spec, np.full(len(spec), context_sd))
        rng = np.random.default_rng(config.seed(*seed, name))
        fitted = np.zeros_like(x)
        if Z is not None:
            Zc = np.column_stack([np.ones(len(x)), Z])
            fitted = Zc @ np.linalg.lstsq(Zc, x, rcond=None)[0]
        S = fitted[:, None] + gen_basis.randomise(np.repeat((x - fitted)[:, None], draws, 1), rng)
        effects = {"outcome": outcome} | {f"s{j}": (S[:, j], sd) for j in range(draws)}
        _, R, n_eff = pairs.statistics(effects, test_basis, Z)
        out[name] = (R[0, 1:], n_eff[0, 1:])
    return out


def calibrate_delta(families: dict[str, list[tuple[np.ndarray, np.ndarray]]], q: float = Q,
                    grid: tuple[float, ...] = DELTA_GRID) -> dict[str, Any]:
    """δ_E (§8.4): the smallest δ on the grid at which no family's false-lead rate exceeds q. A family is an
    outcome field against its contexts; its rate is the share of all its negative-control pairs with p ≤ q
    under H0 |ρ| ≤ δ (pooled over the contexts: single field pairs carry too little Monte-Carlo mass)."""
    rates = {}
    for d in grid:
        rates[d] = {f: float(np.mean(np.concatenate([pairs.minimum_effect_p(r, n, d) <= q for r, n in cells])))
                    for f, cells in families.items()}
    ok = [d for d in grid if max(rates[d].values()) <= q]
    return {"delta_E": min(ok) if ok else None, "rate_by_delta_and_family": rates}


def pair_power(mu: np.ndarray, signal_sd: float, template_outcome: np.ndarray, template_context: np.ndarray,
               template_latent: np.ndarray, gen_basis: pairs.MoranBasis, test_basis: pairs.MoranBasis,
               rhos: tuple[float, ...] = (0.15, 0.3, 0.45), reps: int = 50, delta: float = pairs.MIN_EFFECT["E_b"],
               context_sd: float = 0.05, seed: tuple = ("pair-power",)) -> dict[float, dict[str, float]]:
    """E_b power on planted shared latent fields (§10.3). The outcome counts are Poisson(μ·exp(σ_b b)) and the
    context is a field, both carrying the latent L: b = √(1−ρ) B₀ + √ρ L, x = √(1−ρ) X₀ + √ρ L, the three
    independent Moran-randomised copies of the given templates (their spectra), standardised. The outcome effect is
    refitted as in production (surprise.refit_place), so shrinkage attenuates the observed ρ̂ below ρ."""
    std = lambda v: (v - v.mean()) / v.std()  # noqa: E731
    out = {}
    for rho in rhos:
        hits, seen = [], []
        for r in range(reps):
            rng = np.random.default_rng(config.seed(*seed, rho, r))
            L, B0, X0 = (std(gen_basis.randomise(t, rng)) for t in (template_latent, template_outcome, template_context))
            b_true = np.sqrt(1 - rho) * B0 + np.sqrt(rho) * L
            x = np.sqrt(1 - rho) * X0 + np.sqrt(rho) * L
            y = rng.poisson(mu * np.exp(signal_sd * b_true))[:, None]
            _, b, sd, _ = surprise.refit_place(y, mu[:, None], np.full(y.shape, np.inf), np.ones((1, 1)))
            _, R, n_eff = pairs.statistics({"outcome": (b[:, 0], sd[:, 0]), "context": (x, np.full(len(x), context_sd))},
                                           test_basis)
            hits.append(float(pairs.minimum_effect_p(R[0, 1], n_eff[0, 1], delta) <= Q))
            seen.append(float(R[0, 1]))
        out[rho] = {"power": float(np.mean(hits)), "mean_observed_rho": float(np.mean(seen))}
    return out


def map_negatives(inp: maps.MapInputs, test_basis: pairs.MoranBasis, gen_basis: pairs.MoranBasis, worlds: int = 20,
                  health_only: bool = False, q: float = Q, seed: tuple = ("map-negatives",), **kw) -> dict[str, Any]:
    """The false-edge rate of a dependency map (§7.6, §10.2): the whole map rerun on worlds in which every field is
    replaced by its Moran-randomised surrogate (each field its own signs, its spectrum, sd and missingness kept), so
    every edge found is false. ``health_only`` keeps the real contexts (their mutual dependence is then a true
    structure the conditional layer must not mistake for the health fields'). The surrogates come from ``gen_basis``,
    another graph than the one that tests. Returns the admitted edges per world and layer and, for δ calibration,
    each world's (ρ̂, n_eff) by family."""
    rng = np.random.default_rng(config.seed(*seed, "health" if health_only else "all"))
    fields = [i for i, g in enumerate(inp.groups) if not (health_only and g == "context")]
    rows, raw = [], []
    for w in range(worlds):
        B = inp.B.copy()
        sub = B[:, fields]
        miss = ~np.isfinite(sub)
        B[:, fields] = np.where(miss, np.nan, gen_basis.randomise(np.where(miss, 0.0, sub), rng))
        world = maps.MapInputs(inp.places, inp.names, inp.groups, inp.labels, B, inp.SD, inp.overlap, inp.meta)
        m = maps.dependency_map(world, test_basis, None, f"negatives-{w}", q, **kw)
        rows.append({"world": w, "tested": m.tested["marginal"], **{f"{lay}:{k}": v for lay, d in m.controlled.items()
                                                                  for k, v in d.items()}})
        e = m.edges
        raw.append({k: e.column(k).to_numpy() for k in ("rho", "n_eff", "rho_c", "n_eff_c") if k in e.column_names}
                   | {"family": np.array(e.column("family").to_pylist())})
    return {"worlds": rows, "raw": raw, "health_only": health_only, "q": q}


def map_delta(negatives: dict[str, Any], layer: str = "marginal", grid: tuple[float, ...] = DELTA_GRID) -> dict[str, Any]:
    """The map's δ_E on its own negatives: the smallest δ at which no family's share of tests with p ≤ q exceeds q
    (pooled over worlds; the layer's n_eff already net of Z)."""
    r, n = ("rho", "n_eff") if layer == "marginal" else ("rho_c", "n_eff_c")
    q = negatives["q"]
    fams = sorted({f for w in negatives["raw"] for f in set(w["family"])})
    rates = {}
    for d in grid:
        rates[d] = {}
        for f in fams:
            ps = np.concatenate([pairs.minimum_effect_p(w[r][w["family"] == f], w[n][w["family"] == f], d)
                                 for w in negatives["raw"]])
            ps = ps[np.isfinite(ps)]
            rates[d][f] = float(np.mean(ps <= q)) if len(ps) else float("nan")
    ok = [d for d in grid if max(v for v in rates[d].values() if np.isfinite(v)) <= q]
    return {"delta": min(ok) if ok else None, "rate_by_delta_and_family": rates}


def shifted(z: np.ndarray, k: int) -> np.ndarray:
    """A within-place negative: the series moved k periods (circularly) within each place."""
    return np.roll(z, k, axis=1)


# ---------------------------------------------------------------------- negatives for one field


def _nb_quantile(u: np.ndarray, mu: np.ndarray, phi: np.ndarray | float) -> np.ndarray:
    """The count with cumulative probability u under NB(μ, φ) (Poisson where φ is infinite)."""
    phi = np.broadcast_to(np.asarray(phi, dtype=float), mu.shape)
    out = np.zeros(mu.shape)
    live = mu > 0
    pois = live & ~np.isfinite(phi)
    out[pois] = stats.poisson.ppf(u[pois], mu[pois])
    nb = live & np.isfinite(phi)
    out[nb] = stats.nbinom.ppf(u[nb], phi[nb], phi[nb] / (phi[nb] + mu[nb]))
    return out


def negative_scores(z: np.ndarray, kind: str, rng: np.random.Generator, gen_basis: pairs.MoranBasis | None = None
                    ) -> np.ndarray:
    """A negative control for a single-field lens, made of the field's own standardised residuals
    z [U, T, ...] (§10.2). ``space``: MSR across places on the symmetric-normalised graph of
    ``gen_basis`` (a graph other than the lens's own), one sign vector shared by every year, so the
    spatial spectrum and the years' joint dependence stay and the places of compact clusters do not.
    ``time``: each place's series moved by its own k ∈ [2, T−2] years (circularly), so each place's
    dependence over time stays and its alignment with the other places does not."""
    U, T = z.shape[:2]
    if kind == "space":
        return gen_basis.randomise(z.reshape(U, -1), rng, shared=True).reshape(z.shape)
    if kind == "time":
        k = rng.integers(2, T - 1, size=U)
        idx = (np.arange(T)[None, :] + k[:, None]) % T
        return z[np.arange(U)[:, None], idx]
    raise ValueError(kind)


def counts_from_scores(s: surprise.Surprise, z: np.ndarray, seed_parts: tuple) -> surprise.Surprise:
    """The field with counts y* whose cumulative probability under its own predictive is Φ(z)."""
    y = _nb_quantile(special.ndtr(z), s.mu, s.phi)
    y = np.where(s.mu > 0, y, s.y)
    return with_counts(s, y, seed_parts)


def mark_surrogate(s: surprise.Surprise, z: np.ndarray) -> surprise.Surprise:
    """A mark field with y* = μ + z/√w on its informative cells (a Gaussian surrogate: z ~ N(0,1))."""
    has = s.w > 0
    y = np.where(has, s.mu + np.divide(z, np.sqrt(np.where(has, s.w, 1.0))), np.nan)
    zz = np.where(has, z, 0.0)
    return surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, special.ndtr(zz), zz, s.w, s.flags,
                             s.calibration, s.extras)


def scores_of(s: surprise.Surprise) -> np.ndarray:
    """Standardised residuals of a field, zero where a cell carries nothing."""
    ok = np.isfinite(s.z) & (s.w > 0) if s.extras.get("kind") == "mark" else np.isfinite(s.z)
    return np.where(ok, s.z, 0.0)


def lens_world(s: surprise.Surprise, kind: str, i: int, gen_basis: pairs.MoranBasis | None = None
               ) -> surprise.Surprise:
    """The i-th world for a lens on field ``s``: ``nb`` (y ~ NB(μ̂, φ̂), §10.4), or a negative control
    (``space`` / ``time``, §10.2) of its residuals; ``space_ns`` / ``time_ns`` first replace the residuals by
    their normal scores, so the real field's heavy tails (unmodelled shocks such as COVID-19) do not count
    as the lens's false leads."""
    parts = ("lens-world", s.field.id, s.tier, kind, i)
    rng = np.random.default_rng(config.seed(*parts))
    mark = s.extras.get("kind") == "mark"
    if kind == "nb":
        if mark:
            return mark_surrogate(s, rng.standard_normal(s.y.shape))
        return surrogate(s, parts)
    z0 = scores_of(s)
    if kind.endswith("_ns"):        # normal scores: the marginal made exactly N(0,1), the dependence kept
        kind = kind[:-3]
        live = z0 != 0
        z0 = z0.copy()
        z0[live] = special.ndtri((stats.rankdata(z0[live]) - 0.5) / live.sum())
    z = negative_scores(z0, kind, rng, gen_basis)
    return mark_surrogate(s, z) if mark else counts_from_scores(s, z, parts)


def group_world(y_g: np.ndarray, mu_g: np.ndarray, phi: float, kind: str, i: int, field_id: str,
                gen_basis: pairs.MoranBasis | None = None) -> np.ndarray:
    """A world for group disparity: counts by (place, year, group). ``nb``: y ~ NB(μ_g, φ); ``space``:
    MSR (shared signs over years and groups) of the field's own residuals against the B0 group pattern."""
    parts = ("group-world", field_id, kind, i)
    rng = np.random.default_rng(config.seed(*parts))
    if kind == "nb":
        return subset.replicate(mu_g, phi, rng)
    _, z = surprise.randomised_pit(y_g.reshape(-1), mu_g.reshape(-1), np.full(mu_g.size, phi),
                                   config.seed(*parts, "pit"))
    z = np.where(mu_g.reshape(-1) > 0, z, 0.0).reshape(y_g.shape)
    z2 = gen_basis.randomise(z.reshape(len(z), -1), rng, shared=True).reshape(z.shape)
    return np.where(mu_g > 0, _nb_quantile(special.ndtr(z2), mu_g, phi), 0.0)


def wilson_upper(k: int, n: int, conf: float = 0.95) -> float:
    """Upper limit of the Wilson interval for k of n."""
    if n == 0:
        return 1.0
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(min(centre + half, 1.0))


# ---------------------------------------------------------------------- the designed grid (§10.3, O5)

GRID_KINDS = ("place", "cluster", "region", "state", "macro")
GRID_SHAPES = ("spike", "step", "trend", "group")
GRID_THETAS = (1.1, 1.2, 1.5, 2.0, 3.0)
GRID_LOAD = 0.05     # a world's planted excess in any period, at most this share of the field's expected events then (beyond its first plant)
GRID_LENSES = ("outbreak", "change_point", "space_time", "spatial_cluster", "trend_divergence", "group_disparity")
MINIMUM_EFFECT_ARG = {"cell_excess": "rate_ratio", "excess": "rate_ratio", "excess_step": "rate_ratio",
                      "excess_level": "rate_ratio", "excess_trend": "rate_ratio", "step": "rate_ratio", "outbreak": "rate_ratio", "change_point": "rate_ratio", "space_time": "rate_ratio",
                      "spatial_cluster": "rate_ratio", "trend_divergence": "ratio", "group_disparity": "sd"}


@dataclass(frozen=True)
class Plant:
    """One planted departure: the field's mean multiplied by θ over ``places`` (indices) in periods [t0, t1).
    ``spike`` and ``step`` multiply by θ; ``trend`` rises log-linearly to θ at t1 − 1; ``group`` multiplies one
    age–sex cell ``group`` only."""
    kind: str
    shape: str
    theta: float
    places: tuple[int, ...]
    t0: int
    t1: int
    group: int | None = None

    def multiplier(self, T: int) -> np.ndarray:
        """[T] the multiplier's course over the series (1 outside the window)."""
        m = np.ones(T)
        if self.shape == "trend":
            n = self.t1 - self.t0
            m[self.t0:self.t1] = np.exp(np.log(self.theta) * np.arange(1, n + 1) / n)
        else:
            m[self.t0:self.t1] = self.theta
        return m

    def cells(self, U: int, T: int) -> np.ndarray:
        out = np.zeros((U, T), dtype=bool)
        out[np.ix_(np.asarray(self.places), np.arange(self.t0, self.t1))] = True
        return out


def _neighbours(U: int, edges: np.ndarray) -> list[list[int]]:
    nb: list[list[int]] = [[] for _ in range(U)]
    for a, b in edges:
        nb[int(a)].append(int(b))
        nb[int(b)].append(int(a))
    return nb


def grid_units(places: np.ndarray, edges: np.ndarray, kind: str) -> list[np.ndarray]:
    """The candidate loci of a kind, as arrays of place indices: every municipality, every municipality with its
    graph neighbours, every immediate region, state and macro-region; or a ``blob``, a connected cluster grown on the
    graph from each place to a log-uniform size between 3 and 300 places, adding a random frontier place at each step.
    Blobs follow no partition: a bench of administrative regions favours a method that reads those regions (the
    ladder of supports won the region plants of 2026-10-07 by matching them unit for unit)."""
    from . import gateway

    U = len(places)
    if kind == "place":
        return [np.array([u]) for u in range(U)]
    if kind == "cluster":
        return [np.unique([u, *n]) for u, n in enumerate(_neighbours(U, edges))]
    if kind == "blob":
        nb = _neighbours(U, edges)
        rng = np.random.default_rng(config.seed("grid-blobs", U))
        out = []
        for u in range(U):
            size = int(np.exp(rng.uniform(np.log(3), np.log(300))))
            members, frontier = {u}, set(nb[u])
            while len(members) < size and frontier:
                v = list(frontier)[int(rng.integers(len(frontier)))]
                members.add(v)
                frontier.discard(v)
                frontier.update(w for w in nb[v] if w not in members)
            out.append(np.array(sorted(members)))
        return out
    code = {"region": lambda: np.asarray(gateway.regions(places, "ibge_immediate_region")),
            "state": lambda: places // 10000, "macro": lambda: places // 100000}[kind]()
    return [np.nonzero(code == c)[0] for c in np.unique(code)]


def grid_design(kind: str, shape: str, units: list[np.ndarray], mu_ut: np.ndarray, mu_g: np.ndarray,
                edges: np.ndarray, rng: np.random.Generator, thetas: tuple[float, ...] = GRID_THETAS,
                load: float = GRID_LOAD, offset: int = 0) -> list[Plant]:
    """One world's plants of one kind and shape: disjoint loci, each kept a graph edge away from the others, θ cycled
    over ``thetas``, loci taken round-robin over five quantile bins of their expected events (so the sparsity axis is
    covered), while the planted excess in every period stays within ``load`` of the field's expected events in that
    period (so the plants move the shared national history little). The first plant is always
    taken, so a macro-region has a world of its own. Spikes last one period or three; steps and trend changes start
    in the series' second half and run to its end; a group plant is a one-period spike in one age–sex cell drawn by
    its share of the locus's expected events."""
    U, T = mu_ut.shape
    tot = np.array([mu_ut[r].sum() for r in units])
    ok = np.nonzero(tot > 0)[0]
    queues = [list(rng.permutation(b)) for b in np.array_split(ok[np.argsort(tot[ok])], min(5, len(ok))) if len(b)]
    nb = _neighbours(U, edges)
    taken = np.zeros(U, dtype=bool)
    budget, used, plants, q = load * mu_ut.sum(0), np.zeros(T), [], 0
    while any(queues):
        queue = queues[q % len(queues)]
        q += 1
        if not queue:
            continue
        rows = units[queue.pop()]
        if taken[rows].any():
            continue
        theta = float(thetas[(offset + len(plants)) % len(thetas)])     # ``offset``: the world's index, so one-plant worlds cycle θ too
        group = None
        if shape == "spike":
            dur = int(rng.choice([1, 3])) if T >= 3 else 1
            t0 = int(rng.integers(0, T - dur + 1))
            t1 = t0 + dur
        elif shape in ("step", "trend"):
            t0, t1 = int(rng.integers(T // 2, max(T // 2 + 1, T - 1))), T
        else:
            t0 = int(rng.integers(0, T))
            t1 = t0 + 1
            share = mu_g[rows, t0].sum(0)
            if share.sum() <= 0:
                continue
            group = int(rng.choice(len(share), p=share / share.sum()))
        window = mu_ut[rows].sum(0) if group is None else mu_g[rows, :, group].sum(0)
        excess = (Plant(kind, shape, theta, (), t0, t1).multiplier(T) - 1.0) * window      # [T]
        if plants and np.any(used + excess > budget):
            continue
        plants.append(Plant(kind, shape, theta, tuple(int(r) for r in rows), t0, t1, group))
        used += excess
        taken[rows] = True
        taken[[v for r in rows for v in nb[int(r)]]] = True
    return plants


def grid_world(m: Any, leaves: np.ndarray, plants: list[Plant], rng: np.random.Generator,
               noise: surprise.Noise | None = None, phi_field: np.ndarray | None = None) -> Any:
    """The block's counts drawn from its fit, y ~ NB(μ', φ) cell by cell (leaf × place × period × age–sex), where μ'
    is the fit's mean with the plants' multipliers on the field's ``leaves``. The background is the model's own
    world, so what a lens finds outside the plants is a false lead. With the field's ``noise`` structure (N1) and its
    place × period dispersion ``phi_field``, the field's own leaves are drawn as Poisson under one lognormal frailty per
    (place, period), log-variance κ·log(1 + 1/φ) and AR(1) over periods (`surprise.replicate_correlated`'s law), so the
    field's totals carry the predictive's marginal and its serial dependence."""
    import dataclasses

    import torch

    d = m.data
    U, T, G = d.N.shape
    mult = np.ones((U, T, G))
    for p in plants:
        rows = np.asarray(p.places)
        course = p.multiplier(T)[None, :]
        if p.group is None:
            mult[rows] *= course[:, :, None]
        else:
            mult[rows, :, p.group] *= course
    inside = {int(e) for e in leaves}
    frail = None
    if noise is not None and not noise.null and phi_field is not None:
        frail = surprise.frailty(phi_field, noise, rng)
        mult = mult * frail[:, :, None]

    def leaf(args):
        e, r = args
        with torch.no_grad():
            mu = m.expected_by_group(np.array([e]))
        y = subset.replicate(mu * mult if e in inside else mu, np.inf if (frail is not None and e in inside) else m.phi, r)
        u, t, g = np.nonzero(y)
        return np.full(len(u), e), u, t, g, y[u, t, g]

    # leaves drawn on threads, each from its own child generator (the draws release the GIL: 4x on 8 threads)
    with ThreadPoolExecutor(8) as pool:
        parts = list(pool.map(leaf, zip(range(len(d.leaves)), rng.spawn(len(d.leaves)), strict=True)))
    e, u, t, g, y = (np.concatenate(z) for z in zip(*parts, strict=True))
    return dataclasses.replace(d, e=e, u=u, t=t, g=g, y=y, key={**d.key, "world": True})


def _score(plants: list[Plant], found: list, places: np.ndarray, periods: np.ndarray, U: int
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every plant against every finding at once (both are a place set × a window of periods): the best finding's
    (precision, recall) per plant, and whether each finding touches a plant. A finding over the whole series, or with
    no periods (spatial cluster, trend divergence, group disparity: place-level lenses), is compared on places alone;
    a cell comparison would cap its precision at the plant's share of the series."""
    import scipy.sparse as sp

    P, F = len(plants), len(found)
    if P == 0 or F == 0:
        return np.zeros(P), np.zeros(P), np.zeros(F, dtype=bool)
    index = {int(c): k for k, c in enumerate(places)}
    pr = [(k, u) for k, p in enumerate(plants) for u in p.places]
    Pm = sp.csr_matrix((np.ones(len(pr)), ([a for a, _ in pr], [b for _, b in pr])), shape=(P, U))
    fr = [(k, index[int(c)]) for k, f in enumerate(found) for c in f.locus.get("places", []) if int(c) in index]
    Fm = sp.csr_matrix((np.ones(len(fr)), ([a for a, _ in fr], [b for _, b in fr])), shape=(F, U))
    inter = (Pm @ Fm.T).toarray()                                       # shared places [P, F]
    np_, nf = np.asarray(Pm.sum(1)).ravel(), np.asarray(Fm.sum(1)).ravel()
    p0, p1 = np.array([p.t0 for p in plants]), np.array([p.t1 for p in plants])
    f0, f1, whole = np.zeros(F, int), np.full(F, len(periods)), np.ones(F, dtype=bool)
    for k, f in enumerate(found):
        yrs = f.locus.get("years")
        if yrs and not (yrs[0] <= periods[0] and yrs[-1] >= periods[-1]):
            f0[k], f1[k], whole[k] = np.searchsorted(periods, yrs[0]), np.searchsorted(periods, yrs[-1], "right"), False
    ov = np.clip(np.minimum(p1[:, None], f1[None]) - np.maximum(p0[:, None], f0[None]), 0, None)
    cells = inter * ov
    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(whole[None], inter / nf[None], cells / (nf * (f1 - f0))[None])
        rec = np.where(whole[None], inter / np_[:, None], cells / (np_ * (p1 - p0))[:, None])
    prec, rec = np.nan_to_num(prec), np.nan_to_num(rec)
    best = np.argmax(prec + 1e-9 * rec, axis=1)
    return prec[np.arange(P), best], rec[np.arange(P), best], (inter > 0).any(0)


def grid(session: Any, node: str, kinds: tuple[str, ...] = GRID_KINDS, shapes: tuple[str, ...] = GRID_SHAPES,
         lens_names: tuple[str, ...] = GRID_LENSES, worlds: int = 4, thetas: tuple[float, ...] = GRID_THETAS,
         replicates: int = 100, null_worlds: int = 0, minimum_effects: dict[str, tuple] | None = None,
         tiers: dict[str, tuple] | None = None, weighted: tuple[bool, ...] = (True,), sink: str | None = None,
         log=print) -> dict[str, Any]:
    """The designed grid of ARCHITECTURE §10.3 for one field: for each (kind, shape), ``worlds`` worlds of disjoint
    plants (`grid_design`), each drawn from the fit (`grid_world`), refitted (`monolith.Monolith.refit`) and read by the production
    lenses (`tools.Session.scan` on a sandbox ledger); and ``null_worlds`` worlds with no plant. Per plant and lens:
    whether a finding lies at least half inside it (detected), the best finding's precision and recall, the plant's
    expected events, and the effect the refitted B1 expectation leaves there against the planted one. Per world and
    lens: the findings that touch no plant (false leads). ``minimum_effects`` runs a lens at each of several minimum
    effects θ0 (`MINIMUM_EFFECT_ARG`; None, the production value): the calibration of §10.5; ``tiers`` at several
    expectation tiers (None, the lens's own: `tools.LENS_TIERS`), which tells a lens's weakness from its tier's
    absorption. ``sink`` (a path) gets
    each world's rows as a JSON line when the world ends, so a long run that fails keeps its finished worlds. Kept in
    the store (kind ``grid``)."""
    from . import control, tools

    ex = session.expectations
    f = ex.field(node)
    m = ex.model(f.block)
    leaves = np.array([m.data.leaves.index(c) for c in ex.registry.leaves(f.node) if c in m.data.leaves])
    places = m.data.places
    edges = session.edges()
    mu_g = m.expected_by_group(leaves)                                    # [U, T, G]
    mu_ut = mu_g.sum(2)
    U, T = mu_ut.shape
    sess = tools.Session(session.dataset, session.event, session.years, session.graph, source=session.source,
                         ledger=control.Ledger(config.home() / "harness" / "grid_ledger"))
    s_orig = session.surprise(node, "B1")                                 # the field's noise structure (N1)
    phi_field = np.broadcast_to(np.asarray(s_orig.phi, dtype=float), (U, T))
    rows, false_rows = [], []
    plans = [(k, s, worlds) for k in kinds for s in shapes] + ([("null", "none", null_worlds)] if null_worlds else [])
    done = 0
    for kind, shape, n in plans:
        units = [] if kind == "null" else grid_units(places, edges, kind)
        for w in range(n):
            rng = np.random.default_rng(config.seed("grid", f.id, kind, shape, w))
            plants = [] if kind == "null" else grid_design(kind, shape, units, mu_ut, mu_g, edges, rng, thetas, offset=w)
            t0 = time.time()
            sess.expectations._models = {f.block: m.refit(grid_world(m, leaves, plants, rng, s_orig.noise, phi_field))}
            sess._local.memo = {}                                           # each tier once per world
            s1 = sess.surprise(node, "B1")
            periods = np.asarray(s1.years)
            per_plant = []                                                   # what does not depend on the lens
            for p in plants:
                c = p.cells(U, T)
                base = mu_ut if p.group is None else mu_g[..., p.group]
                obs, exp_ = s1.y[c].sum(), s1.mu[c].sum()
                planted = mu_ut + base * (p.multiplier(T)[None, :] - 1.0)      # the field's mean with the plant, all groups
                per_plant.append({"theta": p.theta, "periods": p.t1 - p.t0, "places": len(p.places), "group": p.group,
                                  "expected": float(base[c].sum()),
                                  # on the field's total, like the seen ratio (a group plant's own ratio is θ itself)
                                  "true_log_ratio": round(float(np.log(planted[c].sum() / mu_ut[c].sum())), 4),
                                  "seen_log_ratio": round(float(np.log(max(obs, 0.5) / exp_)), 4) if exp_ > 0 else None})
            runs = [(x, t, tr, wt) for x in lens_names for t in (minimum_effects or {}).get(x, (None,))
                    for tr in (tiers or {}).get(x, (None,)) for wt in (weighted if x == "outbreak" else (False,))]
            for lens, theta0, tier, wt in runs:
                kw = {"replicates": replicates} if lens in ("space_time", "spatial_cluster") else {}
                if theta0 is not None:
                    kw[MINIMUM_EFFECT_ARG[lens]] = theta0
                if tier is not None:
                    kw["tier"] = tier
                if lens == "outbreak":
                    kw["weighted"] = wt
                try:
                    found = sess.scan(node, lens, **kw)
                except (ValueError, NotImplementedError) as err:
                    log(f"  {lens}: {err}")
                    continue
                prec, rec, touched = _score(plants, found, places, periods, U)
                for pc, pr_, rc in zip(per_plant, prec, rec, strict=True):
                    rows.append({"lens": lens, "theta0": theta0, "tier": tier, "weighted": wt, "kind": kind, "shape": shape, "world": w, **pc,
                                 "detected": bool(pr_ >= 0.5), "precision": round(float(pr_), 3), "recall": round(float(rc), 3)})
                false_rows.append({"lens": lens, "theta0": theta0, "tier": tier, "weighted": wt, "kind": kind, "shape": shape, "world": w, "findings": len(found),
                                   "false": int((~touched).sum())})
            sess.expectations._models, sess._local.memo = {}, None
            gc.collect()
            if sink:
                with open(sink, "a", encoding="utf-8") as fh:
                    mine = [x for x in false_rows if (x["kind"], x["shape"], x["world"]) == (kind, shape, w)]
                    fh.write(json.dumps({"kind": kind, "shape": shape, "world": w, "rows": rows[done:], "false": mine},
                                        default=float) + "\n")
                done = len(rows)
            log(f"{f.id} {kind}/{shape} world {w}: {len(plants)} plants, {time.time() - t0:.0f}s")
    out = {"field": f.id, "block": f.block, "kinds": list(kinds), "shapes": list(shapes), "lenses": list(lens_names),
           "worlds": worlds, "null_worlds": null_worlds, "thetas": list(thetas), "load": GRID_LOAD, "rows": rows,
           "false": false_rows}
    record("grid", {"field": f.id, "kinds": list(kinds), "shapes": list(shapes), "lenses": list(lens_names),
                    "worlds": worlds, "null_worlds": null_worlds, "years": list(session.years),
                    **({"minimum_effects": {k: list(v) for k, v in minimum_effects.items()}} if minimum_effects else {}),
                    **({"tiers": {k: list(v) for k, v in tiers.items()}} if tiers else {})}, out)
    return out


def surface(rows: list[dict], power: float = 0.8, at: tuple[float, ...] = (10, 100, 1000, 10000)) -> dict[str, Any]:
    """Each (lens, θ0, tier, kind, shape)'s power surface: a logistic regression of detection on log(θ − 1) and the plant's log
    expected events, and from it the minimum detectable rate ratio at ``power`` for the expected counts ``at``.
    A cell where every plant was detected, or none, reports its counts only."""
    import statsmodels.api as sm

    out: dict[str, Any] = {}
    def key_of(r: dict) -> tuple:
        return r["lens"], str(r.get("theta0")), str(r.get("tier")), r["kind"], r["shape"]

    for key in sorted({key_of(r) for r in rows}):
        sel = [r for r in rows if key_of(r) == key and r["expected"] > 0]
        det = np.array([r["detected"] for r in sel], dtype=float)
        rec: dict[str, Any] = {"plants": len(sel), "detected": int(det.sum()),
                               "by_theta": {str(t): round(float(np.mean([r["detected"] for r in sel if r["theta"] == t])), 3)
                                            for t in sorted({r["theta"] for r in sel})}}
        if 0 < det.sum() < len(det):
            X = sm.add_constant(np.column_stack([np.log([r["theta"] - 1 for r in sel]),
                                                 np.log([r["expected"] for r in sel])]))
            try:
                a, b, c = sm.Logit(det, X).fit(disp=0).params
            except Exception as err:  # noqa: BLE001 -- perfect separation and the like: the counts stand alone
                rec["fit"] = str(err)[:80]
            else:
                logit = np.log(power / (1 - power))
                rec["coef"] = [round(float(x), 3) for x in (a, b, c)]
                rec["mde"] = {str(n): round(float(1 + np.exp((logit - a - c * np.log(n)) / b)), 3) for n in at} if b > 0 else {}
        out["|".join(key)] = rec
    return out


def record(kind: str, key: dict[str, Any], result: dict[str, Any]) -> None:
    """Keep a harness result in the store (the evaluation entry cites its address)."""
    store.put_table("harness", {"kind": kind, **key}, pa.table({"result": [json.dumps(result, default=str)]}),
                    {"kind": kind, **key})


def absorbed(rows: list[dict]) -> dict[str, Any]:
    """The bias of the effect a refitted world shows at each kind and shape of plant (§10.3's third output): the share
    of the planted log ratio the refit took, 1 − seen / planted, as its median and quartiles over the plants (one
    lens's rows: the effect does not depend on the lens)."""
    lens = rows[0]["lens"] if rows else None
    out: dict[str, Any] = {}
    for key in sorted({(r["kind"], r["shape"]) for r in rows}):
        a = np.array([1 - r["seen_log_ratio"] / r["true_log_ratio"] for r in rows
                      if (r["kind"], r["shape"]) == key and r["lens"] == lens and r["seen_log_ratio"] is not None
                      and r["true_log_ratio"] > 0 and r["expected"] >= 100])
        if len(a):
            out["|".join(key)] = {"plants": len(a), "median": round(float(np.median(a)), 3),
                                  "quartiles": [round(float(x), 3) for x in np.percentile(a, [25, 75])]}
    return out


# ---------------------------------------------------------------------- documented events as held-out checks (§10.1)

DATASET_ALIAS = {"SINASC": ("SINASC-DN", "birth"), "SIH.RD": ("SIH-RD", "hospitalisation")}


def _served(p: Positive) -> tuple[str, str]:
    """The session's dataset and event of a declaration (older ones name SINAN families with a dot)."""
    if p.dataset in DATASET_ALIAS:
        return DATASET_ALIAS[p.dataset]
    return p.dataset.replace("SINAN.", "SINAN-"), p.event


def _area(spec: str):
    """A declaration's locus as a test on municipality codes, or None when a script derives it."""
    kind, _, codes = spec.partition(":")
    if kind not in ("uf", "ibge_macroregion", "mun"):
        return None
    if codes == "*":
        return lambda p: np.ones(len(p), dtype=bool)
    vals = [int(c) for c in codes.split(",")]
    div = {"uf": 10000, "ibge_macroregion": 100000, "mun": 1}[kind]
    return lambda p: np.isin(np.asarray(p, dtype=np.int64) // div, vals)


def event_record(positives: tuple[Positive, ...] = POSITIVES, years: list[int] | None = None, grains=("year",),
                 log=print) -> list[dict[str, Any]]:
    """Every method of every built question against the documented positives (§10.1; the methods' records of
    docs/plans/2026-10-07-questions-and-methods.md): per positive and method, whether a finding meets the event
    criterion (its years overlapping the event's, half its places or more in the event's area, of a shape the
    question takes, `questions._shape` where the method states none), the matching finding, and how many findings
    the field had. A positive whose question is not built yet, whose locus a script derives, or whose dataset is not
    served is recorded with that status, never dropped. Kept in the store (kind ``event_record``)."""
    from . import questions, tools

    years = list(range(2010, 2024)) if years is None else years
    sessions: dict = {}
    out = []
    for p in positives:
        rec: dict[str, Any] = {"name": p.name, "question": p.question, "dataset": p.dataset, "node": p.node,
                               "places": p.places, "years": list(p.years)}
        out.append(rec)
        qn = questions.QUESTIONS.get(p.question)
        area = _area(p.places)
        if p.question in ("relation", "explanation"):
            rec["status"] = (f"a {p.question} positive: scored by stage {'D' if p.question == 'relation' else 'E'}'s own "
                             "controls, not by this record of stage C")
        elif qn is None:
            rec["status"] = f"no method yet: the question {p.question!r} is not built"
        elif p.grain not in grains:
            rec["status"] = f"{p.grain} grain: not in this record"
        elif area is None:
            rec["status"] = "its locus is derived by a script (scripts/declare_positives.py)"
        if "status" in rec:
            log(f"{p.name}: {rec['status']}")
            continue
        ds, ev = _served(p)
        key = (ds, ev, p.grain)
        try:
            if key not in sessions:
                sessions[key] = tools.Session(ds, ev, years, source={"grain": p.grain} if p.grain != "year" else {})
            s = sessions[key]
        except Exception as exc:  # noqa: BLE001 - an unserved dataset is recorded, the record goes on
            rec["status"] = f"not served: {type(exc).__name__}: {exc}"
            log(f"{p.name}: {rec['status']}")
            continue
        rec["methods"] = {}
        for m in qn.methods:
            try:
                found = s.scan(p.node, m.id)
            except Exception as exc:  # noqa: BLE001 - one method's failure is its record
                rec["methods"][m.id] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            best = None
            for f in found:
                yrs = f.locus.get("years") or [years[0], years[-1]]
                pl = f.locus.get("places", [])
                if not pl or yrs[0] > p.years[1] or yrs[-1] < p.years[0] or area(pl).mean() < 0.5:
                    continue
                if "shape" not in f.stats:
                    f.stats["shape"] = questions._shape(s, p.node, f, "B1")
                shape = f.stats["shape"].get("shape", "unattributed")
                if qn.shapes and shape not in qn.shapes and shape != "unattributed":
                    continue
                if best is None or f.p < best.p:
                    best = f
            rec["methods"][m.id] = {"found": best is not None, "findings": len(found),
                                    "match": None if best is None else {
                                        "years": best.locus.get("years"), "places": len(best.locus.get("places", [])),
                                        "effect": round(float(best.effect), 2), "p": float(f"{best.p:.3g}"),
                                        "shape": best.stats.get("shape", {}).get("shape")}}
        rec["status"] = "scored"
        verdicts = []
        for k, v in rec["methods"].items():
            verdicts.append(f"{k} " + ("error" if "error" in v else "FOUND" if v["found"] else "missed"))
        log(f"{p.name}: " + ", ".join(verdicts))
    record("event_record", {"positives": [p.name for p in positives], "years": years, "grains": list(grains)},
           {"records": out})
    return out


def method_records(q: float = Q) -> dict[str, dict[str, Any]]:
    """Each method's record from what the harness measured and stored (ARCHITECTURE §10.5), never a hand-written
    table, and from each measurement's latest run only (a method fixed since an earlier run is not charged with it):
    per documented positive, the last record's verdict for the method (`event_record`); per field, the last grid that
    read the method (`grid`): its null worlds and how many held a finding, its false share in planted worlds. A
    method is ``calibrated`` when its null worlds hold findings no more often than max(q, 1/worlds), None when no null
    world has read it."""
    events: dict[tuple, tuple] = {}             # (method, positive) -> (written, found)
    grids: dict[tuple, tuple] = {}              # (method, field) -> (written, rows)
    for man in store.manifests("harness"):
        key = man.get("key") or {}
        kind = key.get("kind")
        if kind not in ("event_record", "grid"):
            continue
        table = store.get_table("harness", key)
        if table is None:
            continue
        written = man.get("written", "")
        result = json.loads(table.column("result")[0].as_py())
        if kind == "event_record":
            for rec in result.get("records", []):
                for m, v in (rec.get("methods") or {}).items():
                    if "found" in v and written >= events.get((m, rec["name"]), ("",))[0]:
                        events[(m, rec["name"])] = (written, bool(v["found"]))
        else:
            by_lens: dict[str, list] = {}
            for row in result.get("false", []):
                by_lens.setdefault(row["lens"], []).append(row)
            for lens, rows in by_lens.items():
                if written >= grids.get((lens, result.get("field")), ("",))[0]:
                    grids[(lens, result.get("field"))] = (written, rows)
    out: dict[str, dict[str, Any]] = {}
    for (m, _), (_, found) in events.items():
        r = out.setdefault(m, {})
        r["events_scored"] = r.get("events_scored", 0) + 1
        r["events_found"] = r.get("events_found", 0) + found
    for (m, _), (_, rows) in grids.items():
        r = out.setdefault(m, {})
        for row in rows:
            if row["kind"] == "null":
                r["null_worlds"] = r.get("null_worlds", 0) + 1
                r["null_worlds_with_findings"] = r.get("null_worlds_with_findings", 0) + (row["findings"] > 0)
            elif row["findings"]:
                r["planted_findings"] = r.get("planted_findings", 0) + row["findings"]
                r["planted_false"] = r.get("planted_false", 0) + row["false"]
    for r in out.values():
        n = r.get("null_worlds", 0)
        r["calibrated"] = (r["null_worlds_with_findings"] / n <= max(q, 1.0 / n)) if n else None
        if r.get("planted_findings"):
            r["false_share"] = round(r["planted_false"] / r["planted_findings"], 3)
    return out
