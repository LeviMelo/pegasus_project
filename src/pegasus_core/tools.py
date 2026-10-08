"""The interface for people and agents (ARCHITECTURE §9.3): a Python API first.

A `Session` binds one event type's fitted monolith (dataset, event, years,
graph) to the ledger and the lead register. Everything that tests something
goes through the ledger; everything admitted becomes a lead.

`survey_questions` is the scheduled pass: every field asked each stage-C question through all its methods
(`questions`), error control across families (Benjamini–Bogomolov, §8.2), the answers written to the register.

Replication is by units that took no part in the selection (`replication`, ARCHITECTURE §8.3): `train(last)` selects
on the years up to ``last`` and `temporal_confirm` tests the later years; `spatial_confirm` reads a unit claim in other jurisdictions and against how deaths are recorded (ADR-0019);
`corroborate` asks an independent record system; `confirm` is the agents' only
route to a claim: one test on the reserved period, under online FDR (LOND) whose state is read back from the
ledger. The event sides survive for sizes only: `honest_sizes`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import gc
import inspect
import json
import pickle
import threading
import time
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

LENS_TIERS = {"institution_step": "B1", "share_excess": "B1", "cell_excess": "B1", "excess": "B1", "excess_step": "B1", "excess_trend": "B1", "excess_level": "B0", "step": "B1", "outbreak": "B1", "change_point": "B1", "trend_divergence": "B2", "space_time": "B1",
              "spatial_cluster": "B0", "group_disparity": "B0"}
# The lenses a prospective survey (``survey(prospective=t0)``, fit on the years up to t0) can run, with their tier
# (ADR-0012): the outbreak lens reads the ALARM BASELINE (BPA: a flat level that past epidemics do not enter, so an
# epidemic stays a departure), the others the calibrated EXPECTATION (BP: a regime mixture, for surprises).
PROSPECTIVE_TIERS = {"outbreak": "BPA", "change_point": "BP", "space_time": "BP"}
# the methods that read a location field in one direction only: asked of both (`Session.scan`)
TWO_SIDED = ("cell_excess", "excess", "excess_step", "excess_trend", "excess_level")
SCALE = {"institution_step": "rate_ratio", "share_excess": "rate_ratio", "cell_excess": "rate_ratio", "excess": "rate_ratio", "excess_step": "rate_ratio", "excess_trend": "rate_ratio",
         "excess_level": "rate_ratio", "step": "rate_ratio", "outbreak": "rate_ratio", "change_point": "rate_ratio", "trend_divergence": "sd",
         "space_time": "rate_ratio", "spatial_cluster": "rate_ratio", "group_disparity": "rate_ratio"}


def lens_tier(lens: str, prospective: bool = False) -> str:
    """The expectation tier a lens reads: retrospective (`LENS_TIERS`) or, in a prospective survey, `PROSPECTIVE_TIERS`."""
    if not prospective:
        return LENS_TIERS[lens]
    if lens not in PROSPECTIVE_TIERS:
        raise ValueError(f"the {lens} lens has no prospective tier (one of {sorted(PROSPECTIVE_TIERS)})")
    return PROSPECTIVE_TIERS[lens]




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

        return [self.expectations.tag(f) for f in reg.walk(block, has_events)]

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
        key = {**m.key(), "field": f"{self.dataset}:{self.event}:{node}", "tier": tier, "what": "calibration", "code": config.code_key("pegasus_core.tools:Session.calibration_of")}
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
        su = self.surprise(node, "B1")                 # the survey's memo: built once for all of a field's questions
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
            self._spectrum = multiscale.spectrum(e, len(places), w)
        return self._spectrum

    def _blocks(self) -> list[str]:
        """The blocks fitted for this session's reader (the counts, or its measure, share or classifier)."""
        mine = json.loads(json.dumps({f: self.source.get(f) for f in READER_FIELDS}))     # tuples as the key's lists
        found = {k["block"] for k in fitted(self.dataset, self.event, self.graph, self.years)
                 if all(k["key"].get(f) == mine[f] for f in READER_FIELDS)}
        if self.expectations.registry.classifier != "*":
            found.discard("*")      # a classified type's total is a share's denominator, not a block of its tree
        return sorted(found)

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
        if lens == "institution_step":               # one institution against its catchment (E_i, §4.5)
            from scipy import stats as st

            res = self.institutions(node)
            T = len(self.surprise(node, "B1").years)
            windows = T * (T + 1) / 2
            return [lenses.Finding("institution_step", self.expectations.field(node).id, "B1",
                                   {"institutions": [r["facility"]], "years": [r["start"], r["end"]], "places": []},
                                   float(np.exp(r["log_ratio"])), float(min(1.0, windows * st.chi2.sf(2 * r["g"], 1))),
                                   {k: v for k, v in r.items() if k != "facility"})
                    for r in res["steps"]]
        if lens == "share_excess":                   # the field's share of all events (§7.1, the observation lens)
            from . import departures
            s = self.surprise(node, "B1")
            self._prepare_grid()
            if self._total is None:
                raise ValueError(f"{self.dataset}: no all-event count to take a share of (one block, no tree)")
            index = {int(p_): i for i, p_ in enumerate(self._grid_places)}
            rows = np.array([index.get(int(p_), -1) for p_ in s.places])
            have = rows >= 0
            total = np.zeros(s.y.shape)
            total[have] = self._total[rows[have]]
            mu_total = np.zeros(s.y.shape)
            mu_total[have] = self._expected_total()[rows[have]]
            return departures.share_excess(s.y, total, s.mu, mu_total, s.places, s.years, s.field.id, self.ledger, **kw)
        s = self.surprise(node, tier, train_last)
        if "rate_ratio" not in kw and (rr := surprise.location_rate_ratio(s)) is not None:
            kw["rate_ratio"] = rr                     # a location's relevance is on its own scale, not the counts'
        if surprise.gaussian(s) and lens in TWO_SIDED and not kw.pop("one_side", False):
            # a location departs either way (a shorter gestation matters as much as a longer one): each side at q/2,
            # the fall read as the rise of the mirrored field μ − (y − μ), whose predictive is the same
            q = kw.pop("q", 0.05)
            up = self.scan(node, lens, tier, None, train_last, q=q / 2, one_side=True, **kw)
            memo = getattr(self._local, "memo", None)
            mirror = dataclasses.replace(s, y=2 * s.mu - s.y, z=-s.z, u=1 - s.u)
            mirror.__dict__["_memo"] = s.__dict__.setdefault("_memo", {})
            self._local.memo = {**(memo or {}), (node, tier or lens_tier(lens, train_last is not None), train_last): mirror}
            try:
                down = self.scan(node, lens, tier, None, train_last, q=q / 2, one_side=True, **kw)
            finally:
                self._local.memo = memo
            for f in up:
                f.locus["direction"] = "up"
            for f in down:
                f.locus["direction"] = "down"
                f.effect = 1.0 / f.effect if f.effect else f.effect
            return up + down
        if lens in ("cell_excess", "step") and "scales" not in kw:
            kw["scales"] = self.scales()              # the departure models run over the ladder of supports
        if lens == "cell_excess":                     # a departure model (stage C, O6)
            from . import departures
            return departures.cell_excess(s, self.ledger, **kw)
        if lens in ("excess", "excess_step", "excess_trend", "excess_level"):  # at unknown spatial scale (stage C, O6)
            from . import departures
            return departures.excess(s, self.ledger, self.spectrum(), shape=lens.partition("_")[2] or "spike", **kw)
        if lens == "step":                     # the step departure model (stage C, O6)
            from . import departures
            return departures.step(s, self.ledger, **kw)
        if lens in ("outbreak", "change_point"):
            return getattr(lenses, lens)(s, self.ledger, **kw)
        fn = getattr(lenses, lens)
        if "q" in kw and "q" not in inspect.signature(fn).parameters:      # the scans name their level alpha
            kw["alpha"] = kw.pop("q")
        return fn(s, self.edges(), self.ledger, **kw)

    def alarms(self, node: str, as_of: str, report: str, recurrence: float = 260.0, weeks: int = 8,
               confidence: float = 0.5) -> list[dict]:
        """Phase 4 (`surveillance`; ADR-0004): the alarms of the last ``weeks`` epidemiological weeks before the date
        ``as_of`` (ISO) for every place of a field. The events known by then are the current year's records whose
        ``report`` date (`gateway.entry_date`) precedes it (`gateway.delay_counts`); each place's reporting delay comes
        from the last closed year; the baseline is the alarm tier (BPA, ADR-0012) fitted on the years before, at its
        own grain and allocated to weeks in proportion to their days (stated: a weekly alarm fit replaces it).
        Returns one row per place-week that alarms, strongest first."""
        from . import gateway, surveillance

        day = np.datetime64(as_of, "D")
        year = int(str(day)[:4])
        closed = surveillance.delays(gateway.delay_counts(self.dataset, self.event, year - 1, report))
        cur = gateway.delay_counts(self.dataset, self.event, year, report).to_pandas()
        ey, ew = surveillance.epi_week(np.array([day]))
        now = int(ew[0])
        cur = cur[(cur["year"] == int(ey[0])) & (cur["week"] > now - weeks) & (cur["week"] <= now)]
        cur = cur[cur["delay"] <= now - cur["week"]]                      # known by as_of
        known = cur.groupby(["u", "week"])["n"].sum()
        s = self.surprise(node, "BPA", train_last=year - 1)
        yrs = np.asarray(s.years)
        monthly = bool(yrs.max() > 10000)                   # periods labelled YYYYMM at the monthly grain
        month = int(str(day)[5:7])
        col = np.flatnonzero(yrs == (year * 100 + month if monthly else year))
        if col.size == 0:
            raise ValueError(f"the alarm baseline has no period holding {as_of}: the session's years must include {year}")
        first = np.datetime64(f"{year}-{month:02d}", "M")
        days = int(((first + 1).astype("datetime64[D]") - first.astype("datetime64[D]")).astype(int)) if monthly else 365.25
        mu_week = s.mu[:, col[0]] * 7 / days
        phi = np.broadcast_to(np.asarray(s.phi, dtype=float), s.mu.shape)[:, col[0]]
        index = {int(p): i for i, p in enumerate(s.places)}
        test = self.ledger.register(control.Hypothesis(f"alarm|{node}|{as_of}", "scan", {
            "model": "nowcast against the alarm baseline (BPA)", "field": s.field.id, "as_of": as_of,
            "recurrence": recurrence, "weeks": weeks}))
        out = []
        for (u, w), y in known.items():
            i = index.get(int(u))
            if i is None:
                continue
            a = surveillance.alarm(np.array([y]), np.array([closed.F(int(u), now - int(w))]), np.array([mu_week[i]]),
                                   np.array([phi[i]]), recurrence, confidence)
            if a["alarm"][0]:
                out.append({"place": int(u), "week": int(w), "known": int(y), "nowcast": float(a["nowcast"][0]),
                            "threshold": float(a["threshold"][0]), "p_exceed": float(a["p_exceed"][0]),
                            "baseline_week": float(mu_week[i])})
        out = sorted(out, key=lambda r: -r["p_exceed"])
        self.ledger.complete(test, 1.0 - max((r["p_exceed"] for r in out), default=0.0), None,
                             {"place_weeks": int(len(known)), "alarms": len(out)})
        self.register.add([leads.Lead(
            kind="residual", estimand="alarm", tier="BPA", fields=[s.field.id],
            locus={"places": [r["place"]], "years": [int(ey[0]), int(ey[0])], "week": r["week"]},
            effect=r["nowcast"] / max(r["baseline_week"], 1e-12), scale="rate_ratio", interval=None,
            p=1.0 - r["p_exceed"], q=1.0 / recurrence, family=f"alarm|{node}", null="the alarm baseline (BPA)",
            calibrated=False, train_last=year - 1, provenance={"as_of": as_of, **r}) for r in out])
        return out

    def ask(self, question: str, node: str, q: float = 0.05, **kw) -> list:
        """A question of `questions.QUESTIONS` on one field: every method answering it at q/k, their findings merged
        into answers by overlapping loci, each naming the methods that agree (docs/plans/2026-10-07-questions-and-methods.md)."""
        from . import questions
        return questions.ask(self, question, node, q, **kw)

    def survey_questions(self, blocks: list[str] | None = None, questions: tuple[str, ...] | None = None,
                         q: float = 0.05, levels: tuple[str, ...] | None = None, log=print,
                         train_last: int | None = None) -> list[leads.Lead]:
        """The pass over every field with events, asking questions instead of running lenses (`questions`): per field
        and question, the methods' answers (each method at q/k inside the field, merged by overlapping loci); an
        answer's p is its smallest method p times k (Bonferroni over the methods, valid under any dependence);
        across fields, Benjamini–Bogomolov per (question, block) family. Each lead names the question, the methods
        that agree, each one's effect and scale. Retrospective, in the fields' order. ``levels`` keeps the fields of
        those tree levels (None: every level). An answer of another shape than its question's (`questions.ask`'s
        ``other_shape``) is logged and left to the question of its shape, whose own methods test it. With
        ``train_last`` the prospective questions are asked instead, of the years after it, against fits on the years up
        to it (ADR-0012); without it they are not asked."""
        from . import questions as qs

        names = tuple(n for n in (questions or tuple(qs.QUESTIONS))
                      if qs.QUESTIONS[n].prospective == (train_last is not None))
        ask_kw = {"train_last": train_last} if train_last is not None else {}
        found: dict[str, list] = {}
        src = self.source
        measure = (f"|{'interval:' if src.get('anchor') else ''}{src['mark']}" if src.get("mark") else
                   f"|{src['indicator']}={','.join(src['success'])}" if src.get("indicator") else
                   f"|link:{src['link']}:{src['side']}" if src.get("link") else
                   f"|{src.get('classifier') or src['column']}" if src.get("source") == "code_list" else
                   f"|away:{src['place']}" if src.get("place") else
                   f"|classifier:{src['classifier']}" if src.get("classifier") else "")   # its own family
        code = config.code_key(qs.ask)
        suffix = f"|t{train_last}" if train_last else ""
        asked_fields, asked_families = set(), set()
        for block in blocks or self._blocks():
            asked_families |= {f"{qn}|{block}{measure}{suffix}" for qn in names}
            for f in self.fields(block):
                if levels is not None and f.level not in levels:
                    continue
                asked_fields.add(f.id)
                # each field's answers are an object of the state (work plan §2): stored when every question was
                # answered, keyed by the fit, the reader, the questions and the code, so a run killed mid-chapter
                # resumes at the next field and a rerun recomputes only what changed
                m = self.expectations.model(block)
                fit = store.manifest("monolith", m.key()) or {}
                key = {"what": "field_answers", "field": f.id, "source": json.loads(json.dumps(src, default=str)),
                       "questions": list(names), "q": q, "years": list(self.years), "graph": self.graph,
                       "fit": m.key(), "fitted": fit.get("written"), "code": code, **ask_kw}
                hit = store.get_arrays("answers", key)
                if hit is not None:
                    rows = pickle.loads(hit["rows"].tobytes())
                    log(f"{f.id}: answers stored")
                else:
                    self._local.memo = {}           # a field's surprises computed once for all its questions
                    rows, failed = [], False
                    for qn in names:
                        try:
                            answers = self.ask(qn, f.node, q=q, **ask_kw)
                            k = getattr(answers, "k", len(qs.QUESTIONS[qn].methods))
                        except Exception as exc:  # noqa: BLE001 - a field that fails is reported, the survey goes on
                            log(f"FAIL {f.id} {qn}: {type(exc).__name__}: {exc}")
                            failed = True
                            continue
                        failed = failed or any(m != "*" for m in getattr(answers, "failed", {}))  # "*": no method reads it
                        rows.append((qn, list(answers), k))
                        log(f"{f.id} {qn}: {len(answers)} answers {qs.agreement(answers)}, "
                            f"{len(getattr(answers, 'other_shape', []))} of another shape")
                    self._local.memo = None
                    if not failed:                  # a failure is retried by the next run, never stored
                        store.put_arrays("answers", key, {"rows": np.frombuffer(pickle.dumps(rows), dtype=np.uint8)})
                for qn, answers, k in rows:
                    for a in answers:
                        found.setdefault(f"{qn}|{block}{measure}{suffix}", []).append((f.id, a, min(1.0, a.p * k)))
        self._local.memo = None
        families = {k: np.array([p for *_, p in v]) for k, v in found.items() if v}
        rejected = control.bogomolov(families, q)
        by_lens = qs.method_records()                 # keyed by lens: a method's record is its lens's
        records = {m.id: {**by_lens[m.lens or m.id], "tier": LENS_TIERS.get(m.lens or m.id)}
                   for qn in qs.QUESTIONS.values() for m in qn.methods if (m.lens or m.id) in by_lens}
        admitted = []
        for fam, mask in rejected.items():
            qv = control.adjusted(families[fam])
            for (fid, a, p), keep, qq in zip(found[fam], mask, qv, strict=True):
                if not keep:
                    continue
                best = min(a.findings.values(), key=lambda x: x.p)
                admitted.append(leads.Lead(
                    kind="answer", estimand=fam.split("|")[0], tier=best.tier, fields=[fid], train_last=train_last,
                    locus={"places": sorted(a.places), "years": list(a.years),
                           **({"institutions": inst} if (inst := sorted({i for x in a.findings.values()
                                                                         for i in x.locus.get("institutions", [])}))
                              else {})}, effect=float(best.effect),
                    scale=SCALE.get(best.lens, "rate_ratio"), interval=None, p=float(p), q=float(qq), family=fam,
                    null="each method's own (questions.QUESTIONS)",
                    calibrated=all(records.get(m, {}).get("calibrated") is True for m in a.methods),
                    method={m: records.get(m, {"calibrated": None, "evidence": "not characterised"})
                            for m in a.methods},
                    provenance={"graph": self.graph, "methods": a.methods, "source": dict(self.source),
                                "years": list(self.years), "by_method": {m: {"effect": float(x.effect), "p": float(x.p), "stats": x.stats}
                                              for m, x in a.findings.items()}}))
        # an earlier answer of the same families and fields that this pass no longer selects is retired (the data,
        # the model or the code changed), never left open beside the current answers; a person's verdict keeps it
        new = {x.id for x in admitted}
        stale = [x for x in self.register.current() if x.kind == "answer" and x.family in asked_families
                 and x.fields and x.fields[0] in asked_fields and x.id not in new
                 and x.status in ("open", "replicated", "rescoped") and not x.robustness.get("verdict")]
        when = time.strftime("%Y-%m-%d")
        for x in stale:
            x.status, x.note = "retired", f"not selected by the question pass of {when}; {x.note}".strip("; ")
        self.register.add(stale + admitted)
        if stale:
            log(f"{len(stale)} earlier answers retired: no longer selected")
        return admitted

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

        Each verdict carries the rules' version (`explain.rules()`). ``stale`` re-triages only the leads whose verdict
        was made by other rules (or none); a lead a superseded rule had explained is open again unless the new verdict
        explains it, and the old verdict is kept beside the new one."""
        # a lead is triaged by the session of its own reader: a measure's or a linked share's answers were read
        # against the count field's evidence of the same node
        own = json.dumps(self.source, sort_keys=True, default=list)
        mine = [x for x in (register if register is not None else self.register.current())
                if x.fields and x.fields[0].startswith(f"{self.dataset}:") and x.status != "retired"
                and json.dumps(x.provenance.get("source") or {}, sort_keys=True, default=list) == own]
        if stale:
            mine = [x for x in mine if x.robustness.get("triage", {}).get("rules") != explain.rules()]
        if self.source.get("source") == "mark":
            return self._triage_marks(mine, write, log)
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
            batch = self._ledger_open("triage", [(x, {"rules": explain.rules()}) for x in group])
            for x in group:
                rows = np.array([index[int(p)] for p in x.locus.get("places", []) if int(p) in index], dtype=int)
                span, direction = replication.span_direction(x)
                st = x.provenance.get("stats", {})
                if x.estimand == "group_disparity":
                    ev.group_spread = explain.group_spread(*self._by_group_cells(node), rows)
                if fac is not None and rows.size:
                    ev.facility = fac.tally(self.expectations.registry.chapter(node), block_codes, lead_codes, rows)
                obs, exp_ = st.get("observed"), st.get("expected")
                if obs is None and s is not None and span:
                    # a question's answer (`survey_questions`) carries its methods' stats, not the locus's totals:
                    # read them from the field's expectation over the answer's places and window
                    sel = np.isin(s.places, np.asarray(x.locus.get("places", []), dtype=s.places.dtype))
                    w = (s.years >= span[0]) & (s.years <= span[-1])
                    obs, exp_ = float(s.y[sel][:, w].sum()), float(s.mu[sel][:, w].sum())
                def run(x=x, rows=rows, span=span, direction=direction, obs=obs, exp_=exp_, ev=ev):
                    if x.estimand == "institution":      # an institution's step reads its own statistics
                        st_i = (x.provenance.get("by_method", {}).get("institution_step") or {}).get("stats", {})
                        run.verdict = explain.institution_triage(st_i)
                    else:
                        run.verdict = explain.triage(x.estimand, rows, span, direction, ev, obs, exp_)
                    v = run.verdict
                    pv = v.evidence.get("p")
                    return {"tested": pv is not None, "p": 1.0 if pv is None else float(pv),
                            "reason": f"{v.cls} ({v.grade or 'ungraded'}): {v.reason}"}

                self._ledgered("triage", x, run, batch=batch)
                verdict = run.verdict
                old = x.robustness.get("triage")
                x.robustness = {**x.robustness, "triage": {"class": verdict.cls, "reason": verdict.reason,
                                                           "grade": verdict.grade or None, "bound": verdict.bound,
                                                           "rules": explain.rules(), **verdict.evidence,
                                                           **({"superseded": old} if old and old.get("rules") != explain.rules() else {})}}
                if verdict.grade == explain.TESTED and verdict.cls in (explain.SUBSTITUTION, explain.SYSTEM):
                    x.status = "explained"      # only a tested explanation takes a lead out; bound and consistent stay attached
                elif x.status == "explained":
                    x.status = "open"           # explained by a verdict the current rules do not repeat
                if replicate:
                    x.replications = {**x.replications, **self._replicate(x, s, rows, span, direction, half, edges)}
                    x.replication = control.replication_tier(kinds_of(x))
            self._ledger_close(batch)
            log(f"{i + 1}/{len(by_node)} {node}{f' ({tier} fit to {train_last})' if train_last else ''}: {len(group)} leads")
        if write:
            self.register.add(mine)
        return mine

    def _triage_marks(self, mine: list[leads.Lead], write: bool, log) -> list[leads.Lead]:
        """Stage E for a measure's answers (S4.3): the lead's admissions (its node's categories, its places, its window)
        by recording facility (`marks.triage_lead`). One institution's when at most FAC_K facilities carry FAC_SHARE of
        the departure and the rest is within the minimum effect (tested); else a signal, said unread under FAC_CATCH
        admissions (the location's own test weighed its count). The count field's evidence is not this field's (the 646 length-of-stay answers were read on it)."""
        from . import marks

        names = gateway.municipality_names()
        reg = self.expectations.registry
        by_block: dict[str, list[leads.Lead]] = {}
        for x in mine:
            by_block.setdefault(reg.chapter(x.fields[0].split(":")[-1]), []).append(x)
        for block, group in sorted(by_block.items()):
            model = self.expectations.model(block)
            batch = self._ledger_open("triage", [(x, {"rules": explain.rules()}) for x in group])
            for x in group:
                node = x.fields[0].split(":")[-1]
                places = np.asarray(x.locus.get("places", []), dtype=np.int64)
                window = x.locus.get("years") or [self.years[0], self.years[-1]]

                def run(x=x, node=node, places=places, window=window, model=model):
                    res = marks.triage_lead(model, self.source["mark"], list(self.years), places, window,
                                            self.source.get("facility_effects"), names, codes=list(reg.leaves(node)))
                    if res["admissions"] < explain.FAC_CATCH:
                        # too few admissions for the facilities to say anything: not noise (the location's own test
                        # weighed its count), only unread by this rule
                        run.verdict = explain.Triage(explain.SIGNAL, f"{res['admissions']} admissions: too few for the "
                                                     "recording facilities to say whether one carries it", res)
                    elif res.get("facility"):
                        tops = ", ".join(f"{t['facility']} ({t['n_share']:.0%} of admissions)" for t in res["top"])
                        run.verdict = explain.Triage(explain.FACILITY, f"one institution's: {tops} carry "
                                                     f"{res['share_of_excess']:.0%} of the departure, the rest within the minimum effect",
                                                     res, explain.TESTED)
                    else:
                        run.verdict = explain.Triage(explain.SIGNAL, "carried by more than one institution" if res.get("spread")
                                                     else "no recording explanation found in the admissions", res)
                    return {"tested": False, "reason": f"{run.verdict.cls}: {run.verdict.reason}"}

                self._ledgered("triage", x, run, batch=batch)
                v = run.verdict
                old = x.robustness.get("triage")
                x.robustness = {**x.robustness, "triage": {"class": v.cls, "reason": v.reason, "grade": v.grade or None,
                                                           "rules": explain.rules(), **v.evidence,
                                                           **({"superseded": old} if old else {})}}
            self._ledger_close(batch)
            log(f"{block}: {len(group)} measure leads triaged")
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
        """The event type's observed counts on one grid (all causes, the ill-defined chapter) and its person-years: at
        the annual grain from one cached read per year (`gateway.event_counts`), never from every fitted block's cells
        (assembling SIH's twenty chapters for this alone took minutes)."""
        if getattr(self, "_pop", None) is not None:
            return
        if self.source.get("grain", "year") == "year" and self.expectations.registry.classifier != "*":
            import pyarrow.compute as pc

            # an object of the state: the event type's totals per place-year, read once (14 s a process on SIH)
            key = {"what": "evidence_grid", "dataset": self.dataset, "event": self.event, "years": list(self.years),
                   "data": config.data_version(), "code": config.code_key("pegasus_core.tools:Session._prepare_grid")}
            hit = store.get_arrays("tools", key)
            if hit is not None:
                self._grid_places, self._grid_years, self._per_year = hit["places"], hit["years"], 1
                self._total, self._ill, self._pop = hit["total"], hit["ill"], hit["pop"]
                return
            pop_t = gateway.population(list(self.years)).group_by(["u", "year"]).aggregate([("n", "sum")])
            places = np.unique(pop_t.column("u").to_numpy())
            years = np.asarray(self.years)
            pop = np.zeros((len(places), len(years)))
            pop[np.searchsorted(places, pop_t.column("u").to_numpy()),
                np.searchsorted(years, pop_t.column("year").to_numpy())] = pop_t.column("n_sum").to_numpy()
            reg = self.expectations.registry
            total, ill = np.zeros_like(pop), np.zeros_like(pop)
            for j, year in enumerate(years):          # vectorised: a Python loop over SIH's rows took 320 s a field
                c = gateway.event_counts(self.dataset, self.event, int(year)).counts
                cu = c.column("u").to_numpy()
                u = np.minimum(np.searchsorted(places, cu), len(places) - 1)
                ok = places[u] == cu
                y = np.asarray(c.column("y").to_numpy(), dtype=float)
                total[:, j] += np.bincount(u[ok], weights=y[ok], minlength=len(places))
                cat = pc.dictionary_encode(pc.utf8_slice_codeunits(pc.cast(c.column("code"), "string"), 0, 3))                     .combine_chunks()
                ill_cat = np.array([reg.chapter(str(x)) == "XVIII" for x in cat.dictionary.to_pylist()], dtype=bool)
                chap = ill_cat[cat.indices.to_numpy(zero_copy_only=False)] if len(ill_cat) else np.zeros(len(cu), bool)
                total_ill = ok & chap
                ill[:, j] += np.bincount(u[total_ill], weights=y[total_ill], minlength=len(places))
            self._grid_places, self._grid_years, self._per_year = places, years, 1
            self._total, self._ill, self._pop = total, ill, pop
            store.put_arrays("tools", key, {"places": places, "years": years, "total": total, "ill": ill, "pop": pop})
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

    def _expected_total(self) -> np.ndarray:
        """[U, T] the expected events of the whole event type (stage B1), on the evidence grid: a share's denominator.
        One fit of the all-events field (block ``*``), not a sum over every chapter's fit (twenty robust fits on
        SIH-RD, hours, and 13 GB held at once, 2026-10-07). The fit is an object of the state, made by `update` (or
        `pegasus-core fit DATASET EVENT '*'`), never inside a reading: missing, it raises."""
        if getattr(self, "_mu_total", None) is None and self.expectations.registry.classifier != "*":
            self._prepare_grid()
            try:
                m = self.expectations.model("*")
            except LookupError as exc:
                raise LookupError(f"{self.dataset}: the all-events fit (block *) a share reads is not stored; "
                                  f"`pegasus-core update` fits it with the plan, or `pegasus-core fit "
                                  f"{self.dataset} {self.event} '*'`") from exc
            mu = m.expected(np.arange(len(m.data.leaves)))[0]
            index = {int(p): i for i, p in enumerate(m.data.places)}
            rows = np.array([index.get(int(p), -1) for p in self._grid_places])
            self._mu_total = np.where(rows[:, None] >= 0, mu[np.maximum(rows, 0)], 0.0)
            return self._mu_total
        if getattr(self, "_mu_total", None) is None:
            self._prepare_grid()
            key = {"what": "expected_total", "dataset": self.dataset, "event": self.event, "years": list(self.years),
                   "graph": self.graph, "robust": self.expectations.robust, "data": config.data_version(),
                   "fits": sorted(k["model"] for k in fitted(self.dataset, self.event, self.graph, self.years))}
            hit = store.get_arrays("tools", key)
            if hit is not None:
                self._mu_total = hit["mu"]
                return self._mu_total
            tot = None
            for b in self._blocks():
                held = b in self.expectations._models
                m = self.expectations.model(b)
                mu = m.expected(np.arange(len(m.data.leaves)))[0]
                tot = mu if tot is None else tot + mu
                if not held:
                    del m
                    self.expectations._models.pop(b, None)
                    gc.collect()
            self._mu_total = tot
            store.put_arrays("tools", key, {"mu": np.asarray(tot)})
        return self._mu_total

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
        # the siblings: the family's other leaves (the family is the outermost group, `leads.family`); an outermost
        # group's are the rest of its chapter. Without them a group under the chapter had none, and a facility that
        # recoded its asthma and pneumonia as pneumoconiosis read as a signal (Mundo Novo/GO, J64, 2012; S5.1)
        parent = fam if fam != node else reg.chapter(node)
        sib = None
        if reg.level.get(node) != "chapter" and parent != node and parent in reg.children:
            sl = np.setdiff1d(self._leaves(parent)[1], leaves)
            sib = self._counts(d, sl) if sl.size else None
        by_g = sib is not None and d.N.shape[-1] > 1
        return explain.Evidence(self._grid_years, y, sib, self._ill, self._total, self._pop, chapter=reg.chapter(node),
                                residual=explain.residual_label(reg.label.get(node, "")), per_year=self._per_year,
                                y_g=self._counts(d, leaves, by_group=True) if by_g else None,
                                siblings_g=self._counts(d, sl, by_group=True) if by_g else None,
                                pop_g=d.N if by_g else None)

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
        # every reader its own home: a tag of four of its keys let a classifier's, a mention's or a flow's training
        # survey share the counts' ledger and register (survey 2026-10-07)
        reader = {k: v for k, v in self.source.items() if k != "grain"}
        tag = f"_{config.seed('reader', json.dumps(reader, sort_keys=True, default=str)):x}"[:13] if reader else ""
        return Session(self.dataset, self.event, [y for y in self.years if y <= last], self.graph, self.supply,
                       self.rank, dict(self.source), ledger=control.Ledger(home / f"ledger_T{last}{tag}"),
                       register=leads.Register(home / f"leads_T{last}{tag}"))

    def temporal_confirm(self, last: int, q: float = 0.05, level: str = "state", log=print) -> list[leads.Lead]:
        """The leads the survey selected on the years up to ``last`` (`train`), each tested once at its fixed places on the
        later years of this session, against a fit that ends at ``last`` (BP, the place's course not carried
        forward), re-levelled to the state's course of each year (`replication.relevel`); Benjamini-Hochberg over
        everything tested. The verdict is in ``lead.replications["prospective"]``. A one-off event does not
        recur: an answer whose every attributed course is a spike or a transient (`departures.attribute`) stays
        untested here by nature, and needs corroboration."""
        t = self.train(last)
        selected = t.register.current()
        if self.source.get("mark"):
            tested = [(x, {"tested": False, "reason": "a measure's later years are cell means: the count tail does not "
                                                      "apply; not built"}) for x in selected]
            self._record(tested, "prospective", q)
            t.register.add(selected)
            return selected
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
            tested += [(x, self._ledgered("prospective", x, lambda x=x, sp=sp: replication.test_lead(sp, x, level),
                                          last=last, level=level) if replication.lasting(x) else
                        {"tested": False, "reason": "a passing departure (spike or transient) does not recur: corroboration"})
                       for x in group]
            log(f"{i + 1}/{len(by_node)} {node}: {len(group)} leads")
        self._record(tested, "prospective", q)
        t.register.add(selected)
        return selected

    def _ledger_open(self, kind: str, items: list[tuple[leads.Lead, dict[str, Any]]]) -> dict[str, Any]:
        """A batch of stage-E tests, (lead, spec) each, written to the ledger before any of them runs (§9.2), in one
        part; they run in this order (`_ledgered`). A test per part left tens of thousands of files
        (`control.Ledger.compact`)."""
        ids = self.ledger.register_many([control.Hypothesis(f"{kind}|{self.dataset}", "scan", {
            "lead": x.id, "fields": x.fields, "locus": x.locus, "estimand": x.estimand, **spec}) for x, spec in items])
        return {"ids": ids, "leads": [x.id for x, _ in items], "done": []}

    def _ledger_close(self, batch: dict[str, Any]) -> None:
        self.ledger.complete_many(batch["done"])

    def _ledgered(self, kind: str, x: leads.Lead, run, batch: dict[str, Any] | None = None, **spec) -> dict[str, Any]:
        """One stage-E test of a lead, written to the ledger before it runs and completed with its p (§9.2): ``run``
        returns the test's record (``tested``, ``p``, ``effect`` or a ``reason``). In a ``batch`` (`_ledger_open`) it
        was registered with its batch, and its result is written when the batch closes."""
        own = batch is None
        batch = batch or self._ledger_open(kind, [(x, spec)])
        k = len(batch["done"])
        if batch["leads"][k] != x.id:
            raise RuntimeError(f"{kind}: test {k} of the batch was registered for {batch['leads'][k]}, run for {x.id}")
        r = run()
        batch["done"].append((batch["ids"][k], float(r.get("p", 1.0)) if r.get("tested") else 1.0,
                              r.get("effect") if r.get("tested") else None,
                              {"tested": bool(r.get("tested")), **({"reason": r["reason"]} if r.get("reason") else {})}))
        if own:
            self._ledger_close(batch)
        return r

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
            def run(x=x, last=last, direction=direction):
                run.rec = replication.audit(st, x.locus["places"], x.fields[0].split(":")[-1], x.locus["scale"],
                                            x.provenance["stats"]["beta"], direction, [y for y in self.years if y <= last],
                                            tree, seed_text=x.id, later_years=[y for y in self.years if y > last])
                j = run.rec["jurisdiction"]       # its p is named by the unit's test (`replication.jurisdiction`)
                pv = next((j[k] for k in ("p_binomial", "p_test", "p_state_rest") if j.get(k) is not None), None)
                return {"tested": pv is not None, "p": 1.0 if pv is None else float(pv), "reason": j.get("reason")}

            self._ledgered("spatial_unit", x, run, source=source)
            rec = run.rec
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

    def corroborate(self, register: list[leads.Lead], served: list[tuple[str, str]] | None = None,
                    only_signals: bool = True, replicates: int = 4999, q: float = 0.05, log=print,
                    refine_p: float = 0.01, refine_replicates: int = 99999) -> list[leads.Lead]:
        """Ask every independent field (`corroborate.sources` over the ``served`` event types, and the context fields
        with a declared ICD-10 correspondence) that holds a lead's codes whether its places and years are unusual
        there, against that field's own null (random same-size place sets of the same state and population quintile;
        a cluster of touching places is replaced by connected sets grown on the graph, `corroborate._null_sets`).
        Leads with p < ``refine_p`` are redrawn at ``refine_replicates`` so that Benjamini-Hochberg over many tests can
        reject. Benjamini-Hochberg within each source. Written to ``lead.replications["corroboration"]``: the best
        source's test, ``ok`` when any source rejects, and every source's test under ``sources``."""
        self._prepare_grid()
        pop = self._pop.sum(1)
        state = (self._grid_places // 10000).astype(int)
        grid = corroborate.Fields(self._grid_places, self._grid_years, state, pop, self.edges())
        index = {int(p): j for j, p in enumerate(self._grid_places)}
        reg = self.expectations.registry
        fields_ = corroborate.sources(self.dataset, served or [])
        tests: list[tuple[leads.Lead, corroborate.Corroboration]] = []
        seen: list[leads.Lead] = []
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
            seen.append(x)
            cats = corroborate.categories_of(reg, node)
            held = [src for src in fields_ if grid.holds(src, cats)]
            batch = self._ledger_open("corroboration", [(x, {"source": src.label}) for src in held])
            for src in held:
                def run(x=x, src=src, cats=cats, rows=rows, span=span, direction=direction):
                    c = corroborate.corroborate(grid, src, cats, rows, span, direction, f"corroborate|{x.id}|{src.label}",
                                                replicates)
                    # a permutation p-value cannot fall below 1 / (replicates + 1), and Benjamini-Hochberg over m tests
                    # needs the best to reach q / m: the promising ones are redrawn with many more replicates
                    if c.tested and c.p < refine_p:
                        c = corroborate.corroborate(grid, src, cats, rows, span, direction,
                                                    f"corroborate-refine|{x.id}|{src.label}", refine_replicates)
                    run.result = c
                    return {"tested": c.tested, "p": c.p, "effect": c.observed, "reason": (c.detail or {}).get("reason")}

                self._ledgered("corroboration", x, run, batch=batch)
                tests.append((x, run.result))
            self._ledger_close(batch)
            if len(seen) % 200 == 0:
                log(f"corroborated {len(seen)}")
        # one family (S4.1): each lead's corroboration p is its smallest source p times the number of its sources
        # tested (Bonferroni: a lead is corroborated by any of k sources only at q/k each), and one Benjamini-Hochberg
        # over every lead. "Any source rejects at q" over unbounded sources inflated a lead's error by its source count
        by_lead: dict[str, list] = {}
        for x, c in tests:
            by_lead.setdefault(x.id, []).append(c)
        tested = [x for x in seen if any(c.tested for c in by_lead.get(x.id, []))]
        lead_p = np.array([min(1.0, min(c.p for c in by_lead[x.id] if c.tested)
                               * sum(c.tested for c in by_lead[x.id])) for x in tested])
        mask, qv = (control.bh(lead_p, q), control.adjusted(lead_p)) if len(lead_p) else (np.zeros(0, bool), np.zeros(0))
        verdict = {x.id: (bool(hit), float(qq), float(pp)) for x, hit, qq, pp in zip(tested, mask, qv, lead_p, strict=True)}
        for x in seen:
            got = [{**c.asdict(), "ok": False} for c in by_lead.get(x.id, [])] or \
                [{"tested": False, "reason": "no independent field holds its codes", "ok": False}]
            if x.id in verdict:
                hit, qq, pp = verdict[x.id]
                best = dict(min((g for g in got if g.get("tested")), key=lambda g: g.get("p", 1.0)))
                best.update({"ok": hit, "q": qq, "p_lead": pp, "sources_tested": sum(bool(g.get("tested")) for g in got)})
            else:
                best = got[0]
            x.replications = {**x.replications, "corroboration": {**best, "sources": got}}
            x.replication = control.replication_tier(kinds_of(x))
        return seen

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


#: the source fields that name what a fit reads (`monolith.assemble`'s key): a session's blocks are the fits of its own
READER_FIELDS = ("source", "classifier", "structure", "mark", "indicator", "success", "link", "side", "anchor", "column",
                 "place")


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
                    "block": k["block"], "model": d.parent.name, "key": k})
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


def method_status() -> dict[str, Any]:
    """Every method's measured record (ARCHITECTURE §10.5; `questions.method_records`), with its tier."""
    from . import questions

    return {m: {**r, "tier": LENS_TIERS.get(m)} for m, r in questions.method_records().items()}


def relation_survey(plan: list[tuple[str, str, list[str]]], years: list[int], graph: str = "contiguity",
                    min_events: int = 2000, levels: tuple[str, ...] = ("group",), q: float = 0.05, log=print
                    ) -> list[leads.Lead]:
    """Stage D across systems (`relations.relation_map`): every field of the ``levels`` of each (dataset, event,
    blocks) in ``plan`` with at least ``min_events`` events, read at B1; the reported relations enter the register as
    leads of kind "relation" (fields: the follower and the leader; locus: the band and the lag; effect: the implied
    correlation). Each system's fits are released before the next is loaded. Statistical relations only (P16)."""
    import gc

    from . import multiscale, relations

    surps, edges, n_places, excluded = [], None, None, []
    for ds, ev, blocks in plan:
        s = Session(ds, ev, years, graph)
        for b in blocks:
            m = s.expectations.model(b)
            for f in s.fields(b):
                if f.level not in levels and not (b == "*" and f.node == "*"):
                    continue
                x = s.surprise(f.node, "B1")
                if x.y.sum() < min_events:
                    continue
                if x.calibration.get("calibrated") is False:
                    # invariant 8 (ARCHITECTURE): a field whose predictive is miscalibrated is never in a pair scan;
                    # its relations are unanswered, and say why
                    excluded.append(f"{x.field.id}: miscalibrated (KS {x.calibration.get('ks', float('nan')):.3f})")
                    continue
                surps.append(x)
            if edges is None:
                edges, n_places = s.edges(), len(m.data.places)
            s.expectations._models = {}
            gc.collect()
        log(f"{ds}: {len(surps)} fields so far")
    out = relations.relation_map(surps, multiscale.spectrum(edges, n_places), q=q, ledger=control.Ledger(), log=log)
    rep = [r for r in out["rows"] if r["reported"]]
    qv = control.adjusted(np.array([r["p"] for r in out["rows"]]))
    qmap = {id(r): float(v) for r, v in zip(out["rows"], qv, strict=True)}
    family = "relations|" + "+".join(f"{ds}:{','.join(b)}" for ds, _, b in plan)
    from . import questions

    record = questions.method_records().get("relation_map", {"calibrated": None, "evidence": "not characterised"})
    admitted = [leads.Lead(kind="relation", estimand="co-movement", tier="B1", fields=[r["field"], r["leader"]],
                           locus={"band": r["support"], "lag": r["lag"]}, effect=float(r["rho"]), scale="rho",
                           interval=None, p=float(r["p"]), q=qmap[id(r)], family=family,
                           null="independent fields' innovations (factor model per band)",
                           calibrated=record.get("calibrated") is True, method={"relation_map": record},
                           provenance={"z": float(r["z"]), "unanswered": out["unanswered"] + excluded,
                                       **({"partial": r["partial"], "direct": bool(r["direct"])} if "direct" in r else {})})
                for r in rep]
    leads.Register().add(admitted)
    log(f"{len(rep)} relations reported of {len(out['rows'])} pairs; unanswered: {len(out['unanswered'])} bands, "
        f"{len(excluded)} miscalibrated fields")
    return admitted



def joint(fields: list[tuple[str, str, str]], years: list[int], graph: str = "contiguity", q: float = 0.05,
          replicates: int = 100) -> list:
    """Places and periods where several fields, of one system or several, depart together (`departures.joint_excess`,
    the fast subset scan over fields): ``fields`` as (dataset, event, node), each read at B1."""
    from . import departures

    sessions: dict = {}
    surps = []
    for ds, ev, node in fields:
        s = sessions.setdefault((ds, ev), Session(ds, ev, years, graph))
        surps.append(s.surprise(node, "B1"))
    first = next(iter(sessions.values()))
    found = departures.joint_excess(surps, first.ledger, q=q, replicates=replicates)
    if found:
        qv = control.adjusted(np.array([f.p for f in found]))
        family = "joint|" + "+".join(f"{ds}:{node}" for ds, _, node in fields)
        leads.Register().add([leads.Lead(
            kind="subset", estimand="joint_excess", tier="B1", fields=f.locus["fields"],
            locus={"places": f.locus["places"], "years": f.locus["years"]}, effect=float(f.effect), scale="rate_ratio",
            interval=None, p=float(f.p), q=float(qq), family=family, null="each field's predictive (N1), GPD tail",
            calibrated=False, method={"joint_excess": {"calibrated": None, "evidence": "not characterised"}},
            provenance={"stats": f.stats}) for f, qq in zip(found, qv, strict=True)])
    return found


def compare(x: tuple[str, str, str], y: tuple[str, str, str], years: list[int], graph: str = "contiguity",
            lags: int = 2, q: float = 0.05) -> list[dict]:
    """Do two fields move together, at which spatial scale and lag (ARCHITECTURE §9.3, `compare`)? The relation map
    of the two (`relations.relation_map`: N1 innovations by graph band, the factor model, directness, and the national
    and macro-regional courses where the bands cannot be identified), each field as (dataset, event, node) at B1.
    Every row is returned, ``reported`` marking the relations at q."""
    from . import multiscale, relations

    sessions: dict = {}
    surps = []
    for ds, ev, node in (x, y):
        s = sessions.setdefault((ds, ev), Session(ds, ev, years, graph))
        surps.append(s.surprise(node, "B1"))
    first = next(iter(sessions.values()))
    spectrum = multiscale.spectrum(first.edges(), len(surps[0].places))
    return relations.relation_map(surps, spectrum, lags=lags, K=2, q=q, ledger=first.ledger)["rows"]


def records(dataset: str, event: str, year: int, columns: list[str], places: list[int] | None = None):
    """The records of one event type and year through pegasus_data, the event type's status applied
    (`gateway._records`), raw-coded; ``places`` keeps the residences given (six-digit IBGE codes). Personal
    identifiers pass through unmodified, flagged by pegasus_data's roles (`pegasus_data.roles`)."""
    import pyarrow.compute as pc

    t = gateway._records(dataset, event, year, columns)
    if places is not None:
        res = gateway._strata(dataset)["residence"]
        code = pc.utf8_slice_codeunits(pc.cast(t[res], pa.string()), 0, 6)
        t = t.filter(pc.is_in(code, value_set=pa.array([str(p) for p in places])))
    return t


def cohort(dataset: str, event: str, link: str, side: str, year: int, draws: int = 20, q: float = 0.05,
           log=print) -> list[leads.Lead]:
    """The cohort scan (ARCHITECTURE §7.8) on one side of a declared link: every event of ``dataset`` in ``year`` is a
    person; the outcome is having a partner on the link's other side (a birth followed by an infant death); every
    modelled composition of ``dataset`` (`fields.declared`, a declared category with its missing codes, which form
    their own "not recorded" level) is an attribute, tested level by level against its most common one, adjusted for
    the side's age class, sex and year with a shrunk place effect (`scans.cohort.scan`). Linkage uncertainty enters
    by ``draws`` plausible link sets (each pair kept with its p_match), combined by Rubin's rules. Nothing is named:
    the persons, the attributes and the outcome come from pegasus_data's declarations. Results enter the register as
    leads of kind "cohort"."""
    from . import fields
    from .scans import cohort as cohort_mod

    attrs = [d for d in fields.declared(dataset) if d.kind == "composition" and not d.reason]
    if not attrs:
        raise ValueError(f"{dataset}: no modelled composition to read as an attribute (`fields.declared` says why)")
    t, ids, pairs = gateway.cohort_records(dataset, event, year, link, side, [d.column for d in attrs])
    rng = np.random.default_rng(config.seed("cohort", dataset, link, side, year))
    p = pairs.column("p_match").to_numpy(zero_copy_only=False) if "p_match" in pairs.column_names else np.ones(pairs.num_rows)
    mine = pairs.column("r" if side == "right" else "l").to_numpy(zero_copy_only=False)
    base = {"place": pa.array([str(u) for u in t["u"].to_pylist()]),
            "age_band": pa.array([str(a) for a in t["age"].to_pylist()]),
            "sex": pa.array([str(s) for s in t["sex"].to_pylist()]),
            "year": pa.array([str(year)] * t.num_rows), "person_time": pa.array(np.ones(t.num_rows))}
    for d in attrs:
        raw = [str(x) if x not in (None, "") else "blank" for x in t[d.column].to_pylist()]
        base[d.column] = pa.array(["not recorded" if x in d.missing else x for x in raw])
    tables = []
    id_list = ids.to_numpy(zero_copy_only=False)
    for _ in range(draws):
        kept = set(mine[rng.random(len(p)) < p])
        out = np.fromiter((x in kept for x in id_list), dtype=float, count=len(id_list))
        tables.append(pa.table({**base, "outcome": pa.array(out)}))
    family = f"cohort|{link}:{side}|{dataset}|{year}"
    res = cohort_mod.scan(tables[0], [d.column for d in attrs], ["outcome"], control.Ledger(), family, draws=tables)
    log(f"{family}: {len(res)} contrasts over {len(attrs)} attributes, {t.num_rows} persons")
    if not res:
        return []
    qv = control.adjusted(np.array([r.p for r in res]))
    admitted = [leads.Lead(kind="cohort", estimand="rate_ratio_vs_reference", tier="cohort",
                           fields=[f"{dataset}:{event}", f"link:{link}:{side}"],
                           locus={"attribute": r.attribute, "level": r.level, "reference": r.reference,
                                  "years": [year, year]},
                           effect=float(np.exp(r.log_rr)), scale="rate_ratio",
                           interval=(float(np.exp(r.log_rr - 1.96 * r.sd)), float(np.exp(r.log_rr + 1.96 * r.sd))),
                           p=float(r.p), q=float(qq), family=family,
                           null=f"|log RR| ≤ log {cohort_mod.DELTA_RR} (minimum effect), Rubin over {draws} link draws",
                           calibrated=False, provenance={"events": r.events, "persons": r.person_time})
                for r, qq in zip(res, qv, strict=True) if qq <= q]
    leads.Register().add(admitted)
    return admitted


def disparity(dataset: str, event: str, node: str, years: list[int], races: tuple[str, ...] | None = None,
              reference: str = "1", graph: str = "contiguity", q: float = 0.05, log=print) -> list[leads.Lead]:
    """Race disparities of a field (ARCHITECTURE §3.4, §4.2; P15) by indirect standardisation: each race's expectation
    without place effects (tier B0 of the race's own fit: its national rates by age, sex and period on its slice of
    the population account, and for recorded race the exposure through the measured confusion, `gateway.population`),
    so a place's standardised ratio O_j/E_j is the race's rate there against the race's national rate. A place's
    disparity is its race-j ratio over the ``reference`` race's; given the two races' events there, race j's count is
    beta-binomial with mean E_j·θ/(E_j·θ + E_ref), θ the national disparity, and the places' own spread of disparities by central
    matching (`departures.betabinom_central`), so the test (two-sided) reports places
    whose disparity departs from Brazil's, pooled over ``years``. One BH at q over races and places; the leads carry
    the place's disparity against the national one. Each race's block must be fitted (`update` fits them as a declared
    step of a plan's ``disparities``); a missing one raises."""

    from . import departures

    races = races or tuple(k for k in gateway.RACE if k != reference)
    out_rows = []
    sess = {}
    for k in (reference, *races):
        s = Session(dataset, event, years, graph, source={"race": k})
        block = s.expectations.field(node).block
        s.expectations.model(block)          # raises LookupError when the race's fit is not stored
        sess[k] = s.surprise(node, "B0")
    ref = sess[reference]
    o_ref, e_ref = ref.y.sum(1), ref.mu.sum(1)
    test = control.Ledger().register(control.Hypothesis(f"disparity|{dataset}|{node}", "scan", {
        "model": "indirect standardisation by race, conditional binomial", "reference": reference, "races": races,
        "years": [years[0], years[-1]]}))
    for k in races:
        s = sess[k]
        if not np.array_equal(np.asarray(s.places), np.asarray(ref.places)):
            raise ValueError("the race fits read different places")
        o, e = s.y.sum(1), s.mu.sum(1)
        theta = (o.sum() / max(e.sum(), 1e-12)) / max(o_ref.sum() / max(e_ref.sum(), 1e-12), 1e-12)
        n = o + o_ref
        use = (n > 0) & (e > 0) & (e_ref > 0)
        p0 = np.clip(e * theta / (e * theta + e_ref), 1e-9, 1 - 1e-9)
        # beta-binomial with the places' own spread of disparities (central matching): places differ in a disparity
        # as they differ in every rate, and a binomial at a birth's counts called half of them departures
        pv = np.ones(len(o))
        if use.sum() >= 20:
            conc, below, at, upper = departures.betabinom_central(o[use], n[use], p0[use], ("disparity", dataset, node, k))
            pv[use] = np.minimum(1.0, 2 * np.minimum(below + at, upper))
        for i in np.flatnonzero(use):
            rr = (o[i] / e[i]) / max(o_ref[i] / e_ref[i], 1e-12) if o_ref[i] > 0 else np.inf
            out_rows.append((k, int(s.places[i]), float(rr), float(theta), float(pv[i]), float(o[i]), float(o_ref[i])))
    if not out_rows:
        return []
    pv = np.array([r[4] for r in out_rows])
    keep = control.bh(pv, q)
    qv = control.adjusted(pv)
    control.Ledger().complete(test, float(pv.min()), None, {"places": len(out_rows), "reported": int(keep.sum())})
    field_id = ref.field.id
    admitted = [leads.Lead(kind="residual", estimand="race_disparity", tier="B0", fields=[field_id],
                           locus={"places": [u], "years": [years[0], years[-1]], "race": k, "reference": reference},
                           effect=rr if np.isfinite(rr) else 1e6, scale="rate_ratio", interval=None, p=p, q=float(qq),
                           family=f"disparity|{field_id}", null="the national disparity (beta-binomial, central matching)",
                           calibrated=False, provenance={"national_disparity": theta, "events": o_k, "events_reference": o_r})
                for (k, u, rr, theta, p, o_k, o_r), kp, qq in zip(out_rows, keep, qv, strict=True) if kp]
    reg = leads.Register()
    new = {x.id for x in admitted}
    stale = [x for x in reg.current() if x.family == f"disparity|{field_id}" and x.id not in new
             and x.status in ("open", "replicated", "rescoped") and not x.robustness.get("verdict")]
    for x in stale:                        # an earlier reading this one no longer selects
        x.status, x.note = "retired", f"not selected by the disparity reading of {time.strftime('%Y-%m-%d')}"
    reg.add(stale + admitted)
    log(f"disparity {field_id}: {len(admitted)} places depart from the national disparity, of {len(out_rows)}"
        + (f"; {len(stale)} earlier readings retired" if stale else ""))
    return admitted
