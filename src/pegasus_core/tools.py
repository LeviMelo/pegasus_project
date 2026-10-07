"""The interface for people and agents (ARCHITECTURE §9.3): a Python API first.

A `Session` binds one event type's fitted monolith (dataset, event, years,
graph) to the ledger and the lead register. Everything that tests something
goes through the ledger; everything admitted becomes a lead.

`survey` is the scheduled pass: every admissible field of each fitted block, the lenses at their tiers, error
control across families (Benjamini–Bogomolov, §8.2), and the admitted findings written to the register.

Replication is by units that took no part in the selection (`replication`, ARCHITECTURE §8.3): `train(last)` selects
on the years up to ``last`` and `temporal_confirm` tests the later years; `spatial_confirm` reads a unit claim in other jurisdictions and against how deaths are recorded (ADR-0019);
`corroborate` asks an independent record system; `confirm` is the agents' only
route to a claim: one test on the reserved period, under online FDR (LOND) whose state is read back from the
ledger. The event sides survive for sizes only: `honest_sizes`.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pyarrow as pa
from scipy import stats

from . import (
    config,
    control,
    corroborate,
    facility,
    fields,
    gateway,
    graphs,
    leads,
    monolith,
    relations,
    replication,
    store,
    surprise,
)
from .scans import explain, lenses
from .scans import scales as scales_mod

LENS_TIERS = {"cell_excess": "B1", "excess": "B1", "excess_step": "B1", "excess_trend": "B1", "step": "B1", "outbreak": "B1", "change_point": "B1", "trend_divergence": "B2", "space_time": "B1",
              "spatial_cluster": "B0", "group_disparity": "B0"}
# The lenses a prospective survey (``survey(prospective=t0)``, fit on the years up to t0) can run, with their tier
# (ADR-0012): the outbreak lens reads the ALARM BASELINE (BPA: a flat level that past epidemics do not enter, so an
# epidemic stays a departure), the others the calibrated EXPECTATION (BP: a regime mixture, for surprises).
PROSPECTIVE_TIERS = {"outbreak": "BPA", "change_point": "BP", "space_time": "BP"}
SCALE = {"cell_excess": "rate_ratio", "excess": "rate_ratio", "excess_step": "rate_ratio", "excess_trend": "rate_ratio", "step": "rate_ratio", "outbreak": "rate_ratio", "change_point": "rate_ratio", "trend_divergence": "sd",
         "space_time": "rate_ratio", "spatial_cluster": "rate_ratio", "group_disparity": "rate_ratio"}


# The survey's lens/estimand/scale combinations (ARCHITECTURE §10.5, O5): every one runs, and each lead carries its
# method's record (`method_record`) in place of v0's gate.
SURVEY_PLAN = (
    ("outbreak", None, ("municipality",)),
    ("change_point", None, ("municipality",)),
    ("trend_divergence", "national", ("municipality", "region", "state")),
    ("trend_divergence", "neighbours", ("municipality", "region", "state")),
    ("space_time", None, ("municipality",)),
    ("spatial_cluster", None, ("municipality",)),
    ("group_disparity", None, ("municipality", "region", "state")),
)

#: What the evidence says of a method where it runs: (lens, reference, dataset or None for any, calibrated, evidence).
#: The first match wins; a method with no entry is calibrated on the grid of ADR-0026/0027.
METHOD_EVIDENCE = (
    ("trend_divergence", None, "SIH-RD", False, "SIH trends: time-shift negatives find trends at every θ0, half of them "
                                                 "with the place × time interaction (ADR-0026; evaluation 2026-10-06, "
                                                 "minimum effects)"),
    ("trend_divergence", "neighbours", None, False, "the neighbours estimand recovers no documented positive "
                                                    "(evaluation 2026-10-05, lens positives)"),
    ("group_disparity", None, None, False, "fails its spatial negatives below sd 1.0 at the state (ARCHITECTURE §8.4)"),
    ("spatial_cluster", None, None, True, "θ0 1.5 on SIM, 2.0 on SIH: model worlds within q (ADR-0026)"),
    ("change_point", None, None, True, "the past course on B1, calibrated on three fields; sparse fields' time "
                                       "negatives fail (ADR-0027)"),
    ("outbreak", None, None, True, "B1, calibrated on three fields (ADR-0027)"),
)


def method_record(dataset: str, lens: str, reference: str | None, prospective: bool = False) -> dict[str, Any]:
    """The record a lead carries of its method (ARCHITECTURE §10.5): its tier, its minimum effect, whether its
    false-discovery rate is calibrated where it ran, and the evidence."""
    calibrated, evidence = True, "calibrated on the grid (ADR-0026)"
    for ln, ref, ds, cal, ev in METHOD_EVIDENCE:
        if ln == lens and (ref is None or ref == reference) and (ds is None or ds == dataset):
            calibrated, evidence = cal, ev
            break
    theta0 = lenses.GROUP_SD if lens == "group_disparity" else lenses.minimum_effect(lens, dataset + ":")
    return {"tier": lens_tier(lens, prospective), "theta0": theta0, "calibrated": calibrated, "evidence": evidence}


def lens_tier(lens: str, prospective: bool = False) -> str:
    """The expectation tier a lens reads: retrospective (`LENS_TIERS`) or, in a prospective survey, `PROSPECTIVE_TIERS`."""
    if not prospective:
        return LENS_TIERS[lens]
    if lens not in PROSPECTIVE_TIERS:
        raise ValueError(f"the {lens} lens has no prospective tier (one of {sorted(PROSPECTIVE_TIERS)})")
    return PROSPECTIVE_TIERS[lens]


FIT_YEARS = list(range(2010, 2024))      # the years of the production fits (the dependency map reads their calibration)
SURVEY_THREAD_GB = 0.5      # host memory one scanning thread adds over the loaded model (measured, evaluation 2026-10-05)


def survey_workers() -> int:
    """Threads for a survey: PEGASUS_SURVEY_WORKERS, else a quarter of the cores (at most 4), cut to what
    the free memory carries (this much per thread, and 3 GB left for the machine)."""
    if os.environ.get("PEGASUS_SURVEY_WORKERS"):
        return max(1, int(os.environ["PEGASUS_SURVEY_WORKERS"]))
    n = min(4, max(1, (os.cpu_count() or 4) // 4))
    try:
        import psutil

        n = min(n, max(1, int((psutil.virtual_memory().available / 2 ** 30 - 3) / SURVEY_THREAD_GB)))
    except ImportError:
        pass
    return n


@dataclass
class Session:
    dataset: str
    event: str
    years: list[int]
    graph: str = graphs.DEFAULT
    supply: bool = False          # the facility-supply term in every expectation (ADR-0016)
    rank: int = 0                 # the low-rank place x time interaction's R in every expectation (ADR-0021); 0: none
    source: dict = field(default_factory=dict)   # the event reader: {"grain": "month"} for the monthly grain
    ledger: control.Ledger = field(default_factory=control.Ledger)
    register: leads.Register = field(default_factory=leads.Register)
    _local: threading.local = field(default_factory=threading.local, init=False, repr=False)   # .memo: one field's tiers
    _edges: np.ndarray | None = field(default=None, init=False, repr=False)
    _scales: dict | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        control.check_reserved(self.dataset, self.years)     # the reserve is read by claims only (§8.3)
        self.expectations = surprise.Expectations(self.dataset, self.event, self.years, self.graph, source=self.source, supply=self.supply, rank=self.rank)

    # ---- reading ---------------------------------------------------------------

    def fields(self, block: str, lens: str | None = None) -> list[fields.Field]:
        """Every field of a fitted block with an event in the fit, top-down. No field is left out for low power
        (ARCHITECTURE §8.4, P9): a lens's BH runs within each field, so a weak field dilutes no other, and its leads
        carry their method's record. ``lens`` is accepted and unused."""
        m = self.expectations.model(block)
        reg = self.expectations.registry
        leaf = {c: i for i, c in enumerate(m.data.leaves)}
        events = np.bincount(m.data.e, weights=m.data.y, minlength=len(m.data.leaves))

        def has_events(node: str) -> bool:
            idx = [leaf[c] for c in reg.leaves(node) if c in leaf]
            return bool(idx) and events[idx].sum() > 0

        return reg.walk(block, has_events)

    def surprise(self, node: str, tier: str = "B1", train_last: int | None = None) -> surprise.Surprise:
        """The field's expectation at ``tier``; the prospective tiers (BP the expectation, BPA the alarm baseline,
        ADR-0012) are fitted on the years up to ``train_last``."""
        memo = getattr(self._local, "memo", None)       # set while a survey runs the lenses of one field
        key = (node, tier, train_last)
        if memo is not None and key in memo:
            return memo[key]
        if tier in ("BP", "BPA"):
            if train_last is None:
                raise ValueError(f"tier {tier} is fitted on the years up to a train_last")
            purpose = next(k for k, v in surprise.PURPOSE_TIER.items() if v == tier)
            s = self.expectations.prospective(node, train_last, purpose=purpose)
        else:
            s = self.expectations.surprise(node, tier)
        if memo is not None:
            memo[key] = s
        return s

    def calibration_of(self, node: str, tier: str = "B1") -> dict:
        """The field's calibration record at a tier (§6.2), kept in the store under the fit's key so a map need not
        refit the block's expectation to read it again."""
        m = self.expectations.model(self.expectations.field(node).block)
        key = {**m.key(), "field": f"{self.dataset}:{self.event}:{node}", "tier": tier, "what": "calibration", "v": 1}
        hit = store.manifest("calibration", key)
        if hit is not None and "calibration" in hit:
            return hit["calibration"]
        cal = self.surprise(node, tier).calibration
        store.put_table("calibration", key, pa.table({"ks": [float(cal["ks"])]}), {"calibration": cal})
        return cal

    def institutions(self, node: str) -> dict:
        """The institution lattice of a field (E_i, ADR-0016): its facilities' steps against their catchment's expectation
        (`facility.institution_lattice`), read on the B1 expectation without the supply term. Annual grain; SIH-RD, whose
        events all name a facility (SIM-DO's CODESTAB is empty for a death at home)."""
        su = self.expectations.surprise(node, "B1")
        codes = list(self.expectations.registry.leaves(node))
        p = facility.pairs(self.dataset, self.event, [int(y) for y in su.years], codes)
        return facility.institution_lattice(p, su.places, np.asarray(su.years), su.mu)

    def by_group(self, node: str) -> tuple[np.ndarray, np.ndarray]:
        """Observed and B0-expected counts by (place, year, group), B0 re-levelled per year and
        group to the **observed** national totals, so a place's group pattern is read against Brazil's
        observed one. (Re-levelled to the fitted model's own national totals it overstated women's
        share, 9.98% against 8.2% observed: the model's sex-age profile is smoothed and shrunk, so its
        national group totals depart from the data's; evaluation 2026-10-05, lens redesign.)"""
        f = self.expectations.field(node)
        m = self.expectations.model(f.block)
        reg = self.expectations.registry
        leaves = np.array([m.data.leaves.index(c) for c in reg.leaves(f.node) if c in m.data.leaves])
        y = m.observed_by_group(leaves)
        mu = m.expected_by_group(leaves, spatial=False)
        tot = y.sum(0)
        mu = mu * np.divide(tot, mu.sum(0), out=np.ones_like(tot), where=mu.sum(0) > 0)[None]
        return y, mu

    def exposure(self, sources: list[tuple[str, str]], per: float = 1000.0) -> np.ndarray:
        """[U, T] an exposure on this session's places and periods: the events of ``sources`` ((dataset, event) pairs,
        summed: e.g. the three arboviruses' notifications) by residence and period, per ``per`` residents, as
        log(1 + rate): an epidemic month's rate (tens per 1,000) makes a linear term's exp() explode and is no plausible
        dose–response. Monthly sessions count by the month of each event's date; a year a source has not published
        counts as none."""
        block = next(iter(self.expectations._models), None) or self._blocks()[0]
        d = self.expectations.model(block).data
        index = {int(p): i for i, p in enumerate(d.places)}
        monthly = d.grain == "month"
        x = np.zeros(d.N.shape[:2])
        y0 = int(d.years[0])
        for dataset, event in sources:
            for year in d.years:
                reader = gateway.monthly_counts if monthly else gateway.event_counts
                try:
                    t = reader(dataset, event, int(year), places=pa.array(d.places, pa.int32())).counts
                except LookupError:                      # nothing published for that year (NothingPublished)
                    continue
                rows = np.array([index.get(int(a), -1) for a in t.column("u").to_numpy()])
                yr = t.column("year").to_numpy()
                k = (yr - y0) * 12 + t.column("month").to_numpy() - 1 if monthly else yr - y0
                ok = (rows >= 0) & (k >= 0) & (k < x.shape[1])
                np.add.at(x, (rows[ok], k[ok]), t.column("y").to_numpy()[ok])
        residents = d.N.sum(2) * (12.0 if monthly else 1.0)        # person-months back to residents
        return np.log1p(np.divide(x * per, residents, out=np.zeros_like(x), where=residents > 0))

    def relation(self, node: str, exposure: np.ndarray, max_lag: int, scale: str = "ibge_immediate_region",
                 within: list[int] | None = None, reverse: bool = False) -> relations.LagCurve:
        """The distributed-lag relation of an exposure [U, T] (`exposure`) to field ``node``'s rate (ARCHITECTURE §7.5,
        `relations.distributed_lag`): both aggregated to ``scale`` (the exposure as a resident-weighted rate), the
        outcome read against its B1 expectation, NB at its block's dispersion. ``within`` keeps the units whose places
        lie in these macro-regions (1–5); ``reverse`` reverses time, so the regressor at lag ℓ is the exposure ℓ periods
        later (a negative control: the outcome leading its exposure)."""
        f = self.expectations.field(node)
        m = self.expectations.model(f.block)
        s1 = self.surprise(node, "B1")
        places = m.data.places
        unit = np.asarray(gateway.regions(places, scale)) if scale != "municipality" else places.astype(str)
        codes, uid = np.unique(unit, return_inverse=True)
        residents = m.data.N.sum(2)

        def agg(a: np.ndarray) -> np.ndarray:
            out = np.zeros((len(codes), a.shape[1]))
            np.add.at(out, uid, a)
            return out

        Y, M = agg(s1.y), agg(s1.mu)
        rate = np.expm1(exposure)                            # the unit's rate from its places' (`exposure` is log1p)
        X = np.log1p(np.divide(agg(rate * residents), agg(residents), out=np.zeros(M.shape), where=agg(residents) > 0))
        rows = None
        if within is not None:
            macro = np.array([int(str(places[np.nonzero(uid == k)[0][0]])[0]) for k in range(len(codes))])
            rows = np.nonzero(np.isin(macro, within))[0]
        if reverse:
            Y, M, X = Y[:, ::-1], M[:, ::-1], X[:, ::-1]
        return relations.distributed_lag(Y, M, X, max_lag, phi=m.phi, rows=rows)

    def held_out(self, node: str, places: list[int], years: list[int]) -> dict[str, Any]:
        """A locus's effect read against the fit with the locus held out (`monolith.Monolith.without`): observed
        against expected there, beside the in-sample ratio, and the upper tail of the observed total under the
        held-out NB predictive. In-sample, a fit absorbs 9–63 % of a departure's log ratio by its locus (ARCHITECTURE
        §10.3); this is the size a lead is reported at. ``places`` are municipality codes, ``years`` periods."""
        f = self.expectations.field(node)
        m = self.expectations.model(f.block)
        reg = self.expectations.registry
        leaves = np.array([m.data.leaves.index(c) for c in reg.leaves(f.node) if c in m.data.leaves])
        cells = np.outer(np.isin(m.data.places, places), np.isin(m.data.periods(), years))
        if not cells.any():
            raise LookupError(f"{node}: no cell of {places} × {years} in block {f.block}")
        y = m.observed(leaves)[cells].sum()
        mu_in = m.expected(leaves)[0][cells].sum()
        mu, mu2 = m.without(cells).expected(leaves)
        M, M2 = mu[cells].sum(), mu2[cells].sum()
        phi = surprise.aggregate_phi(np.array([M]), np.array([M2]), m.phi)
        p = lenses._upper_tail(np.array([y]), np.array([M]), phi)[0]
        return {"field": f.id, "cells": int(cells.sum()), "observed": float(y), "expected_in_sample": float(mu_in),
                "expected_held_out": float(M), "ratio_in_sample": float(y / mu_in) if mu_in > 0 else None,
                "ratio_held_out": float(y / M) if M > 0 else None, "p_held_out": float(p)}

    def expected(self, node: str, tier: str = "B1") -> dict[str, Any]:
        s = self.surprise(node, tier)
        return {"places": s.places, "years": s.years, "observed": s.y, "expected": s.mu}

    def edges(self) -> np.ndarray:
        """The graph over the session's places, built once. The places are the population's, the same in
        every block: an already loaded model gives them (loading another block's model for them cost
        minutes and gigabytes, survey profile 2026-10-05)."""
        if self._edges is None:
            block = next(iter(self.expectations._models), None) or next(iter(self._blocks()))
            self._edges = graphs.edges(self.expectations.model(block).data.places, self.graph)
        return self._edges

    def scales(self, names: tuple[str, ...] | list[str] | None = None) -> list[scales_mod.Scale]:
        """The scales (municipality, immediate region, state) over the session's places, built once; ``names`` picks."""
        if self._scales is None:
            block = next(iter(self.expectations._models), None) or next(iter(self._blocks()))
            self._scales = {x.name: x for x in scales_mod.standard(self.expectations.model(block).data.places)}
        return [self._scales[n] for n in (names or self._scales)]

    def spectrum(self):
        """The place graph's spectrum (`multiscale.GraphSpectrum`), built once per session."""
        if getattr(self, "_spectrum", None) is None:
            from . import multiscale
            block = next(iter(self.expectations._models), None) or next(iter(self._blocks()))
            places = self.expectations.model(block).data.places
            e, w = graphs.graph(places, self.graph)
            self._spectrum = multiscale.GraphSpectrum(e, len(places), w)
        return self._spectrum

    def _blocks(self) -> list[str]:
        return sorted({k["block"] for k in fitted(self.dataset, self.event, self.graph, self.years)})

    # ---- scanning ----------------------------------------------------------------

    def scan(self, node: str, lens: str, tier: str | None = None, scales: tuple[str, ...] | None = None,
             train_last: int | None = None, **kw) -> list[lenses.Finding]:
        """One lens on one field. ``scales`` (names; trend divergence and group disparity) default to the
        municipality; ``reference`` (trend divergence) to ``neighbours``. ``train_last`` makes the scan prospective:
        the lens reads its `PROSPECTIVE_TIERS` tier, fitted on the years up to it."""
        tier = tier or lens_tier(lens, train_last is not None)
        if scales:
            kw["scales"] = self.scales(scales)
        if lens == "group_disparity":
            y_g, mu_g = self.by_group(node)
            places = self.expectations.model(self.expectations.field(node).block).data.places
            phi = float(self.expectations.model(self.expectations.field(node).block).phi)
            return lenses.group_disparity(y_g, mu_g, places, self.expectations.field(node).id, self.ledger,
                                          **{"phi": phi, **kw})
        s = self.surprise(node, tier, train_last)
        if lens in ("cell_excess", "step") and "scales" not in kw:
            kw["scales"] = self.scales()              # the departure models run over the ladder of supports
        if lens == "cell_excess":                     # a departure model (stage C, O6)
            from . import departures
            return departures.cell_excess(s, self.ledger, **kw)
        if lens in ("excess", "excess_step", "excess_trend"):  # departures at unknown spatial scale (stage C, O6)
            from . import departures
            return departures.excess(s, self.ledger, self.spectrum(), shape=lens.partition("_")[2] or "spike", **kw)
        if lens == "step":                     # the step departure model (stage C, O6)
            from . import departures
            return departures.step(s, self.ledger, **kw)
        if lens in ("outbreak", "change_point"):
            return getattr(lenses, lens)(s, self.ledger, **kw)
        return getattr(lenses, lens)(s, self.edges(), self.ledger, **kw)

    def ask(self, question: str, node: str, q: float = 0.05, **kw) -> list:
        """A question of `questions.QUESTIONS` on one field: every method answering it at q/k, their findings merged
        into answers by overlapping loci, each naming the methods that agree (docs/plans/2026-10-07-questions-and-methods.md)."""
        from . import questions
        return questions.ask(self, question, node, q, **kw)

    def survey(self, blocks: list[str] | None = None, lens_names: tuple[str, ...] = ("outbreak", "change_point",
               "trend_divergence", "space_time", "group_disparity"), q: float = 0.05, replicates: int = 100, log=print,
               workers: int | None = None, prospective: int | None = None) -> list[leads.Lead]:
        """The scheduled pass over every field with events; returns the leads admitted. Every combination of
        `SURVEY_PLAN` runs, and each lead carries its method's record (`method_record`: tier, θ0, whether its
        false-discovery rate is calibrated where it ran). A call's scales are its multiplicity (BH within each
        scale at q / number of scales). Fields are scanned by ``workers`` threads (default `survey_workers`; 1: in
        order, in this thread) over the one loaded model; the lenses of a field share its tiers' expectations. The
        findings are merged in the fields' order, so the leads do not depend on the number of workers.
        ``prospective=t0`` runs the plan's prospective lenses (`PROSPECTIVE_TIERS`) on the years after t0 against a
        fit up to t0: the outbreak lens on the alarm baseline, the others on the calibrated expectation
        (ADR-0012). It is a different family from the retrospective survey; its leads carry ``train_last`` and
        ``purpose``, from which explanation, triage and replication rebuild the same prospective expectation."""
        if prospective is not None:
            lens_names = tuple(x for x in lens_names if x in PROSPECTIVE_TIERS)
        found: dict[str, list[lenses.Finding]] = {}
        log_lock = threading.Lock()
        calls = []                  # (lens, reference, scale names, family suffix)
        for lens, reference, scale_names in SURVEY_PLAN:
            if lens not in lens_names or (prospective is not None and reference):
                continue
            calls.append((lens, reference, scale_names, "|national" if reference == "national" else ""))

        def one(block: str, f: fields.Field) -> list[tuple[str, list[lenses.Finding]]]:
            self._local.memo = {}      # B2 serves three lenses: computed once per field
            out = []
            try:
                for lens, reference, scale_names, tag in calls:
                    kw = {"replicates": replicates} if lens in ("space_time", "spatial_cluster", "change_point") else {}
                    if lens in ("trend_divergence", "group_disparity"):
                        kw["scales"] = scale_names
                    if reference:
                        kw["reference"] = reference
                    name = " ".join(x for x in (lens, reference, "+".join(scale_names)) if x)
                    if prospective is not None:
                        kw["train_last"] = prospective
                    try:
                        hits = self.scan(f.node, lens, **kw)
                    except Exception as exc:  # noqa: BLE001 - a field that fails is reported, the survey goes on
                        with log_lock:
                            log(f"FAIL {f.id} {name}: {type(exc).__name__}: {exc}")
                        continue
                    out.append((f"{lens}|{lens_tier(lens, prospective is not None)}|{block}{tag}", hits))
                    with log_lock:
                        log(f"{f.id} {name}: {len(hits)}")
            finally:
                self._local.memo = None
            return out

        tasks = [(block, f) for block in blocks or self._blocks() for f in self.fields(block)]
        n = survey_workers() if workers is None else max(1, workers)
        self.edges()
        self.scales()
        if n > 1 and tasks:
            results = [one(*tasks[0])]                             # the first field warms the shared caches alone
            with ThreadPoolExecutor(n) as pool:
                results += pool.map(lambda t: one(*t), tasks[1:])
        else:
            results = [one(*t) for t in tasks]
        for res in results:
            for family, hits in res:
                found.setdefault(family, []).extend(hits)
        # error control across families: families selected by Simes, BH inside at the reduced level
        families = {k: np.array([h.p for h in v]) for k, v in found.items() if v}
        rejected = control.bogomolov(families, q)
        admitted = []
        for fam, mask in rejected.items():
            qv = control.adjusted(families[fam])
            admitted += leads.admit(found[fam], mask, qv, lambda h, qq, fam=fam: self._lead(h, qq, fam, prospective))
        self.register.add(admitted)
        return admitted

    def _lead(self, h: lenses.Finding, q: float, family: str, train_last: int | None = None) -> leads.Lead:
        return leads.Lead(kind="subset" if h.lens in ("space_time", "spatial_cluster") else "residual",
                          estimand=h.lens, tier=h.tier, fields=[h.field], locus=h.locus, effect=h.effect,
                          scale=SCALE[h.lens], interval=None, p=h.p, q=q, family=family,
                          null="Gumbel on NB replicates" if h.lens in ("space_time", "spatial_cluster", "change_point")
                          else "NB predictive",
                          calibrated=bool(h.stats.get("calibrated", True)), robustness={},
                          method=method_record(self.dataset, h.lens, h.stats.get("estimand"), train_last is not None),
                          train_last=train_last,
                          provenance={"graph": self.graph, "stats": h.stats})

    # ---- on demand -------------------------------------------------------------------

    def explain_away(self, lead: leads.Lead, candidate: np.ndarray, tier: str | None = None) -> explain.Explanation:
        """``candidate`` [U, T] over the session's places and years."""
        node = lead.fields[0].split(":")[-1]
        s = self.surprise(node, tier or lead.tier, lead.train_last)
        mask = np.zeros(s.y.shape, dtype=bool)
        pi = np.isin(s.places, lead.locus.get("places", s.places.tolist()))
        yrs = lead.locus.get("years", [int(s.years[0]), int(s.years[-1])])
        ti = (s.years >= yrs[0]) & (s.years <= yrs[-1])
        mask[np.ix_(pi, ti)] = True
        return explain.explain_away(s.y, s.mu, s.phi, candidate, mask)

    def decompose(self, node: str, first: int, second: int) -> dict[str, Any]:
        """Change in expected events from year ``first`` to ``second``: size, composition, place, risk."""
        f = self.expectations.field(node)
        m = self.expectations.model(f.block)
        reg = self.expectations.registry
        leaves = np.array([m.data.leaves.index(c) for c in reg.leaves(node) if c in m.data.leaves])
        mu = m.expected_by_group(leaves)
        t0, t1 = (int(np.nonzero(m.data.years == y)[0][0]) for y in (first, second))
        N0, N1 = m.data.N[:, t0], m.data.N[:, t1]
        r0 = np.divide(mu[:, t0], N0, out=np.zeros_like(N0), where=N0 > 0)
        r1 = np.divide(mu[:, t1], N1, out=np.zeros_like(N1), where=N1 > 0)
        return explain.decompose(N0, r0, N1, r1)

    # ---- triage and replication (§7.7, §8.3) ---------------------------------------------

    def triage(self, register: list[leads.Lead] | None = None, replicate: bool = True, write: bool = True,
               log=print, facility: bool = True, stale: bool = False) -> list[leads.Lead]:
        """Classify every open lead of the session's dataset by the data's own evidence (substitution, system
        artefact, noise, one institution's behaviour, signal; `explain.triage`) and run the replication of §8.3
        on the same arrays. ``facility`` reads each lead's events by recording institution (`facility`; SIH-RD
        names every admission's facility, SIM.DO only the deaths certified in one). The
        verdict goes to ``lead.robustness["triage"]``, the tier to ``lead.replication``; leads read as
        artefacts are marked `explained`. With ``write`` the new states are appended to the register.

        Each verdict carries the rules' version (`explain.RULES`). ``stale`` re-triages only the leads whose verdict
        was made by other rules (or none); a lead a superseded rule had explained is open again unless the new verdict
        explains it, and the old verdict is kept beside the new one."""
        mine = [x for x in (register if register is not None else self.register.current())
                if x.fields and x.fields[0].startswith(f"{self.dataset}:")]
        if stale:
            mine = [x for x in mine if x.robustness.get("triage", {}).get("rules") != explain.RULES]
        by_node: dict[tuple[str, int, str], list[leads.Lead]] = {}      # a prospective lead is read at its own fit and tier
        for x in mine:
            by_node.setdefault((x.fields[0].split(":")[-1], x.train_last or 0, x.tier if x.train_last else ""), []).append(x)
        edges = self.edges() if replicate else None
        fac = self._facilities() if facility else None
        if facility and fac is None:
            self._prepare_grid()
            log("facility read skipped: " + ("the cube is by year, the grain here is monthly" if self._per_year > 1
                                             else "the event names no facility classifier"))
        for i, ((node, train_last, tier), group) in enumerate(sorted(by_node.items())):
            ev = self._evidence(node)
            if fac is not None:
                block_codes = self._data(self.expectations.registry.chapter(node)).leaves
                lead_codes = [block_codes[j] for j in self._leaves(node)[1]]
            index = {int(p): j for j, p in enumerate(self._grid_places)}
            s = (self.surprise(node, tier, train_last) if train_last else self.surprise(node, "B1")) if replicate else None
            half = self._trend_halves(s, edges) if replicate and any(x.estimand == "trend_divergence" for x in group) else None
            for x in group:
                rows = np.array([index[int(p)] for p in x.locus.get("places", []) if int(p) in index], dtype=int)
                span, direction = replication.span_direction(x)
                st = x.provenance.get("stats", {})
                if x.estimand == "group_disparity":
                    ev.group_spread = explain.group_spread(*self._by_group_cells(node), rows)
                if fac is not None and rows.size:
                    ev.facility = fac.tally(self.expectations.registry.chapter(node), block_codes, lead_codes, rows)
                verdict = explain.triage(x.estimand, rows, span, direction, ev, st.get("observed"), st.get("expected"))
                old = x.robustness.get("triage")
                x.robustness = {**x.robustness, "triage": {"class": verdict.cls, "reason": verdict.reason,
                                                           "grade": verdict.grade or None, "bound": verdict.bound,
                                                           "rules": explain.RULES, **verdict.evidence,
                                                           **({"superseded": old} if old and old.get("rules") != explain.RULES else {})}}
                if verdict.grade == explain.TESTED and verdict.cls in (explain.SUBSTITUTION, explain.SYSTEM):
                    x.status = "explained"      # only a tested explanation takes a lead out; bound and consistent stay attached
                elif x.status == "explained":
                    x.status = "open"           # explained by a verdict the current rules do not repeat
                if replicate:
                    x.replications = {**x.replications, **self._replicate(x, s, rows, span, direction, half, edges)}
                    x.replication = control.replication_tier(kinds_of(x))
            log(f"{i + 1}/{len(by_node)} {node}{f' ({tier} fit to {train_last})' if train_last else ''}: {len(group)} leads")
        if write:
            self.register.add(mine)
        return mine

    def _facilities(self) -> facility.Facilities | None:
        """The facility cube of the session's years on the evidence grid (None: the dataset names no facility)."""
        if "_fac" not in self.__dict__:
            self._prepare_grid()
            self._fac = None
            if self._per_year == 1:         # the cube is by year: no facility read at the monthly grain (`triage` says so)
                with contextlib.suppress(LookupError):      # the event names no facility classifier (SINAN): nothing to read
                    self._fac = facility.Facilities(self.dataset, self.event, self.years, self._grid_places, self._grid_years)
        return self._fac

    def _prepare_grid(self) -> None:
        """Every fitted block's observed counts (all causes, the ill-defined chapter) on one grid."""
        if getattr(self, "_pop", None) is not None:
            return
        blocks = self._blocks()
        total = ill = pop = None
        for b in blocks:
            d = self._data(b)
            n = self._counts(d, np.arange(len(d.leaves)))
            total = n if total is None else total + n
            if b == "XVIII":
                ill = n
            pop = d.N.sum(2)
            self._grid_places, self._grid_years = d.places, d.periods()       # YYYYMM at the monthly grain
            self._per_year = 12 if d.grain == "month" else 1
        if blocks == ["*"]:
            total = ill = None      # an event type without a classifier tree has no all-cause count: the death-rate reads need one
        self._total, self._ill, self._pop = total, ill, pop

    def _data(self, block: str) -> monolith.BlockData:
        """A block's cells (`monolith.assemble`, which keeps them in the store)."""
        cache = self.__dict__.setdefault("_blocks_data", {})
        if block not in cache:
            cache[block] = monolith.assemble(self.dataset, self.event, block, self.years, **self.expectations._reader())
        return cache[block]

    @staticmethod
    def _counts(d: monolith.BlockData, leaves: np.ndarray, by_group: bool = False) -> np.ndarray:
        m = np.isin(d.e, leaves)
        U, T, G = d.N.shape
        if by_group:
            return np.bincount((d.u[m] * T + d.t[m]) * G + d.g[m], weights=d.y[m], minlength=U * T * G).reshape(U, T, G)
        return np.bincount(d.u[m] * T + d.t[m], weights=d.y[m], minlength=U * T).reshape(U, T)

    def _leaves(self, node: str) -> tuple[monolith.BlockData, np.ndarray]:
        reg = self.expectations.registry
        d = self._data(reg.chapter(node))
        pos = {c: i for i, c in enumerate(d.leaves)}
        return d, np.array([pos[c] for c in reg.leaves(node) if c in pos], dtype=int)

    def _evidence(self, node: str) -> explain.Evidence:
        self._prepare_grid()
        reg = self.expectations.registry
        d, leaves = self._leaves(node)
        y = self._counts(d, leaves)
        fam = leads.family(node)
        sib = None
        if reg.level.get(node) != "chapter" and fam != node and fam in reg.children:
            # the siblings: the family's other leaves (the family is the outermost group, `leads.family`)
            sl = np.setdiff1d(self._leaves(fam)[1], leaves)
            sib = self._counts(d, sl) if sl.size else None
        return explain.Evidence(self._grid_years, y, sib, self._ill, self._total, self._pop, chapter=reg.chapter(node),
                                residual=explain.residual_label(reg.label.get(node, "")), per_year=self._per_year)

    def _by_group_cells(self, node: str) -> tuple[np.ndarray, np.ndarray]:
        d, leaves = self._leaves(node)
        return self._counts(d, leaves, by_group=True), d.N

    def _trend_halves(self, s: surprise.Surprise, edges: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        """Per temporal half: every place's divergence from its neighbours' mean slope, per year, with its sd."""
        out = []
        for yrs in control.temporal_halves(s.years):
            cols = np.isin(s.years, yrs)
            x = (yrs - yrs.mean()) / max(yrs.std(), 1e-9)
            _, b, sd, _ = surprise.refit_place(s.y[:, cols], s.mu[:, cols], s.phi[:, cols], np.stack([np.ones_like(x), x], 1))
            n = len(b)
            A, S, V = np.zeros(n), np.zeros(n), np.zeros(n)
            for a, c in ((edges[:, 0], edges[:, 1]), (edges[:, 1], edges[:, 0])):
                np.add.at(A, a, b[c, 1])
                np.add.at(V, a, sd[c, 1] ** 2)
                np.add.at(S, a, 1)
            has = S > 0
            diff = (b[:, 1] - np.divide(A, S, out=np.zeros(n), where=has)) / max(yrs.std(), 1e-9)
            var = (sd[:, 1] ** 2 + np.divide(V, S ** 2, out=np.zeros(n), where=has)) / max(yrs.std(), 1e-9) ** 2
            out.append((np.where(has, diff, 0.0), np.sqrt(var)))
        return out

    def _replicate(self, x: leads.Lead, s: surprise.Surprise, rows: np.ndarray, span: list[int] | None,
                   direction: int, half, edges: np.ndarray) -> dict[str, Any]:
        """The recurrence of an effect (tier R2) and its spatial homogeneity, from the expectation of the fit on all
        years (splits of the evidence, not refits). Recurrence: the effect in the temporal half the window does not
        touch (a trend: in both halves). Homogeneity: the effect in both spatial halves of a subset's places, which
        were selected on the same data, so it is reported, not tiered. Same sign, at least half the effect,
        one-sided p < 0.05 (`control.replicates`). Neighbour support is recorded."""
        out: dict[str, Any] = {}
        if x.estimand == "group_disparity" or direction == 0:
            return {"untested": "no direction"}
        if x.estimand == "trend_divergence" and (leads.trend_reference(x) != "neighbours" or x.locus.get("scale")):
            return {"untested": "the trend replication reads a municipality's contrast with its neighbours"}
        if x.estimand == "trend_divergence" and rows.size:
            st = x.provenance["stats"]
            yrs = s.years.astype(float)
            full = (st["beta"] - st["neighbours"]) / max(yrs.std(), 1e-9)
            ps = []
            for (diff, sd), name in zip(half, ("first", "second"), strict=True):
                z = direction * diff[rows[0]] / max(sd[rows[0]], 1e-12)
                ps.append((direction * diff[rows[0]], float(stats.norm.sf(z))))
                out[name] = {"per_year": float(diff[rows[0]]), "p": ps[-1][1]}
            out["ok"] = control.replicates(float(abs(full)), *min(ps, key=lambda t: t[0]))
            out["full_per_year"] = float(full)
            return out
        sign, full = direction, abs(np.log(max(x.effect, 1e-12)))
        win = (s.years >= span[0]) & (s.years <= span[-1])
        first, second = control.temporal_halves(s.years)
        other = [np.isin(s.years, h) for h in (first, second) if not np.isin(s.years[win], h).any()]
        if other:
            eff, p = explain.split_effect(s.y, s.mu, s.phi, rows, other[0], sign)
            out["temporal"] = {"log_rr": eff, "p": p, "ok": control.replicates(full, sign * eff, p)}
        if len(rows) >= 2:
            if getattr(self, "_region_of", None) is None:       # 8 s a call: once per session
                self._region_of = dict(zip(s.places.tolist(), gateway.regions(s.places, "ibge_immediate_region"), strict=True))
            a, b = control.spatial_halves(s.places[rows], self._region_of)
            ia, ib = (np.nonzero(np.isin(s.places, h))[0] for h in (a, b))
            if ia.size and ib.size:
                parts = [explain.split_effect(s.y, s.mu, s.phi, r, win, sign) for r in (ia, ib)]
                weak = min(parts, key=lambda t: sign * t[0] if np.isfinite(t[0]) else -1e9)
                out["spatial"] = {"log_rr": [p[0] for p in parts], "p": [p[1] for p in parts],
                                  "ok": control.replicates(full, sign * weak[0] if np.isfinite(weak[0]) else 0.0, weak[1])}
        near = np.unique(np.concatenate([edges[edges[:, 0] == r, 1] for r in rows] +
                                        [edges[edges[:, 1] == r, 0] for r in rows] + [np.array([], dtype=int)]))
        near = near[~np.isin(near, rows)]
        if near.size:
            eff, p = explain.split_effect(s.y, s.mu, s.phi, near, win, sign)
            out["neighbours"] = {"log_rr": eff, "p": p}
        return out

    # ---- replication by independent units (§8.3) --------------------------------------------

    split_home = None      # (a Path) where the selecting sessions (side A, training years) keep their register and ledger

    def side(self, side: str) -> Session:
        """This session over one side of the events (`replication`): A explores and selects, with its own register
        and ledger (its tests are not the all-data denominator); E is read to size what A selected."""
        home = self.split_home or config.home()
        out = Session(self.dataset, self.event, self.years, self.graph,
                      ledger=control.Ledger(home / "ledger_A") if side == "A" else self.ledger,
                      register=leads.Register(home / "leads_A") if side == "A" else self.register)
        out.expectations = replication.SideExpectations(out.expectations, side)
        return out

    def train(self, last: int) -> Session:
        """This session over the years up to ``last``, with its own register and ledger: the survey that selects
        what the later years then test (`temporal_confirm`). Nothing after ``last`` is read."""
        home = self.split_home or config.home()
        return Session(self.dataset, self.event, [y for y in self.years if y <= last], self.graph,
                       ledger=control.Ledger(home / f"ledger_T{last}"), register=leads.Register(home / f"leads_T{last}"))

    def temporal_confirm(self, last: int, q: float = 0.05, level: str = "state", log=print) -> list[leads.Lead]:
        """The leads the survey selected on the years up to ``last`` (`train`), each tested once at its fixed places on the
        later years of this session, against a fit that ends at ``last`` (BP, the place's course not carried
        forward), re-levelled to the state's course of each year (`replication.relevel`); Benjamini-Hochberg over
        everything tested. The verdict is in ``lead.replications["prospective"]``. A one-off event does not
        recur: it stays untested here by nature, and needs corroboration."""
        t = self.train(last)
        selected = t.register.current()
        by_node: dict[str, list[leads.Lead]] = {}
        for x in selected:
            by_node.setdefault(x.fields[0].split(":")[-1], []).append(x)
        tested: list[tuple[leads.Lead, dict[str, Any]]] = []
        for i, (node, group) in enumerate(sorted(by_node.items())):
            try:
                sp = self.expectations.prospective(node, last, course=False)
            except LookupError as exc:
                tested += [(x, {"tested": False, "reason": str(exc)}) for x in group]
                continue
            tested += [(x, replication.test_lead(sp, x, level)) for x in group]
            log(f"{i + 1}/{len(by_node)} {node}: {len(group)} leads")
        self._record(tested, "prospective", q)
        t.register.add(selected)
        return selected

    def strata(self, source: str = "popsvs") -> replication.Strata:
        """The session's events by municipality, year, sex, age band and 4-character code, with the person-years of
        ``source`` (`replication.Strata`): what direct standardisation and the profile of a set of deaths read."""
        if "_strata" not in self.__dict__:
            self._strata = {}
        if source not in self._strata:
            self._strata[source] = replication.Strata.from_gateway(self.dataset, self.event, self.years, source)
        return self._strata[source]

    def spatial_confirm(self, register: list[leads.Lead], source: str = "popsvs", log=print) -> list[leads.Lead]:
        """The unit claims of ``register`` (a region's or state's trend against the national course, or a municipality's
        against its neighbours) read by `replication.audit` (ADR-0019): against the year's observed national rate, the
        unit's all-cause slope, conservation inside an ICD family, the shape of the change, and the other *jurisdictions*
        (`replication.jurisdiction`: a state claim must hold in other states, else it is one jurisdiction's and is not
        confirmed). Written to ``lead.robustness["artefact"]`` (the record, every recording explanation graded:
        ``explain.GRADES``), ``lead.replications["national"]`` and ``["spatial_unit"]`` (``ok``: the claim holds beyond its
        jurisdiction). A lead is dropped (``explained``) only when a *tested* explanation accounts for at least half of it and nothing remains at the conserved level (``rescoped`` otherwise: both reported)."""
        mine = [x for x in register if x.estimand == "trend_divergence" and x.locus.get("scale") and x.fields
                and x.fields[0].startswith(f"{self.dataset}:")]
        st = self.strata(source)
        tree = gateway.code_structure("ICD10").to_pandas().set_index("code")
        for i, x in enumerate(mine):
            last = x.train_last or max(self.years)
            span, direction = replication.span_direction(x)
            rec = replication.audit(st, x.locus["places"], x.fields[0].split(":")[-1], x.locus["scale"],
                                    x.provenance["stats"]["beta"], direction, [y for y in self.years if y <= last], tree,
                                    seed_text=x.id, later_years=[y for y in self.years if y > last])
            x.robustness = {**x.robustness, "artefact": rec}
            x.replications = {**x.replications, "national": rec["national"],
                              "spatial_unit": {"tested": True, **rec["jurisdiction"]}}
            if rec["verdict"] == "explained":
                x.status = "explained"          # nothing remains at any conserved level
            elif rec["verdict"] == "rescoped":
                x.status = "rescoped"           # the code-level shift is certification; the family-level claim stands (``robustness["artefact"]["rescope"]``)
            x.replication = control.replication_tier(kinds_of(x))
            if (i + 1) % 10 == 0:
                log(f"{i + 1}/{len(mine)} unit claims")
        return mine

    @staticmethod
    def _record(tested: list[tuple[leads.Lead, dict[str, Any]]], key: str, q: float, only=None) -> None:
        """Benjamini-Hochberg over the tests that ran (and ``only`` those, if given), written to each lead's ``replications[key]``."""
        ok = np.array([bool(r["tested"]) and (only is None or bool(only(r))) for _, r in tested], dtype=bool)
        p = np.array([r.get("p", 1.0) for _, r in tested])
        mask, qv = np.zeros(len(p), dtype=bool), np.ones(len(p))
        mask[ok] = control.bh(p[ok], q)
        qv[ok] = control.adjusted(p[ok])
        for (x, r), hit, qq in zip(tested, mask, qv, strict=True):
            x.replications = {**x.replications, key: {**r, "q": float(qq), "ok": bool(hit)}}
            x.replication = control.replication_tier(kinds_of(x))

    def honest_sizes(self, log=print) -> list[leads.Lead]:
        """The size of every lead selected on side A, read on side E (`replication.honest_effect`): a rate ratio and its
        exact Poisson interval, unbiased for the locus's realised rate whatever A selected. Written to
        ``lead.replications["honest"]``; it is a size, never a verdict."""
        a, e = self.side("A"), self.side("E")
        selected = a.register.current()
        by_node: dict[str, list[leads.Lead]] = {}
        for x in selected:
            by_node.setdefault(x.fields[0].split(":")[-1], []).append(x)
        for i, (node, group) in enumerate(sorted(by_node.items())):
            surprises: dict[tuple[str, int | None], surprise.Surprise] = {}
            for x in group:
                if (x.tier, x.train_last) not in surprises:
                    surprises[x.tier, x.train_last] = e.surprise(node, x.tier, x.train_last)
                x.replications = {**x.replications, "honest": replication.honest_effect(surprises[x.tier, x.train_last], x)}
            log(f"{i + 1}/{len(by_node)} {node}: {len(group)} leads")
        a.register.add(selected)
        return selected

    def corroborate(self, register: list[leads.Lead], only_signals: bool = True, replicates: int = 4999,
                    q: float = 0.05, log=print, refine_p: float = 0.01, refine_replicates: int = 99999) -> list[leads.Lead]:
        """Ask an independent field (S2iD, SINAN, SIH: `corroborate.RULES`) whether each lead's places and years are
        unusual there, against that field's own null (random same-size place sets of the same state and
        population quintile; a cluster of touching places is replaced by connected sets grown on the graph, `corroborate._null_sets`). Leads with p < ``refine_p`` are redrawn at ``refine_replicates`` so that Benjamini-Hochberg over many tests can reject. Benjamini-Hochberg within each source.
        Written to ``lead.replications["corroboration"]``."""
        self._prepare_grid()
        pop = self._pop.sum(1)
        state = (self._grid_places // 10000).astype(int)
        grid = corroborate.Fields(self._grid_places, self._grid_years, state, pop, self.edges())
        index = {int(p): j for j, p in enumerate(self._grid_places)}
        reg = self.expectations.registry
        done: list[tuple[leads.Lead, corroborate.Corroboration]] = []
        for x in register:
            tri = x.robustness.get("triage", {})
            if not x.fields or not x.fields[0].startswith(f"{self.dataset}:") or (
                    only_signals and (tri.get("grade") == explain.TESTED or ("grade" not in tri and tri.get("class") != explain.SIGNAL))):
                continue
            node = x.fields[0].split(":")[-1]
            span, direction = replication.span_direction(x)
            rows = np.array([index[int(u)] for u in x.locus.get("places", []) if int(u) in index], dtype=int)
            if rows.size == 0 or not span:
                continue
            c = corroborate.corroborate(grid, node, corroborate.categories_of(reg, node), rows, span, direction,
                                        f"corroborate|{x.id}", replicates, dataset=self.dataset)
            done.append((x, c))
            if len(done) % 200 == 0:
                log(f"corroborated {len(done)}")
        # a permutation p-value cannot fall below 1 / (replicates + 1), and Benjamini-Hochberg over m tests needs the best
        # to reach q / m: the promising ones are redrawn with many more replicates, so the tier is reachable
        for i, (x, c) in enumerate(done):
            if c.tested and c.p < refine_p and c.source:
                node = x.fields[0].split(":")[-1]
                span, direction = replication.span_direction(x)
                rows = np.array([index[int(u)] for u in x.locus["places"] if int(u) in index], dtype=int)
                done[i] = (x, corroborate.corroborate(grid, node, corroborate.categories_of(reg, node), rows, span, direction,
                                                      f"corroborate-refine|{x.id}", refine_replicates, dataset=self.dataset))
        for source in {c.source for _, c in done if c.tested}:
            group = [(x, c) for x, c in done if c.tested and c.source == source]
            ps = np.array([c.p for _, c in group])
            mask, qv = control.bh(ps, q), control.adjusted(ps)
            for (x, c), hit, qq in zip(group, mask, qv, strict=True):
                x.replications = {**x.replications, "corroboration": {**c.asdict(), "q": float(qq), "ok": bool(hit)}}
        for x, c in done:
            if not c.tested:
                x.replications = {**x.replications, "corroboration": {**c.asdict(), "ok": False}}
            x.replication = control.replication_tier(kinds_of(x))
        return [x for x, _ in done]

    def retier(self, register: list[leads.Lead], selected: list[leads.Lead]) -> list[leads.Lead]:
        """Give each lead of the all-data register the verdicts of the selecting session's lead that is the same finding
        (`replication.match`; the tested one with the smallest q): the later-years test (``selected`` from `train`) or the
        size on side E (from side A), then its tier from the confirmations it holds (`control.replication_tier`)."""
        by_node: dict[str, list[leads.Lead]] = {}
        for a in selected:
            by_node.setdefault(a.fields[0], []).append(a)
        for x in register:
            hits = replication.match(x, by_node.get(x.fields[0], [])) if x.fields else []
            for key in ("prospective", "honest"):   # the verdicts of the selecting session; the spatial and corroboration verdicts belong to the register itself
                have = [h for h in hits if h.replications.get(key, {}).get("tested", h.replications.get(key, {}).get("sized"))]
                if have:
                    best = min(have, key=lambda h: h.replications[key].get("q", h.q))
                    x.replications = {**x.replications, key: {**best.replications[key], "matched": best.id}}
                else:
                    x.replications = {k: v for k, v in x.replications.items() if k != key}
            x.replication = control.replication_tier(kinds_of(x))
            if x.replication != "R0" and x.status == "open":
                x.status = "replicated"
        return register

    # ---- agents ---------------------------------------------------------------------

    def confirm(self, node: str, lens: str, locus: dict[str, Any], q: float = 0.05, actor: str = "agent",
                caller: str | None = None) -> dict[str, Any]:
        """One claim, tested once on the reserved period under LOND."""
        return self.confirm_many([(node, lens, locus)], q, actor, caller)[0]

    def confirm_many(self, claims: list[tuple[str, str, dict[str, Any]]], q: float = 0.05, actor: str = "agent",
                     caller: str | None = None) -> list[dict[str, Any]]:
        """Claims (field node, lens, locus with ``places`` and ``direction`` "up"/"down") that the departure persists or
        recurs, tested in the order given, which must be fixed before the reserve is read: each locus on the
        reserved period of the dataset (`control.RESERVED_PERIODS`), against the fit on this session's years,
        re-levelled by state (`replication.test_prospective`), at its lens's minimum effect. The p-values enter the
        LOND stream of the ledger (`control.Reserve`). ``actor`` (agent | person) and ``caller`` (who asked) are
        written with the hypothesis. A session's own years can never include the reserve (`control.check_reserved`)."""
        held = control.reserved(self.dataset)
        if not held:
            raise LookupError(f"{self.dataset} has no reserved period")
        last = max(self.years)
        spend, out, bp = [], [], {}
        with control.reserve_open():
            exp = surprise.Expectations(self.dataset, self.event, sorted(set(self.years) | set(held)), self.graph)
            for node, lens, locus in claims:
                if node not in bp:
                    bp[node] = exp.prospective(node, last, course=False)
                res = replication.test_prospective(bp[node], lens, locus, -1 if locus.get("direction") == "down" else 1)
                out.append(res)
                if res["tested"]:
                    spec = {"field": node, "lens": lens, "locus": locus, **({"caller": caller} if caller else {})}
                    spend.append((control.Hypothesis("confirm", actor, spec),
                                  res["p"], res.get("effect"), {k: v for k, v in res.items() if k != "p"}))
        verdicts = iter(control.Reserve(self.ledger, q).spend(spend))
        return [{**res, **next(verdicts)} if res["tested"] else res for res in out]


def kinds_of(x: leads.Lead) -> set[str]:
    """The independent confirmations a lead holds (`control.KINDS`): ``temporal`` (it stands on the years after the fit's
    last, `Session.temporal_confirm`), ``spatial`` (it stands in other jurisdictions than the one it is
    about, `Session.spatial_confirm`, ADR-0019), ``corroborated`` (an independent field, `Session.corroborate`). The in-sample splits of
    `Session.triage` (``temporal``, ``spatial``) are descriptions, not confirmations: they share the selection."""
    r = x.replications
    kinds = set()
    if (r.get("national") or {}).get("ok") is False:
        return kinds            # a unit claim that does not stand against the year's observed national rate confirms nothing
    if (r.get("prospective") or {}).get("ok"):
        kinds.add("temporal")
    if (r.get("spatial_unit") or {}).get("ok"):
        kinds.add("spatial")
    if (r.get("corroboration") or {}).get("ok"):
        kinds.add("corroborated")
    return kinds


# ---- reading the stores, for the tools over MCP (`mcp_server`) -------------------------------------------


def fitted(dataset: str | None = None, event: str | None = None, graph: str | None = None,
           years: list[int] | None = None) -> list[dict[str, Any]]:
    """The fitted monolith blocks in the store (their manifests' keys), optionally narrowed."""
    out = []
    for d in sorted(store.address("monolith", {}).parent.glob("*/manifest.json")):
        k = json.loads(d.read_text(encoding="utf-8"))["key"]
        if k.get("block") is None or any(want is not None and k.get(name) != want for name, want in
                                         (("dataset", dataset), ("event", event), ("graph", graph), ("years", years))):
            continue
        out.append({"dataset": k["dataset"], "event": k["event"], "graph": k.get("graph"), "years": k.get("years"),
                    "block": k["block"], "model": d.parent.name})
    return out


def lead_row(x: leads.Lead) -> dict[str, Any]:
    """A lead, compact: where, what, how large, how well controlled, how replicated."""
    span, direction = replication.span_direction(x)
    return {"id": x.id, "rank": round(x.rank, 3), "kind": x.kind, "estimand": x.estimand, "field": x.fields[0],
            "node": x.fields[0].split(":")[-1], "tier": x.tier, "train_last": x.train_last, "purpose": x.purpose, "places": list(x.locus.get("places", []))[:20],
            "n_places": len(x.locus.get("places", [])), "years": span,
            "direction": {1: "up", -1: "down", 0: "pattern"}[direction], "effect": x.effect, "scale": x.scale,
            "q": x.q, "family": x.family, "replication": x.replication, "status": x.status,
            "triage": x.robustness.get("triage", {}).get("class"), "calibrated": x.calibrated}


def _ancestors(node: str) -> set[str]:
    seen, cur = {node}, node
    while (up := leads._parent(cur)) != cur and up not in seen:
        seen.add(up)
        cur = up
    return seen


def find_leads(register: list[leads.Lead], *, cls: str | None = None, tier: str | None = None,
               place: int | None = None, code: str | None = None, estimand: str | None = None,
               min_replication: str | None = None, status: str | None = None, direction: str | None = None,
               year: int | None = None, min_effect: float | None = None, max_q: float | None = None,
               dataset: str | None = None) -> list[leads.Lead]:
    """The leads of ``register`` (best rank first) that satisfy every filter given. ``code`` matches a lead whose
    field is that ICD-10 node or lies under it; ``min_effect`` is on the effect's own scale (a rate ratio r counts
    as max(r, 1/r)); ``min_replication`` is a tier R0..R3."""
    out = []
    for x in register:
        if not x.fields:
            continue
        span, d = replication.span_direction(x)
        size = max(x.effect, 1 / max(x.effect, 1e-12)) if x.scale == "rate_ratio" else abs(x.effect)
        node = x.fields[0].split(":")[-1]
        keep = (
            (dataset is None or x.fields[0].startswith(f"{dataset}:"))
            and (cls is None or x.robustness.get("triage", {}).get("class") == cls)
            and (tier is None or x.tier == tier)
            and (place is None or place in x.locus.get("places", []))
            and (code is None or code in _ancestors(node))
            and (estimand is None or x.estimand == estimand)
            and (min_replication is None or x.replication >= min_replication)
            and (status is None or x.status == status)
            and (direction is None or {1: "up", -1: "down", 0: "pattern"}[d] == direction)
            and (year is None or not span or span[0] <= year <= span[-1])
            and (min_effect is None or size >= min_effect)
            and (max_q is None or x.q <= max_q)
        )
        if keep:
            out.append(x)
    return out


def explain_lead(x: leads.Lead, register: list[leads.Lead]) -> dict[str, Any]:
    """Everything the stores hold about one lead: the lens's statistics, the triage verdict and its evidence,
    each replication, the siblings (same field, or the same single place) and the story it belongs to."""
    places = x.locus.get("places", [])
    siblings = [lead_row(y) for y in register if y.id != x.id and y.fields
                and (y.fields[0] == x.fields[0]
                     or (len(places) == 1 and y.locus.get("places", []) == places))]
    story = next((st for st in leads.stories(register) if any(m.id == x.id for m in st.leads)), None)
    return {"lead": lead_row(x), "locus": x.locus,
            "test": {"p": x.p, "q": x.q, "family": x.family, "null": x.null, "stats": x.provenance.get("stats", {})},
            "triage": x.robustness.get("triage"), "replications": x.replications,
            "confirmations": sorted(kinds_of(x)),
            "siblings": sorted(siblings, key=lambda r: -r["rank"])[:15], "n_siblings": len(siblings),
            "story": None if story is None else {"key": story.key, "fields": story.fields, "flags": story.flags,
                                                  "leads": len(story.leads), "rank": story.rank},
            "provenance": {k: v for k, v in x.provenance.items() if k != "stats"}}


def ledger_status(ledger: control.Ledger | None = None, q: float = 0.05) -> dict[str, Any]:
    """Tests per family and actor in the ledger, and the confirmation reserve: tests spent, rejections, and the
    level the next claim would be tested at."""
    ledger = ledger or control.Ledger()
    pending = [r for r in ledger.table().to_pylist() if r["kind"] == "pending"]
    reserve = control.Reserve(ledger, q)
    tested, rejected = reserve.state()
    by_family: dict[str, int] = {}
    actors: dict[str, int] = {}
    for r in pending:
        by_family[r["family"]] = by_family.get(r["family"], 0) + 1
        actors[r["actor"]] = actors.get(r["actor"], 0) + 1
    claims = [r for r in pending if r["split"] == control.Reserve.SPLIT]
    return {"tests": len(pending), "n_families": len(by_family), "actors": actors,
            "families": dict(sorted(by_family.items(), key=lambda kv: -kv[1])[:25]),
            "reserve": {"split": control.Reserve.SPLIT, "q": q, "spent": tested, "rejections": rejected,
                        "next_level": reserve.level(),
                        "last_claims": [{"id": r["id"], "at": r["at"], "actor": r["actor"], "spec": json.loads(r["spec"])}
                                        for r in claims[-10:]]}}


def method_status(dataset: str | None = None) -> dict[str, Any]:
    """Each survey method's record (ARCHITECTURE §10.5): tier, minimum effect, whether its false-discovery rate is
    calibrated, and the evidence, per combination of `SURVEY_PLAN` (for ``dataset``; SIM by default)."""
    ds = dataset or "SIM.DO"
    return {" ".join(x for x in (lens, reference) if x): method_record(ds, lens, reference)
            for lens, reference, _ in SURVEY_PLAN}


def dependency_map(years: list[int] | None = None, worlds: int = 0, health_only: bool = False,
                   ledger: control.Ledger | None = None) -> dict[str, Any]:
    """A dependency map (§7.6) of SIM chapters, SIH chapters (admissions that did not end in death), SINASC indicators
    and the context fields over ``years``: the inputs from the store (built through the gateway on first use), the
    marginal and conditional layers controlled over the whole map, and with ``worlds`` > 0 the false-edge rate on that
    many worlds of Moran-randomised surrogates (``health_only``: contexts kept real). Returns the summary and the edges."""
    from . import harness, store
    from .scans import map_inputs, maps, pairs

    years = years or map_inputs.YEARS
    key = {"what": "map_inputs", "years": years, "v": 2}     # v2: admission by power at rho 0.3 (ADR-0022)
    inp = maps.MapInputs.load(key)
    if inp is None:
        inp = map_inputs.build(years)
        inp.save(key)
    # §11.4: a chapter whose count expectation failed calibration at B1 (the first tier with geography, whose field
    # dispersion the place effects' Poisson sd leans on) never enters a pair scan; the fits are the production ones
    calibration = {}
    for dataset, event, group in (("SIM.DO", "death", "SIM"), ("SIH-RD", "hospitalisation", "SIH")):
        session = Session(dataset, event, FIT_YEARS)
        for name in inp.names:
            if name.startswith(group + ":"):
                calibration[name] = session.calibration_of(name.split(":", 1)[1], "B1")
    inp = maps.exclude_miscalibrated(inp, calibration, "B1")
    basis, gen = pairs.MoranBasis(inp.places), pairs.MoranBasis(inp.places, "knn8")
    dm = maps.dependency_map(inp, basis, ledger or control.Ledger(), tag="-".join(map(str, (years[0], years[-1]))))
    out: dict[str, Any] = {"fields": len(inp.names), "tested": dm.tested, "excluded_by_overlap": dm.excluded,
                           "admitted": dm.controlled, "seconds": dm.seconds, "left_out": inp.meta.get("left_out", {}),
                           "admission_power": inp.meta.get("admission_power", {}),
                           "excluded_calibration": inp.meta.get("excluded_calibration", {})}
    if worlds:
        neg = harness.map_negatives(inp, basis, gen, worlds, health_only)
        out["negatives"] = {"worlds": neg["worlds"], "delta_marginal": harness.map_delta(neg, "marginal"),
                            "delta_conditional": harness.map_delta(neg, "conditional")}
        harness.record("depmap", {"years": years, "worlds": worlds, "health_only": health_only}, out["negatives"])
    store.put_table("maps", {"what": "map_edges", "years": years}, dm.edges, {"summary": out})
    return {"summary": out, "edges": dm.edges, "inputs": inp}
