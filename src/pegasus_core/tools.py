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
import gc
import json
import threading
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


FIT_YEARS = list(range(2010, 2024))      # the years of the production fits (the dependency map reads their calibration)


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
        """The blocks fitted for this session's reader (the counts, or its measure, share or classifier)."""
        mine = json.loads(json.dumps({f: self.source.get(f) for f in READER_FIELDS}))     # tuples as the key's lists
        return sorted({k["block"] for k in fitted(self.dataset, self.event, self.graph, self.years)
                       if all(k["key"].get(f) == mine[f] for f in READER_FIELDS)})

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
        return getattr(lenses, lens)(s, self.edges(), self.ledger, **kw)

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
                         q: float = 0.05, levels: tuple[str, ...] | None = None, log=print) -> list[leads.Lead]:
        """The pass over every field with events, asking questions instead of running lenses (`questions`): per field
        and question, the methods' answers (each method at q/k inside the field, merged by overlapping loci); an
        answer's p is its smallest method p times k (Bonferroni over the methods, valid under any dependence);
        across fields, Benjamini–Bogomolov per (question, block) family. Each lead names the question, the methods
        that agree, each one's effect and scale. Retrospective, in the fields' order. ``levels`` keeps the fields of
        those tree levels (None: every level). An answer of another shape than its question's (`questions.ask`'s
        ``other_shape``) is logged and left to the question of its shape, whose own methods test it."""
        from . import questions as qs

        names = questions or tuple(qs.QUESTIONS)
        found: dict[str, list] = {}
        src = self.source
        measure = (f"|{'interval:' if src.get('anchor') else ''}{src['mark']}" if src.get("mark") else
                   f"|{src['indicator']}={','.join(src['success'])}" if src.get("indicator") else
                   f"|link:{src['link']}:{src['side']}" if src.get("link") else
                   f"|{src.get('classifier') or src['column']}" if src.get("source") == "code_list" else
                   f"|away:{src['place']}" if src.get("place") else "")   # its own family
        for block in blocks or self._blocks():
            for f in self.fields(block):
                if levels is not None and f.level not in levels:
                    continue
                self._local.memo = {}           # a field's surprises computed once for all its questions
                for qn in names:
                    try:
                        answers = self.ask(qn, f.node, q=q)
                        k = getattr(answers, "k", len(qs.QUESTIONS[qn].methods))
                    except Exception as exc:  # noqa: BLE001 - a field that fails is reported, the survey goes on
                        log(f"FAIL {f.id} {qn}: {type(exc).__name__}: {exc}")
                        continue
                    for a in answers:
                        found.setdefault(f"{qn}|{block}{measure}", []).append((f.id, a, min(1.0, a.p * k)))
                    log(f"{f.id} {qn}: {len(answers)} answers {qs.agreement(answers)}, "
                        f"{len(getattr(answers, 'other_shape', []))} of another shape")
        self._local.memo = None
        families = {k: np.array([p for *_, p in v]) for k, v in found.items() if v}
        rejected = control.bogomolov(families, q)
        from . import harness

        records = harness.method_records()
        admitted = []
        for fam, mask in rejected.items():
            qv = control.adjusted(families[fam])
            for (fid, a, p), keep, qq in zip(found[fam], mask, qv, strict=True):
                if not keep:
                    continue
                best = min(a.findings.values(), key=lambda x: x.p)
                admitted.append(leads.Lead(
                    kind="answer", estimand=fam.split("|")[0], tier="B1", fields=[fid],
                    locus={"places": sorted(a.places), "years": list(a.years),
                           **({"institutions": inst} if (inst := sorted({i for x in a.findings.values()
                                                                         for i in x.locus.get("institutions", [])}))
                              else {})}, effect=float(best.effect),
                    scale="rate_ratio", interval=None, p=float(p), q=float(qq), family=fam,
                    null="each method's own (questions.QUESTIONS)",
                    calibrated=all(records.get(m, {}).get("calibrated") is True for m in a.methods),
                    method={m: records.get(m, {"calibrated": None, "evidence": "not characterised"})
                            for m in a.methods},
                    provenance={"graph": self.graph, "methods": a.methods, "source": dict(self.source),
                                "years": list(self.years), "by_method": {m: {"effect": float(x.effect), "p": float(x.p), "stats": x.stats}
                                              for m, x in a.findings.items()}}))
        self.register.add(admitted)
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
                obs, exp_ = st.get("observed"), st.get("expected")
                if obs is None and s is not None and span:
                    # a question's answer (`survey_questions`) carries its methods' stats, not the locus's totals:
                    # read them from the field's expectation over the answer's places and window
                    sel = np.isin(s.places, np.asarray(x.locus.get("places", []), dtype=s.places.dtype))
                    w = (s.years >= span[0]) & (s.years <= span[-1])
                    obs, exp_ = float(s.y[sel][:, w].sum()), float(s.mu[sel][:, w].sum())
                verdict = explain.triage(x.estimand, rows, span, direction, ev, obs, exp_)
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

    def _expected_total(self) -> np.ndarray:
        """[U, T] the expected events of every fitted block (stage B1), on the evidence grid: a share's denominator.
        Kept in the store under the blocks' fit keys; a block read only for this total is released at once (holding
        every chapter's model at the same time took 13 GB on SIH-RD, 2026-10-07)."""
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
        tag = "".join(f"_{v}" for k, v in sorted(self.source.items()) if k in ("mark", "indicator", "link", "side"))
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

    def _ledgered(self, kind: str, x: leads.Lead, run, **spec) -> dict[str, Any]:
        """One stage-E test of a lead, written to the ledger before it runs and completed with its p (§9.2): ``run``
        returns the test's record (``tested``, ``p``, ``effect`` or a ``reason``)."""
        tid = self.ledger.register(control.Hypothesis(f"{kind}|{self.dataset}", "scan", {
            "lead": x.id, "fields": x.fields, "locus": x.locus, "estimand": x.estimand, **spec}))
        r = run()
        self.ledger.complete(tid, float(r.get("p", 1.0)) if r.get("tested") else 1.0,
                             r.get("effect") if r.get("tested") else None,
                             {"tested": bool(r.get("tested")), **({"reason": r["reason"]} if r.get("reason") else {})})
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
            for src in fields_:
                if not grid.holds(src, cats):
                    continue
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

                self._ledgered("corroboration", x, run, source=src.label)
                tests.append((x, run.result))
            if len(seen) % 200 == 0:
                log(f"corroborated {len(seen)}")
        verdicts: dict[str, list[dict]] = {}
        for source in {c.source for _, c in tests if c.tested}:
            group = [(x, c) for x, c in tests if c.tested and c.source == source]
            ps = np.array([c.p for _, c in group])
            mask, qv = control.bh(ps, q), control.adjusted(ps)
            for (x, c), hit, qq in zip(group, mask, qv, strict=True):
                verdicts.setdefault(x.id, []).append({**c.asdict(), "q": float(qq), "ok": bool(hit)})
        for x, c in tests:
            if not c.tested:
                verdicts.setdefault(x.id, []).append({**c.asdict(), "ok": False})
        for x in seen:
            got = verdicts.get(x.id) or [{"tested": False, "reason": "no independent field holds its codes", "ok": False}]
            best = min(got, key=lambda v: (not v["ok"], v.get("q", v.get("p", 1.0))))
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
    """Every method's measured record (ARCHITECTURE §10.5; `harness.method_records`)."""
    from . import harness

    return harness.method_records()


def dependency_map(years: list[int] | None = None, worlds: int = 0, health_only: bool = False,
                   ledger: control.Ledger | None = None, plan: str = "plans/default.yml") -> dict[str, Any]:
    """A dependency map (§7.6) of every fitted field of the ``plan``'s systems (`map_inputs.build`: chapters, measures,
    shares; "not linked to" twins where a declared link records the same events) and the context fields over
    ``years``: the inputs from the store (built through the gateway on first use), the
    marginal and conditional layers controlled over the whole map, and with ``worlds`` > 0 the false-edge rate on that
    many worlds of Moran-randomised surrogates (``health_only``: contexts kept real). Returns the summary and the edges."""
    from . import harness, store, update
    from .scans import map_inputs, maps, pairs

    years = years or map_inputs.YEARS
    loaded = update.Plan.load(plan)
    systems = [(x.dataset, x.event, x.blocks) for x in loaded.systems]
    contexts = loaded.extra.get("contexts") or []
    key = {"what": "map_inputs", "years": years, "systems": [list(s[:2]) for s in systems], "contexts": contexts,
           "v": 3}   # v3: declared fields and contexts
    inp = maps.MapInputs.load(key)
    if inp is None:
        inp = map_inputs.build(systems, years, contexts=contexts)
        inp.save(key)
    # §11.4: a chapter whose count expectation failed calibration at B1 (the first tier with geography, whose field
    # dispersion the place effects' Poisson sd leans on) never enters a pair scan; the fits are the production ones
    calibration = {}
    for dataset, event, _ in systems:
        session = Session(dataset, event, FIT_YEARS)
        for name in inp.names:
            if name.startswith(dataset + ":") and "|" not in name:      # a count field (its twin shares its fit)
                calibration[name] = session.calibration_of(name.split(":", 1)[1], "B1")
    inp = maps.exclude_miscalibrated(inp, calibration, "B1")
    basis, gen = pairs.MoranBasis(inp.places), pairs.MoranBasis(inp.places, "knn8")
    dm = maps.dependency_map(inp, basis, ledger or control.Ledger(), tag="-".join(map(str, (years[0], years[-1]))))
    out: dict[str, Any] = {"fields": len(inp.names), "tested": dm.tested, "excluded_by_overlap": dm.excluded,
                           "admitted": dm.controlled, "seconds": dm.seconds, "linked_share": inp.meta.get("linked_share", {}),
                           "excluded_calibration": inp.meta.get("excluded_calibration", {})}
    if worlds:
        neg = harness.map_negatives(inp, basis, gen, worlds, health_only)
        out["negatives"] = {"worlds": neg["worlds"], "delta_marginal": harness.map_delta(neg, "marginal"),
                            "delta_conditional": harness.map_delta(neg, "conditional")}
        harness.record("depmap", {"years": years, "worlds": worlds, "health_only": health_only}, out["negatives"])
    store.put_table("maps", {"what": "map_edges", "years": years}, dm.edges, {"summary": out})
    # the admitted pairs are relation leads (§9.1), read and triaged with every other lead; the between-places
    # estimand with context fields (E_b) is this map's alone until the relation map reads contexts (S1)
    e = dm.edges.to_pylist()
    adm = [r for r in e if r.get("admitted")]
    if adm:
        qv = dict(zip((id(r) for r in e), control.adjusted(np.array([r["p"] for r in e])), strict=True))
        leads.Register().add([leads.Lead(
            kind="relation", estimand="E_b", tier="B1", fields=[r["x"], r["y"]],
            locus={"band": "between places", "lag": 0, "years": [years[0], years[-1]]}, effect=float(r["rho"]),
            scale="rho", interval=None, p=float(r["p"]), q=float(qv[id(r)]), family=f"map|{r['family']}",
            null="Moran spectral randomisation", calibrated=True,
            method={"dependency_map": {"evidence": "map negatives (harness.map_negatives)"}},
            provenance={"n_eff": r.get("n_eff")}) for r in adm])
    return {"summary": out, "edges": dm.edges, "inputs": inp}


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
    out = relations.relation_map(surps, multiscale.GraphSpectrum(edges, n_places), q=q, ledger=control.Ledger(), log=log)
    rep = [r for r in out["rows"] if r["reported"]]
    qv = control.adjusted(np.array([r["p"] for r in out["rows"]]))
    qmap = {id(r): float(v) for r, v in zip(out["rows"], qv, strict=True)}
    family = "relations|" + "+".join(f"{ds}:{','.join(b)}" for ds, _, b in plan)
    from . import harness

    record = harness.method_records().get("relation_map", {"calibrated": None, "evidence": "not characterised"})
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
    spectrum = multiscale.GraphSpectrum(first.edges(), len(surps[0].places))
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
    binomial with probability E_j·θ/(E_j·θ + E_ref), θ the national disparity, so the test (two-sided) reports places
    whose disparity departs from Brazil's, pooled over ``years``. One BH at q over races and places; the leads carry
    the place's disparity against the national one. Each race's block is fitted where it is not (`update.fit_block`)."""
    from scipy import stats as st

    from . import update

    races = races or tuple(k for k in gateway.RACE if k != reference)
    out_rows = []
    sess = {}
    for k in (reference, *races):
        s = Session(dataset, event, years, graph, source={"race": k})
        block = s.expectations.field(node).block
        try:
            s.expectations.model(block)
        except LookupError:
            update.fit_block(dataset, event, block, years, graph, source={"race": k}, log=log)
            s = Session(dataset, event, years, graph, source={"race": k})
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
        p0 = e * theta / (e * theta + e_ref)
        lower = st.binom.cdf(o, n, np.clip(p0, 1e-12, 1 - 1e-12))
        upper = st.binom.sf(o - 1, n, np.clip(p0, 1e-12, 1 - 1e-12))
        pv = np.where(use, np.minimum(1.0, 2 * np.minimum(lower, upper)), 1.0)
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
                           family=f"disparity|{field_id}", null="the national disparity (conditional binomial)",
                           calibrated=False, provenance={"national_disparity": theta, "events": o_k, "events_reference": o_r})
                for (k, u, rr, theta, p, o_k, o_r), kp, qq in zip(out_rows, keep, qv, strict=True) if kp]
    leads.Register().add(admitted)
    log(f"disparity {field_id}: {len(admitted)} places depart from the national disparity, of {len(out_rows)}")
    return admitted
