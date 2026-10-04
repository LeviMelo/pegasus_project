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
LOCUS_JACCARD = 0.5


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
    Positive("COVID-19 excess deaths, Amazonas", "SIM.DO", "death", "U07", "space_time", "B2", "uf:13",
             (2020, 2021), note="Manaus, January 2021; national 2020–21"),
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


def jaccard(a: set, b: set) -> float:
    return len(a & b) / max(len(a | b), 1)


def power_curve(s: surprise.Surprise, edges: np.ndarray, loci: list[np.ndarray], thetas: list[float],
                k: int = 30, max_window: int | None = 4, replicates: int = 100, alpha: float = Q,
                full_period: bool = False) -> dict[str, Any]:
    """Recovery of planted subsets by the space–time scan, per θ. A locus is a boolean [U, T]
    mask; recovered when the top subset reaches α and its cells overlap the locus with
    Jaccard ≥ 0.5. One null serves every injection (it depends on μ and φ only)."""
    scanner = subset.Scanner(subset.neighbourhoods(edges, len(s.places), k), max_window=max_window,
                             full_period=full_period)
    nul = subset.null(scanner, s.mu, s.phi, replicates, ("power", s.field.id, s.tier))
    rng = np.random.default_rng(config.seed("power", s.field.id, s.tier))
    curve = {}
    for theta in thetas:
        hits = 0
        for locus in loci:
            y = spike(_null_draw(s, rng), s.mu, locus, theta, rng)
            best = scanner.best(y, s.mu)
            if nul.p(best.score) > alpha:
                continue
            found = np.zeros_like(locus)
            found[np.ix_(best.places, np.arange(best.window[0], best.window[1] + 1))] = True
            hits += jaccard(set(zip(*np.nonzero(found), strict=True)), set(zip(*np.nonzero(locus), strict=True))) \
                >= LOCUS_JACCARD
        curve[float(theta)] = hits / max(len(loci), 1)
    return {"field": s.field.id, "tier": s.tier, "loci": len(loci), "curve": curve,
            "null": {"loc": nul.loc, "scale": nul.scale}}


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
    return surprise.Surprise(s.field, s.tier, s.places, s.years, y, s.mu, s.phi, u, z, s.w, s.flags,
                             s.calibration, s.extras)


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
        out["power"] = power_curve(s, edges, chosen, list(thetas), max_window=None if full else 4,
                                   replicates=replicates, full_period=full)
        log(f"  power {out['power']['curve']}")
    record("gate", {"field": s.field.id, "lens": lens, "tier": tier, "graph": session.graph,
                    "surrogates": surrogates, "loci": loci}, out)
    return out


def record(kind: str, key: dict[str, Any], result: dict[str, Any]) -> None:
    """Keep a harness result in the store (the evaluation entry cites its address)."""
    store.put_table("harness", {"kind": kind, **key}, pa.table({"result": [json.dumps(result, default=str)]}),
                    {"kind": kind, **key})
