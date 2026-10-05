"""The validation harness (ARCHITECTURE §10): the test suite of a statistical search.

- Known positives: signals the literature and the surveillance record establish,
  each with the lens that should find it, its locus and a pass criterion.
- Planted signals: y' = y + Poisson((θ − 1)·μ_S) over a known locus S; recovery
  against θ is a lens's power curve.
- Null surrogates: y* ~ NB(μ̂, φ̂), independent across fields; whatever a lens
  finds there is its false-lead rate.
- Negative controls for pairs: surrogates that keep each field's dependence and
  remove the relation. Between places, Moran spectral randomisation (Wagner &
  Dray 2015): the field's coordinates in the graph's Moran eigenvectors get
  random signs, so its spatial autocorrelation spectrum is kept exactly. Within
  places, the field's series shifted by k ≥ 2 years.
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
import scipy.sparse as sp

from . import config, store, surprise
from .scans import subset

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
)


# ---------------------------------------------------------------------- planted signals


def spike(y: np.ndarray, mu: np.ndarray, locus: np.ndarray, theta: float, rng: np.random.Generator) -> np.ndarray:
    """y' = y + Poisson((θ − 1)·μ) on the locus cells."""
    out = y.copy()
    out[locus] += rng.poisson(max(theta - 1, 0) * mu[locus])
    return out


def power_curve(s: surprise.Surprise, run_lens, loci: list[np.ndarray], thetas: list[float]) -> dict[str, Any]:
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
            rows_out.append((float(theta), float(s.mu[locus].sum()), hit))
        curve[float(theta)] = hits / max(len(loci), 1)
        detail[float(theta)] = hits
    # power depends on the expected count in the locus as much as on θ: report it by both
    bins = [0, 100, 300, 1000, 3000, np.inf]
    by_mu = {}
    for theta in thetas:
        for lo, hi in zip(bins[:-1], bins[1:], strict=True):
            sel = [h for t, mu, h in rows_out if t == theta and lo <= mu < hi]
            if sel:
                by_mu[f"θ={theta} μ∈[{lo},{hi})"] = (round(float(np.mean(sel)), 2), len(sel))
    return {"field": s.field.id, "tier": s.tier, "loci": len(loci), "curve": curve, "hits": detail,
            "by_expected": by_mu}


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
    y = subset.replicate(s.mu, s.phi, rng)
    u, z = surprise.randomised_pit(y, s.mu, s.phi, config.seed(*seed_parts, "pit"))
    extras = s.extras
    if "beta" in s.extras:
        # B2's place trends must be the surrogate's own, refitted around the B2 expectation (so a
        # trend lens tests the null, not the real data's trends again)
        yrs = s.years.astype(float)
        st = (yrs - yrs.mean()) / max(yrs.std(), 1e-9)
        _, b, sd, tau = surprise.refit_place(y, s.mu, s.phi, np.stack([np.ones_like(st), st], axis=1))
        extras = {**s.extras, "alpha": b[:, 0], "beta": b[:, 1], "alpha_sd": sd[:, 0], "beta_sd": sd[:, 1],
                  "tau": tau}
    return surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, u, z, s.w, s.flags,
                             s.calibration, extras)


def false_lead_rate(run_lens, s: surprise.Surprise, surrogates: int = 20) -> dict[str, float]:
    """``run_lens(surprise) -> list of findings``, applied to NB surrogates of the field."""
    counts = [len(run_lens(surrogate(s, ("surrogate", s.field.id, s.tier, i)))) for i in range(surrogates)]
    return {"surrogates": surrogates, "mean_findings": float(np.mean(counts)),
            "share_with_any": float(np.mean(np.array(counts) > 0))}


class MoranSpectrum:
    """Moran eigenvectors of a graph: the eigenvectors of the doubly-centred weight matrix."""

    def __init__(self, edges: np.ndarray, weights: np.ndarray | None, n: int):
        key = {"what": "moran_spectrum", "n": n, "edges": int(len(edges)),
               "hash": int(np.sum(edges[:, 0] * 7919 + edges[:, 1]))}
        hit = store.get_arrays("harness", key)
        if hit is None:
            w = np.ones(len(edges)) if weights is None else weights
            W = sp.coo_matrix((w, (edges[:, 0], edges[:, 1])), shape=(n, n)).toarray()
            W = np.maximum(W, W.T)
            H = np.eye(n) - 1.0 / n
            vals, vecs = np.linalg.eigh(H @ W @ H)
            hit = {"values": vals, "vectors": vecs}
            store.put_arrays("harness", key, hit)
        self.values, self.vectors = hit["values"], hit["vectors"]

    def randomise(self, x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """MSR (singleton variant): random signs on each Moran-eigenvector coordinate of x."""
        mean = x.mean()
        c = self.vectors.T @ (x - mean)
        return mean + self.vectors @ (c * rng.choice([-1.0, 1.0], size=len(c)))


def shifted(z: np.ndarray, k: int) -> np.ndarray:
    """A within-place negative: the series moved k periods (circularly) within each place."""
    return np.roll(z, k, axis=1)


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
