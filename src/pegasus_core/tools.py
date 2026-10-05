"""The interface for people and agents (ARCHITECTURE §9.3): a Python API first.

A `Session` binds one event type's fitted monolith (dataset, event, years,
graph) to the ledger and the lead register. Everything that tests something
goes through the ledger; everything admitted becomes a lead.

`survey` is the scheduled pass: every admissible field of each fitted block,
the lenses at their tiers, error control across families (Benjamini–Bogomolov,
§8.2), and the admitted findings written to the register. `confirm` is the
agents' only route to a claim: one test on the spatial reserve (half B), under
online FDR (LOND) whose state is read back from the ledger.

The events are dealt to sides (`replication`, ARCHITECTURE §8.3): `side("A")` explores and selects, `split_confirm`
tests what A selected on side B, `confirm` spends the reserve (side R), `corroborate` asks an independent field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from . import (
    config,
    control,
    corroborate,
    fields,
    gateway,
    graphs,
    leads,
    monolith,
    replication,
    store,
    surprise,
)
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
        # admission reads all the events even when the model is a side's (`replication.load_a`): the same fields
        # are scanned on A as on all the data, and the choice does not depend on which events landed on A
        e, u, y = getattr(m, "full_counts", (m.data.e, m.data.u, m.data.y))
        totals = np.bincount(e, weights=y, minlength=len(m.data.leaves))

        def admissible(node: str) -> bool:
            idx = [leaf_index[c] for c in reg.leaves(node) if c in leaf_index]
            if not idx:
                return False
            units = int(np.unique(u[np.isin(e, idx)]).size)
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
                          calibrated=bool(h.stats.get("calibrated", True)), robustness={},
                          provenance={"graph": self.graph, "stats": h.stats})

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

    # ---- triage and replication (§7.7, §8.3) ---------------------------------------------

    def triage(self, register: list[leads.Lead] | None = None, replicate: bool = True, write: bool = True,
               log=print) -> list[leads.Lead]:
        """Classify every open lead of the session's dataset by the data's own evidence (substitution, system
        artefact, noise, signal; `explain.triage`) and run the replication of §8.3 on the same arrays. The
        verdict goes to ``lead.robustness["triage"]``, the tier to ``lead.replication``; leads read as
        artefacts are marked `explained`. With ``write`` the new states are appended to the register."""
        mine = [x for x in (register if register is not None else self.register.current())
                if x.fields and x.fields[0].startswith(f"{self.dataset}:")]
        by_node: dict[str, list[leads.Lead]] = {}
        for x in mine:
            by_node.setdefault(x.fields[0].split(":")[-1], []).append(x)
        edges = self.edges() if replicate else None
        for i, (node, group) in enumerate(sorted(by_node.items())):
            ev = self._evidence(node)
            index = {int(p): j for j, p in enumerate(self._grid_places)}
            s = self.surprise(node, "B1") if replicate else None
            half = self._trend_halves(s, edges) if replicate and any(x.estimand == "trend_divergence" for x in group) else None
            for x in group:
                rows = np.array([index[int(p)] for p in x.locus.get("places", []) if int(p) in index], dtype=int)
                span, direction = replication.span_direction(x)
                st = x.provenance.get("stats", {})
                if x.estimand == "group_disparity":
                    ev.group_spread = explain.group_spread(*self._by_group_cells(node), rows)
                verdict = explain.triage(x.estimand, rows, span, direction, ev, st.get("observed"), st.get("expected"))
                x.robustness = {**x.robustness, "triage": {"class": verdict.cls, "reason": verdict.reason,
                                                           **verdict.evidence}}
                if verdict.cls in (explain.SUBSTITUTION, explain.SYSTEM):
                    x.status = "explained"
                if replicate:
                    x.replications = {**x.replications, **self._replicate(x, s, rows, span, direction, half, edges)}
                    x.replication = control.replication_tier(kinds_of(x))
            log(f"{i + 1}/{len(by_node)} {node}: {len(group)} leads")
        if write:
            self.register.add(mine)
        return mine

    def _prepare_grid(self) -> None:
        """Every fitted block's observed counts (all causes, the ill-defined chapter) on one grid."""
        if getattr(self, "_total", None) is not None:
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
            self._grid_places, self._grid_years = d.places, d.years
        self._total, self._ill, self._pop = total, ill, pop

    def _data(self, block: str) -> monolith.BlockData:
        """A block's cells, cached on disk: assembling one takes about a minute."""
        cache = self.__dict__.setdefault("_blocks_data", {})
        if block not in cache:
            key = {"dataset": self.dataset, "event": self.event, "block": block, "years": self.years,
                   "data": config.data_version(), "triage_block": 1}
            hit = store.get_arrays("triage_block", key)
            if hit is not None:
                meta = store.manifest("triage_block", key)
                cache[block] = monolith.BlockData(self.dataset, self.event, block, hit["years"], hit["places"],
                                                  meta["leaves"], meta["groups"], hit["leaf_group"], hit["N"], hit["e"],
                                                  hit["u"], hit["t"], hit["g"], hit["y"], key=key)
            else:
                d = monolith.assemble(self.dataset, self.event, block, self.years)
                store.put_arrays("triage_block", key, {k: getattr(d, k) for k in
                                 ("years", "places", "leaf_group", "N", "e", "u", "t", "g", "y")},
                                 {"leaves": d.leaves, "groups": d.groups})
                cache[block] = d
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
        parent = leads._parent(node)
        sib = None
        if reg.level.get(node) != "chapter" and parent != node and parent in reg.children:
            others = [c for c in reg.children[parent] if c != node]
            sl = np.concatenate([self._leaves(c)[1] for c in others]) if others else np.array([], dtype=int)
            sib = self._counts(d, sl) if sl.size else None
        return explain.Evidence(self._grid_years, y, sib, self._ill, self._total, self._pop, chapter=reg.chapter(node),
                                residual=explain.residual_label(reg.label.get(node, "")))

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

    # ---- honest splitting and corroboration (§8.3) -----------------------------------------

    def side(self, side: str) -> Session:
        """This session over one side of the events (`replication`): A explores and selects, with its own register
        and ledger (its tests are not the all-data denominator); B and R are read to test and to confirm."""
        out = Session(self.dataset, self.event, self.years, self.graph,
                      ledger=control.Ledger(config.home() / "ledger_A") if side == "A" else self.ledger,
                      register=leads.Register(config.home() / "leads_A") if side == "A" else self.register)
        out.expectations = replication.SideExpectations(out.expectations, side)
        return out

    def split_confirm(self, q: float = 0.05, log=print) -> list[leads.Lead]:
        """The leads selected on side A, each tested once on side B at its fixed locus, Benjamini-Hochberg over
        all that were tested (valid because B played no part in the selection or in the fit). The verdict is
        in ``lead.replications["split"]``; ``lead.replication`` is R1 for a lead that stands."""
        a = self.side("A")
        b = self.side("B")
        ratio = replication.RATIO["B"]
        selected = a.register.current()
        edges = self.edges()
        by_node: dict[str, list[leads.Lead]] = {}
        for x in selected:
            by_node.setdefault(x.fields[0].split(":")[-1], []).append(x)
        tested: list[tuple[leads.Lead, dict[str, Any]]] = []
        for i, (node, group) in enumerate(sorted(by_node.items())):
            surprises: dict[str, tuple[surprise.Surprise, surprise.Surprise]] = {}
            cache: dict[str, Any] = {}
            for x in group:
                if x.tier not in surprises:
                    surprises[x.tier] = (b.surprise(node, x.tier), a.surprise(node, x.tier))
                sb, sa = surprises[x.tier]
                tested.append((x, replication.test_lead(sb, x, edges, cache.setdefault(x.tier, {}), sa, ratio)))
            log(f"{i + 1}/{len(by_node)} {node}: {len(group)} leads")
        ok = np.array([r["tested"] for _, r in tested], dtype=bool)
        p = np.array([r.get("p", 1.0) for _, r in tested])
        mask = np.zeros(len(p), dtype=bool)
        qv = np.ones(len(p))
        mask[ok] = control.bh(p[ok], q)
        qv[ok] = control.adjusted(p[ok])
        for (x, r), hit, qq in zip(tested, mask, qv, strict=True):
            x.replications = {**x.replications, "split": {**r, "q": float(qq), "ok": bool(hit)}}
            x.replication = control.replication_tier(kinds_of(x))
        a.register.add(selected)
        return selected

    def corroborate(self, register: list[leads.Lead], only_signals: bool = True, replicates: int = 4999,
                    q: float = 0.05, log=print) -> list[leads.Lead]:
        """Ask an independent field (S2iD, SINAN, SIH: `corroborate.RULES`) whether each lead's places and years are
        unusual there, against that field's own null (random same-size place sets of the same states and population
        quintiles). Benjamini-Hochberg within each source. Written to ``lead.replications["corroboration"]``."""
        self._prepare_grid()
        pop = self._pop.sum(1)
        state = (self._grid_places // 10000).astype(int)
        grid = corroborate.Fields(self._grid_places, self._grid_years, state, pop)
        index = {int(p): j for j, p in enumerate(self._grid_places)}
        reg = self.expectations.registry
        done: list[tuple[leads.Lead, corroborate.Corroboration]] = []
        for x in register:
            cls = x.robustness.get("triage", {}).get("class")
            if not x.fields or not x.fields[0].startswith(f"{self.dataset}:") or (only_signals and cls != explain.SIGNAL):
                continue
            node = x.fields[0].split(":")[-1]
            span, direction = replication.span_direction(x)
            rows = np.array([index[int(u)] for u in x.locus.get("places", []) if int(u) in index], dtype=int)
            if rows.size == 0 or not span:
                continue
            c = corroborate.corroborate(grid, node, corroborate.categories_of(reg, node), rows, span, direction,
                                        f"corroborate|{x.id}", replicates)
            done.append((x, c))
            if len(done) % 200 == 0:
                log(f"corroborated {len(done)}")
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
        """Give each lead of the all-data register the split verdict of the side-A lead that is the same finding
        (one that stands on side B), then its tier from the confirmations it holds (`control.replication_tier`)."""
        by_node: dict[str, list[leads.Lead]] = {}
        for a in selected:
            if a.replications.get("split", {}).get("ok"):
                by_node.setdefault(a.fields[0], []).append(a)
        for x in register:
            hits = replication.match(x, by_node.get(x.fields[0], [])) if x.fields else []
            if hits:
                best = min(hits, key=lambda h: h.replications["split"]["q"])
                x.replications = {**x.replications, "split": {**best.replications["split"], "matched": best.id}}
            else:
                x.replications = {k: v for k, v in x.replications.items() if k != "split"}
            x.replication = control.replication_tier(kinds_of(x))
            if x.replication != "R0" and x.status == "open":
                x.status = "replicated"
        return register

    # ---- agents ---------------------------------------------------------------------

    def confirm(self, node: str, lens: str, locus: dict[str, Any], q: float = 0.05) -> dict[str, Any]:
        """One claim, tested once on the reserve (side R) under LOND."""
        return self.confirm_many([(node, lens, locus)], q)[0]

    def confirm_many(self, claims: list[tuple[str, str, dict[str, Any]]], q: float = 0.05) -> list[dict[str, Any]]:
        """Claims (field node, lens, locus with ``places`` and ``years``, and ``direction`` "up"/"down") tested in the
        order given, which must be fixed before the reserve is read, on side R: each locus at its lens's minimum
        effect, the p-values entering the LOND stream of the ledger (`control.Reserve`)."""
        r, a = self.side("R"), self.side("A")
        edges = self.edges() if any(lens == "trend_divergence" for _, lens, _ in claims) else None
        spend, out = [], []
        for node, lens, locus in claims:
            tier = LENS_TIERS.get(lens, "B1")
            res = replication.test_locus(r.surprise(node, tier), lens, locus, -1 if locus.get("direction") == "down" else 1,
                                         edges, None, a.surprise(node, tier), replication.RATIO["R"])
            out.append(res)
            if res["tested"]:
                spend.append((control.Hypothesis("confirm", "agent", {"field": node, "lens": lens, "locus": locus}),
                              res["p"], res.get("effect"), {k: v for k, v in res.items() if k != "p"}))
        verdicts = iter(control.Reserve(self.ledger, q).spend(spend))
        return [{**res, **next(verdicts)} if res["tested"] else res for res in out]


def kinds_of(x: leads.Lead) -> set[str]:
    """The independent confirmations a lead holds: ``split`` (selected on A, standing on B), ``recurs`` (the effect
    in the temporal half it does not touch), ``corroborated`` (an independent field)."""
    r = x.replications
    kinds = set()
    if (r.get("split") or {}).get("ok"):
        kinds.add("split")
    if (r.get("temporal") or {}).get("ok") or (x.estimand == "trend_divergence" and r.get("ok")):
        kinds.add("recurs")
    if (r.get("corroboration") or {}).get("ok"):
        kinds.add("corroborated")
    return kinds
