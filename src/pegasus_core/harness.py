"""The validation harness (ARCHITECTURE §10): the test suite of a statistical search.

- Known positives: signals the literature and the surveillance record establish,
  each with the lens that should find it, its locus and a pass criterion.
- Planted signals: y' = y + Poisson((θ − 1)·μ_S) over a known locus S; recovery
  against θ is a lens's power curve.
- Null surrogates: y* ~ NB(μ̂, φ̂), independent across fields; whatever a lens
  finds there is its false-lead rate.
- Negative controls for pairs: surrogates that keep each field's dependence and
  remove the relation. Between places, Moran spectral randomisation (Wagner &
  Dray 2015) on the symmetric-normalised graph (``pairs.MoranBasis``): the
  field's coordinates in the Moran eigenvectors get random signs, so its
  spectrum is kept exactly. The raw weight matrix is not used: its eigenvectors
  localise and the surrogates lose long-range structure (evaluation 2026-10-05).
  Within places, the field's series shifted by k ≥ 2 years.
- The gate: a lens runs in production after recovering its positives, holding
  its false-lead rate ≤ q on surrogates, and publishing a power curve.

Results are tables in the store (``harness``), written up as evaluation entries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pyarrow as pa
from scipy import special, stats

from . import config, store, surprise
from .scans import pairs, subset

Q = 0.05


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


POSITIVES: tuple[Positive, ...] = (
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


# ---------------------------------------------------------------------- planted signals


def spike(y: np.ndarray, mu: np.ndarray, locus: np.ndarray, theta: float, rng: np.random.Generator) -> np.ndarray:
    """y' = y + Poisson((θ − 1)·μ) on the locus cells."""
    out = y.copy()
    out[locus] += rng.poisson(max(theta - 1, 0) * mu[locus])
    return out


def power_curve(s: surprise.Surprise, run_lens, loci: list[np.ndarray], thetas: list[float], mark: bool = False
                ) -> dict[str, Any]:
    """Recovery of planted signals by the production lens itself, per θ (§10.3). A locus is a
    boolean [U, T] mask; the signal y' = y* + Poisson((θ − 1)μ) is planted into a null background
    y* ~ NB(μ, φ), so recovery measures power, not real signals. A locus is recovered when some
    finding of the lens holds at least half of the locus's cells (recall) and at least half of its
    own cells are planted (precision). The lens's null is computed once per field and cached.

    An earlier version re-implemented the scan beside the lens (its own scanner, no minimum effect)
    and scored by cell Jaccard ≥ 0.5, which a correct two-year window over a one-year locus
    fails; it reported 10% power at θ = 2 for stroke (2026-10-04)."""
    rng = np.random.default_rng(config.seed("power", s.field.id, s.tier))
    curve, detail, rows_out = {}, {}, []
    for theta in thetas:
        hits = 0
        for locus in loci:
            hit = False
            if mark:        # a mark: the locus's mean log mark shifted by log θ (θ a weight ratio)
                y = mark_surrogate(s, rng.standard_normal(s.y.shape)).y
                y[locus] += np.log(theta)
                zz = np.where(s.w > 0, (y - s.mu) * np.sqrt(s.w), 0.0)
                planted = surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, special.ndtr(zz), zz,
                                            s.w, s.flags, s.calibration, s.extras)
            else:
                y = spike(_null_draw(s, rng), s.mu, locus, theta, rng)
                planted = surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, s.u, s.z, s.w,
                                            s.flags, s.calibration, s.extras)
            for f in run_lens(planted):
                found = np.zeros_like(locus)
                rows = np.isin(s.places, f.locus["places"])
                years = f.locus.get("years", [int(s.years[0]), int(s.years[-1])])
                cols = (s.years >= years[0]) & (s.years <= years[-1])
                found[np.ix_(rows, cols)] = True
                inter = (found & locus).sum()
                if inter >= 0.5 * locus.sum() and inter >= 0.5 * found.sum():
                    hit = True
                    break
            hits += hit
            rows_out.append((float(theta), float(np.nansum(np.where(s.w > 0, s.w, 0.0)[locus]) if mark
                                                 else s.mu[locus].sum()), hit))
        curve[float(theta)] = hits / max(len(loci), 1)
        detail[float(theta)] = hits
    # power depends on the expected count in the locus as much as on θ: report it by both
    bins = [0, 1e5, 1e6, 1e7, 1e8, np.inf] if mark else [0, 100, 300, 1000, 3000, np.inf]
    by_mu = {}
    for theta in thetas:
        for lo, hi in zip(bins[:-1], bins[1:], strict=True):
            sel = [h for t, mu, h in rows_out if t == theta and lo <= mu < hi]
            if sel:
                by_mu[f"θ={theta} μ∈[{lo},{hi})"] = (round(float(np.mean(sel)), 2), len(sel))
    return {"field": s.field.id, "tier": s.tier, "loci": len(loci), "curve": curve, "hits": detail,
            "by_expected": by_mu, "rows": rows_out}


def _null_draw(s: surprise.Surprise, rng: np.random.Generator) -> np.ndarray:
    """Plant into a null background (so recovery measures power, not real signals)."""
    return subset.replicate(s.mu, s.phi, rng)


def region_year_loci(places_region: np.ndarray, T: int, regions: list[str] | None = None,
                     length: int = 1) -> list[np.ndarray]:
    """Planted loci: every (region, window of ``length`` years) as a [U, T] mask."""
    out = []
    for r in regions or sorted(set(places_region)):
        rows = places_region == r
        for t0 in range(T - length + 1):
            m = np.zeros((len(places_region), T), dtype=bool)
            m[rows, t0:t0 + length] = True
            out.append(m)
    return out


# ---------------------------------------------------------------------- surrogates


def surrogate(s: surprise.Surprise, seed_parts: tuple) -> surprise.Surprise:
    """The same field with y ~ NB(μ, φ): a world where the model is true."""
    rng = np.random.default_rng(config.seed(*seed_parts))
    return with_counts(s, subset.replicate(s.mu, s.phi, rng), seed_parts)


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
                  "tau": tau}
    return surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, u, z, s.w, s.flags,
                             s.calibration, extras)


def trend_power(s: surprise.Surprise, run_lens, places: list[int], ratios: list[float],
                seed_parts: tuple = ("trend-power",)) -> dict[str, Any]:
    """Power of the trend lens: one place at a time, its expectation multiplied by a ratio θ between
    the period's first and last year (log-linear), y ~ NB around it, everything else null; the
    lens must report that place. Reported by θ and by the place's expected count."""
    rng = np.random.default_rng(config.seed(*seed_parts, s.field.id))
    yrs = s.years.astype(float)
    frac = (yrs - yrs.min()) / max(yrs.max() - yrs.min(), 1e-9) - 0.5
    rows = []
    for theta in ratios:
        for u in places:
            mu = s.mu.copy()
            mu[u] = s.mu[u] * np.exp(np.log(theta) * frac)
            y = subset.replicate(mu, s.phi, rng)
            found = run_lens(with_counts(s, y, (*seed_parts, theta, u)))
            hit = any(int(s.places[u]) in f.locus.get("places", []) for f in found)
            rows.append((float(theta), float(s.mu[u].sum()), hit))
    bins = [0, 30, 100, 300, 1000, np.inf]
    by = {}
    for theta in ratios:
        for lo, hi in zip(bins[:-1], bins[1:], strict=True):
            sel = [h for t, m, h in rows if t == theta and lo <= m < hi]
            if sel:
                by[f"θ={theta} μ∈[{lo},{hi})"] = (round(float(np.mean(sel)), 2), len(sel))
    return {"field": s.field.id, "curve": {float(t): round(float(np.mean([h for tt, _, h in rows if tt == t])), 2)
                                           for t in ratios}, "by_expected": by}


def false_lead_rate(run_lens, s: surprise.Surprise, surrogates: int = 20) -> dict[str, float]:
    """``run_lens(surprise) -> list of findings``, applied to NB surrogates of the field."""
    counts = [len(run_lens(surrogate(s, ("surrogate", s.field.id, s.tier, i)))) for i in range(surrogates)]
    return {"surrogates": surrogates, "mean_findings": float(np.mean(counts)),
            "share_with_any": float(np.mean(np.array(counts) > 0))}


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


COUNT_BANDS = [0, 3, 10, 30, 100, 300, 1000, np.inf]
MARK_BANDS = [0, 1e3, 3e3, 1e4, 3e4, 1e5, np.inf]


def cell_power(s: surprise.Surprise, run_lens, thetas: list[float], per_bin: int = 40, trailing: int = 1,
               seed_parts: tuple = ("cell-power",), mark: bool = False) -> dict[str, Any]:
    """Power of a per-place lens on planted loci (§10.3). For each band of the locus's expected
    count, ``per_bin`` places are planted at once into a null background: one cell (a random year)
    or, with ``trailing`` > 1, that many years at the end of the series, as y' = y* + Poisson((θ−1)μ).
    The field's B2 trends are refitted around the planted counts as in production (``with_counts``).
    A locus is recovered when a finding names its place (and, for one cell, its year). Planted loci
    are far apart in the 5,570-place field, so planting many at once does not change a locus's test.
    For a mark, θ is the weight ratio: y' = y + log θ, in bands of information (Σ w)."""
    rng = np.random.default_rng(config.seed(*seed_parts, s.field.id))
    U, T = s.y.shape
    usable = (s.flags & (surprise.DENOMINATOR | surprise.NO_INFORMATION)) == 0
    info = np.where(s.w > 0, s.w, 0.0) if mark else s.mu
    bands = MARK_BANDS if mark else COUNT_BANDS
    rows = []
    for theta in thetas:
        t_of, picks = {}, []
        for lo, hi in zip(bands[:-1], bands[1:], strict=True):
            tot = info[:, T - trailing:].sum(1) if trailing > 1 else info.max(1)
            cand = np.nonzero((tot >= lo) & (tot < hi) & usable[:, T - trailing:].all(1))[0]
            if len(cand):
                picks += [int(u) for u in rng.choice(cand, size=min(per_bin, len(cand)), replace=False)]
        base = mark_surrogate(s, rng.standard_normal(s.y.shape)) if mark else None
        y = base.y.copy() if mark else subset.replicate(s.mu, s.phi, rng)
        for u in picks:
            t = T - trailing if trailing > 1 else int(rng.choice(np.nonzero(usable[u])[0]))
            t_of[u] = t
            sl = slice(t, T) if trailing > 1 else slice(t, t + 1)
            if mark:
                y[u, sl] += np.log(theta)
            else:
                y[u, sl] += rng.poisson(max(theta - 1, 0) * s.mu[u, sl])
        if mark:
            zz = np.where(s.w > 0, (y - s.mu) * np.sqrt(s.w), 0.0)
            planted = surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, special.ndtr(zz), zz, s.w,
                                        s.flags, s.calibration, s.extras)
        else:
            planted = with_counts(s, y, (*seed_parts, theta))
        got: dict[int, list] = {}
        for f in run_lens(planted):
            for p_ in f.locus["places"]:
                got.setdefault(int(p_), []).append(f.locus.get("years"))
        for u in picks:
            hit = int(s.places[u]) in got
            if hit and trailing == 1:
                yr = int(s.years[t_of[u]])
                hit = any(yy is None or yy[0] <= yr <= yy[-1] for yy in got[int(s.places[u])])
            sl = slice(t_of[u], T) if trailing > 1 else slice(t_of[u], t_of[u] + 1)
            rows.append((float(theta), float(info[u, sl].sum()), bool(hit)))
    return _summarise(s, rows, thetas, bands)


def _summarise(s: surprise.Surprise, rows: list[tuple[float, float, bool]], thetas: list[float],
               bands: list[float]) -> dict[str, Any]:
    curve = {float(t): round(float(np.mean([h for tt, _, h in rows if tt == t])), 3) for t in thetas}
    by = {}
    for t in thetas:
        for lo, hi in zip(bands[:-1], bands[1:], strict=True):
            sel = [h for tt, m, h in rows if tt == t and lo <= m < hi]
            if sel:
                by[f"θ={t} [{lo:g},{hi:g})"] = (round(float(np.mean(sel)), 2), len(sel))
    return {"field": s.field.id, "tier": s.tier, "curve": curve, "by_expected": by, "rows": rows}


def group_power(y_g: np.ndarray, mu_g: np.ndarray, phi: float, places: np.ndarray, run_lens, thetas: list[float],
                per_bin: int = 40, seed_parts: tuple = ("group-power",)) -> dict[str, Any]:
    """Power of group disparity on planted places: in each, one group (drawn by its share of the
    place's expected events) has its expectation multiplied by θ, everything else null. Recovered
    when the lens reports the place; the curve is by θ and by the planted group's expected count."""
    rng = np.random.default_rng(config.seed(*seed_parts))
    Mg = mu_g.sum(1)                                              # [U, G]
    tot = Mg.sum(1)
    bands = [0, 30, 100, 300, 1000, 3000, np.inf]
    rows = []
    for theta in thetas:
        picks = []
        for lo, hi in zip(bands[:-1], bands[1:], strict=True):
            cand = np.nonzero((tot >= lo) & (tot < hi))[0]
            if len(cand):
                picks += [int(u) for u in rng.choice(cand, size=min(per_bin, len(cand)), replace=False)]
        mu = mu_g.copy()
        grp = {}
        for u in picks:
            g = int(rng.choice(Mg.shape[1], p=Mg[u] / Mg[u].sum()))
            grp[u] = g
            mu[u, :, g] *= theta
        hit_places = {p_ for f in run_lens(subset.replicate(mu, phi, rng)) for p_ in f.locus["places"]}
        for u in picks:
            rows.append((float(theta), float(Mg[u, grp[u]]), int(places[u]) in hit_places))
    curve = {float(t): round(float(np.mean([h for tt, _, h in rows if tt == t])), 3) for t in thetas}
    by = {}
    for t in thetas:
        for lo, hi in zip(bands[:-1], bands[1:], strict=True):
            sel = [h for tt, m, h in rows if tt == t and lo <= m < hi]
            if sel:
                by[f"θ={t} [{lo:g},{hi:g})"] = (round(float(np.mean(sel)), 2), len(sel))
    return {"curve": curve, "by_expected": by, "rows": rows}


# ---------------------------------------------------------------------- the gate


@dataclass
class GateRecord:
    lens: str
    positives: dict[str, bool] = field(default_factory=dict)
    false_lead_share: float | None = None
    power_curve: dict | None = None

    @property
    def open(self) -> bool:
        return (bool(self.positives) and all(self.positives.values()) and self.false_lead_share is not None
                and self.false_lead_share <= Q and self.power_curve is not None)


def run(session: Any, node: str, lens: str, surrogates: int = 20, loci: int = 40,
        thetas: tuple[float, ...] = (1.1, 1.25, 1.5, 2.0), replicates: int = 100, log=print) -> dict[str, Any]:
    """One lens on one field through the harness: its false-lead rate on NB surrogates and, for the
    subset lenses, its power curve on planted (immediate region × year) signals (§10.3–10.4).
    Surrogate tests go to the harness's own ledger, never the production one."""
    from . import config, control, gateway, tools
    from .scans import lenses

    tier = tools.LENS_TIERS[lens]
    s = session.surprise(node, tier)
    edges = session.edges()
    sandbox = control.Ledger(config.home() / "harness" / "ledger")
    runners = {
        "space_time": lambda x: lenses.space_time(x, edges, sandbox, replicates=replicates),
        "spatial_cluster": lambda x: lenses.spatial_cluster(x, edges, sandbox, replicates=replicates),
        "outbreak": lambda x: lenses.outbreak(x, sandbox),
        "change_point": lambda x: lenses.change_point(x, sandbox, replicates=replicates),
        "trend_divergence": lambda x: lenses.trend_divergence(x, edges, sandbox),
    }
    out: dict[str, Any] = {"field": s.field.id, "lens": lens, "tier": tier, "calibration": s.calibration}
    log(f"{s.field.id} {lens}: surrogates")
    out["false_leads"] = false_lead_rate(runners[lens], s, surrogates)
    log(f"  false leads {out['false_leads']}")
    if lens == "trend_divergence":
        rng = np.random.default_rng(config.seed("trend-loci", s.field.id))
        tot = s.mu.sum(1)
        candidates = np.nonzero(tot > 5)[0]
        chosen = rng.choice(candidates, size=min(loci, len(candidates)), replace=False).tolist()
        log(f"  trend power on {len(chosen)} places")
        out["power"] = trend_power(s, runners[lens], chosen, [1.2, 1.5, 2.0])
        log(f"  power {out['power']['curve']} {out['power']['by_expected']}")
    if lens in ("space_time", "spatial_cluster"):
        regions = gateway.regions(s.places, "ibge_immediate_region")
        full = lens == "spatial_cluster"
        candidates = region_year_loci(regions, len(s.years), length=len(s.years) if full else 1)
        rng = np.random.default_rng(config.seed("loci", s.field.id, lens))
        chosen = [candidates[i] for i in rng.choice(len(candidates), size=min(loci, len(candidates)), replace=False)]
        log(f"  power on {len(chosen)} loci")
        out["power"] = power_curve(s, runners[lens], chosen, list(thetas))
        log(f"  power {out['power']['curve']}")
    record("gate", {"field": s.field.id, "lens": lens, "tier": tier, "graph": session.graph,
                    "surrogates": surrogates, "loci": loci}, out)
    return out


def record(kind: str, key: dict[str, Any], result: dict[str, Any]) -> None:
    """Keep a harness result in the store (the evaluation entry cites its address)."""
    store.put_table("harness", {"kind": kind, **key}, pa.table({"result": [json.dumps(result, default=str)]}),
                    {"kind": kind, **key})
