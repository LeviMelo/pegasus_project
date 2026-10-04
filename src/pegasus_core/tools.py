"""The interface for people and agents (ARCHITECTURE §9.3): a Python API first.

A `Session` binds one event type's fitted monolith (dataset, event, years,
graph) to the ledger and the lead register. Everything that tests something
goes through the ledger; everything admitted becomes a lead.

`survey` is the scheduled pass: every admissible field of each fitted block,
the lenses at their tiers, error control across families (Benjamini–Bogomolov,
§8.2), and the admitted findings written to the register. `confirm` is the
agents' only route to a claim: one test on the spatial reserve (half B), under
online FDR (LOND) whose state is read back from the ledger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from . import control, fields, gateway, graphs, leads, store, surprise
from .scans import explain, lenses

LENS_TIERS = {"outbreak": "B2", "change_point": "B2", "trend_divergence": "B2", "space_time": "B1",
              "spatial_cluster": "B0", "group_disparity": "B0"}
SCALE = {"outbreak": "rate_ratio", "change_point": "rate_ratio", "trend_divergence": "sd",
         "space_time": "rate_ratio", "spatial_cluster": "rate_ratio", "group_disparity": "rate_ratio"}


@dataclass
class Session:
    dataset: str
    event: str
    years: list[int]
    graph: str = graphs.DEFAULT
    ledger: control.Ledger = field(default_factory=control.Ledger)
    register: leads.Register = field(default_factory=leads.Register)

    def __post_init__(self):
        self.expectations = surprise.Expectations(self.dataset, self.event, self.years, self.graph)

    # ---- reading ---------------------------------------------------------------

    def fields(self, block: str) -> list[fields.Field]:
        """The admissible fields of a fitted block, top-down (§8.4 provisional rule)."""
        m = self.expectations.model(block)
        reg = self.expectations.registry
        leaf_index = {c: i for i, c in enumerate(m.data.leaves)}
        totals = np.bincount(m.data.e, weights=m.data.y, minlength=len(m.data.leaves))

        def admissible(node: str) -> bool:
            idx = [leaf_index[c] for c in reg.leaves(node) if c in leaf_index]
            if not idx:
                return False
            units = int(np.unique(m.data.u[np.isin(m.data.e, idx)]).size)
            return fields.admission(float(totals[idx].sum()), units, len(m.data.places))[0]

        return reg.walk(block, admissible)

    def surprise(self, node: str, tier: str = "B1") -> surprise.Surprise:
        return self.expectations.surprise(node, tier)

    def by_group(self, node: str) -> tuple[np.ndarray, np.ndarray]:
        """Observed and B0-expected counts by (place, year, group), B0 re-levelled per year and
        group to the national totals, so a place's group pattern is read against Brazil's."""
        f = self.expectations.field(node)
        m = self.expectations.model(f.block)
        reg = self.expectations.registry
        leaves = np.array([m.data.leaves.index(c) for c in reg.leaves(f.node) if c in m.data.leaves])
        y = m.observed_by_group(leaves)
        mu = m.expected_by_group(leaves, spatial=False)
        ref = m.expected_by_group(leaves, spatial=True)
        mu = mu * (ref.sum(0) / np.maximum(mu.sum(0), 1e-300))[None]
        return y, mu

    def expected(self, node: str, tier: str = "B1") -> dict[str, Any]:
        s = self.surprise(node, tier)
        return {"places": s.places, "years": s.years, "observed": s.y, "expected": s.mu}

    def edges(self) -> np.ndarray:
        places = self.expectations.model(next(iter(self._blocks()))).data.places
        return graphs.edges(places, self.graph)

    def _blocks(self) -> list[str]:
        fitted = []
        for d in (store.address("monolith", {}).parent).glob("*/manifest.json"):
            k = json.loads(d.read_text(encoding="utf-8"))["key"]
            if (k.get("dataset"), k.get("event"), k.get("graph"), k.get("years")) == \
                    (self.dataset, self.event, self.graph, self.years):
                fitted.append(k["block"])
        return sorted(set(fitted))

    # ---- scanning ----------------------------------------------------------------

    def scan(self, node: str, lens: str, tier: str | None = None, **kw) -> list[lenses.Finding]:
        tier = tier or LENS_TIERS[lens]
        if lens == "group_disparity":
            y_g, mu_g = self.by_group(node)
            places = self.expectations.model(self.expectations.field(node).block).data.places
            return lenses.group_disparity(y_g, mu_g, places, self.expectations.field(node).id, self.ledger, **kw)
        s = self.surprise(node, tier)
        if lens in ("outbreak", "change_point"):
            return getattr(lenses, lens)(s, self.ledger, **kw)
        return getattr(lenses, lens)(s, self.edges(), self.ledger, **kw)

    def survey(self, blocks: list[str] | None = None, lens_names: tuple[str, ...] = ("outbreak", "change_point",
               "trend_divergence", "space_time", "group_disparity"), q: float = 0.05, replicates: int = 100, log=print) -> list[leads.Lead]:
        """The scheduled pass over every admissible field; returns the leads admitted."""
        found: dict[str, list[lenses.Finding]] = {}
        for block in blocks or self._blocks():
            for f in self.fields(block):
                for lens in lens_names:
                    kw = {"replicates": replicates} if lens in ("space_time", "spatial_cluster", "change_point") else {}
                    try:
                        hits = self.scan(f.node, lens, **kw)
                    except Exception as exc:  # noqa: BLE001 - a field that fails is reported, the survey goes on
                        log(f"FAIL {f.id} {lens}: {type(exc).__name__}: {exc}")
                        continue
                    family = f"{lens}|{LENS_TIERS[lens]}|{block}"
                    found.setdefault(family, []).extend(hits)
                    log(f"{f.id} {lens}: {len(hits)}")
        # error control across families: families selected by Simes, BH inside at the reduced level
        families = {k: np.array([h.p for h in v]) for k, v in found.items() if v}
        rejected = control.bogomolov(families, q)
        admitted = []
        for fam, mask in rejected.items():
            qv = control.adjusted(families[fam])
            admitted += leads.admit(found[fam], mask, qv, lambda h, qq, fam=fam: self._lead(h, qq, fam))
        self.register.add(admitted)
        return admitted

    def _lead(self, h: lenses.Finding, q: float, family: str) -> leads.Lead:
        return leads.Lead(kind="subset" if h.lens in ("space_time", "spatial_cluster") else "residual",
                          estimand=h.lens, tier=h.tier, fields=[h.field], locus=h.locus, effect=h.effect,
                          scale=SCALE[h.lens], interval=None, p=h.p, q=q, family=family,
                          null="Gumbel on NB replicates" if h.lens in ("space_time", "spatial_cluster", "change_point")
                          else "NB predictive",
                          calibrated=True, robustness={}, provenance={"graph": self.graph, "stats": h.stats})

    # ---- on demand -------------------------------------------------------------------

    def explain_away(self, lead: leads.Lead, candidate: np.ndarray, tier: str | None = None) -> explain.Explanation:
        """``candidate`` [U, T] over the session's places and years."""
        node = lead.fields[0].split(":")[-1]
        s = self.surprise(node, tier or lead.tier)
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

    # ---- agents ---------------------------------------------------------------------

    def confirm(self, node: str, lens: str, locus: dict[str, Any], q: float = 0.05) -> dict[str, Any]:
        """One test of a claimed locus on the spatial reserve (half B), under LOND."""
        s = self.surprise(node, LENS_TIERS.get(lens, "B1"))
        _, side_b = control.spatial_halves(s.places, dict(zip(s.places.tolist(), gateway.regions(
            s.places, "ibge_immediate_region"), strict=True)))
        places = np.intersect1d(np.array(locus.get("places", [])), side_b)
        if places.size == 0:
            return {"tested": False, "reason": "no place of the locus lies in the reserve"}
        yrs = locus.get("years", [int(s.years[0]), int(s.years[-1])])
        rows = np.isin(s.places, places)
        cols = (s.years >= yrs[0]) & (s.years <= yrs[-1])
        Y = float(s.y[np.ix_(rows, cols)].sum())
        M = float(s.mu[np.ix_(rows, cols)].sum())
        mu_c, phi_c = s.mu[np.ix_(rows, cols)], s.phi[np.ix_(rows, cols)]
        extra = float(np.sum(np.where(np.isfinite(phi_c), mu_c ** 2 / phi_c, 0.0)))
        if M <= 0:
            p = 1.0
        elif extra <= 0:
            p = float(stats.poisson.sf(Y - 1, M))
        else:
            n = M ** 2 / extra          # a sum of NB cells, moment-matched: Var = M + M²/n
            p = float(stats.nbinom.sf(Y - 1, n, n / (n + M)))
        test = self.ledger.register(control.Hypothesis("confirm", "agent", {"field": node, "lens": lens,
                                                                            "locus": locus}, split="spatial:B"))
        lond = control.LOND(q)
        for r in self.ledger.table().to_pylist():
            if r["kind"] == "result" and r["id"] != test and r.get("result") and '"lond"' in r["result"]:
                lond.tested += 1
                lond.rejected += int(json.loads(r["result"]).get("rejected", False))
        hit = lond.test(p)
        self.ledger.complete(test, p, Y / M if M > 0 else None, {"lond": True, "rejected": hit, "observed": Y,
                                                               "expected": M})
        return {"tested": True, "p": p, "rejected": hit, "observed": Y, "expected": M, "places": places.tolist()}
