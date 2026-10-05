"""Error control: the ledger, FDR, splits and replication (ARCHITECTURE §8, §9.2).

The ledger is the denominator of every error rate: a test is written before it
runs, with its family, and its result appended when it finishes. FDR is applied
to what the ledger holds, never to a hand-picked list.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config

_LOCK = threading.Lock()


# ---------------------------------------------------------------------- ledger


@dataclass(frozen=True)
class Hypothesis:
    family: str             # lens or estimand × tier × field family × support (ARCHITECTURE §8.1)
    actor: str              # scan | agent | person
    spec: dict[str, Any]    # what is tested: fields, estimand, tier, scope, null
    split: str = "all"      # all | event:A | event:B | event:R (the reserve; ARCHITECTURE §8.3)


class Ledger:
    """Append-only: ``pending`` rows when a test is registered, ``result`` rows when it finishes."""

    def __init__(self, path: Path | None = None):
        self.path = path or config.home() / "ledger"
        self.path.mkdir(parents=True, exist_ok=True)

    def register(self, h: Hypothesis) -> str:
        return self.register_many([h])[0]

    def register_many(self, hs: list[Hypothesis]) -> list[str]:
        """Write the tests before they run (one file per batch)."""
        ids = [uuid.uuid4().hex[:16] for _ in hs]
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._append([{"id": i, "kind": "pending", "family": h.family, "actor": h.actor, "split": h.split,
                       "spec": json.dumps(h.spec, sort_keys=True, default=str), "p": None, "effect": None,
                       "result": None, "code_version": config.code_version(),
                       "data_version": config.data_code_version(), "at": now} for i, h in zip(ids, hs, strict=True)])
        return ids

    def complete(self, test_id: str, p: float, effect: float | None, result: dict[str, Any]) -> None:
        self.complete_many([(test_id, p, effect, result)])

    def complete_many(self, rows: list[tuple[str, float, float | None, dict[str, Any]]]) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._append([{"id": i, "kind": "result", "family": None, "actor": None, "split": None, "spec": None,
                       "p": float(p), "effect": None if e is None else float(e),
                       "result": json.dumps(r, default=str), "code_version": config.code_version(),
                       "data_version": config.data_code_version(), "at": now} for i, p, e, r in rows])

    def table(self) -> pa.Table:
        files = sorted(self.path.glob("part-*.parquet"))
        return pa.concat_tables([pq.read_table(f) for f in files]) if files else pa.table({})

    def family(self, family: str) -> list[dict[str, Any]]:
        """Registered tests of a family with their results (a test without a result counts as p = 1)."""
        rows = self.table().to_pylist()
        pending = {r["id"]: r for r in rows if r["kind"] == "pending" and r["family"] == family}
        results = {r["id"]: r for r in rows if r["kind"] == "result" and r["id"] in pending}
        return [{**pending[i], "p": results[i]["p"] if i in results else 1.0,
                 "effect": results[i]["effect"] if i in results else None,
                 "result": results[i]["result"] if i in results else None} for i in pending]

    def _append(self, rows: list[dict[str, Any]]) -> None:
        schema = pa.schema([("id", pa.string()), ("kind", pa.string()), ("family", pa.string()),
                            ("actor", pa.string()), ("split", pa.string()), ("spec", pa.string()),
                            ("p", pa.float64()), ("effect", pa.float64()), ("result", pa.string()),
                            ("code_version", pa.string()), ("data_version", pa.string()), ("at", pa.string())])
        with _LOCK:
            name = self.path / f"part-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}.parquet"
            pq.write_table(pa.Table.from_pylist(rows, schema=schema), name)


# ---------------------------------------------------------------------- FDR


def bh(p: np.ndarray, q: float = 0.05, dependence: str = "positive") -> np.ndarray:
    """Benjamini–Hochberg (or Benjamini–Yekutieli for arbitrary dependence): a boolean rejection mask."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return np.zeros(0, dtype=bool)
    c = 1.0 if dependence == "positive" else float(np.sum(1.0 / np.arange(1, m + 1)))
    order = np.argsort(p)
    passed = p[order] <= q * np.arange(1, m + 1) / (m * c)
    k = int(np.max(np.nonzero(passed)[0])) + 1 if passed.any() else 0
    out = np.zeros(m, dtype=bool)
    out[order[:k]] = True
    return out


def adjusted(p: np.ndarray) -> np.ndarray:
    """BH-adjusted p-values (q-values)."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p)
    q = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def simes(p: np.ndarray) -> float:
    """Simes' combination: the family-level p-value used to select families."""
    p = np.sort(np.asarray(p, dtype=float))
    m = len(p)
    return float(np.min(p * m / np.arange(1, m + 1))) if m else 1.0


def bogomolov(families: dict[str, np.ndarray], q: float = 0.05) -> dict[str, np.ndarray]:
    """Benjamini–Bogomolov selective inference across families (ARCHITECTURE §8.2):
    select families by BH on their Simes p-values; inside each selected family,
    BH at q · |selected| / |families|."""
    names = list(families)
    family_p = np.array([simes(families[n]) for n in names])
    selected = bh(family_p, q)
    level = q * selected.sum() / max(len(names), 1)
    return {n: (bh(families[n], level) if s else np.zeros(len(families[n]), dtype=bool))
            for n, s in zip(names, selected, strict=True)}


def tree_bh(p_leaf: dict[str, float], parent: dict[str, str | None], q: float = 0.05) -> set[str]:
    """TreeBH (Bogomolov, Peterson, Benjamini & Sabatti 2021), simplified to Simes
    aggregation: test the root's children; descend only into rejected nodes, each
    family tested at q · (rejected fraction of the families above it)."""
    children: dict[str | None, list[str]] = {}
    for node, par in parent.items():
        children.setdefault(par, []).append(node)
    leaves_under: dict[str, list[str]] = {}

    def collect(node: str) -> list[str]:
        if node not in leaves_under:
            kids = children.get(node, [])
            leaves_under[node] = [node] if not kids else [x for k in kids for x in collect(k)]
        return leaves_under[node]

    def node_p(node: str) -> float:
        ps = np.array([p_leaf[x] for x in collect(node) if x in p_leaf])
        return simes(ps) if len(ps) else 1.0

    rejected: set[str] = set()
    frontier: list[tuple[str | None, float]] = [(None, q)]
    while frontier:
        par, level = frontier.pop()
        kids = [k for k in children.get(par, []) if any(x in p_leaf for x in collect(k))]
        if not kids:
            continue
        ps = np.array([node_p(k) for k in kids])
        mask = bh(ps, level)
        frac = mask.sum() / len(kids)
        for k, r in zip(kids, mask, strict=True):
            if r:
                rejected.add(k)
                frontier.append((k, level * frac))
    return rejected


class LOND:
    """Online FDR for a stream of claims (Javanmard & Montanari 2018): the i-th test
    is run at α_i = q · γ_i · (rejections so far + 1), γ_i ∝ 1/(i (log i)²)."""

    def __init__(self, q: float = 0.05):
        self.q = q
        self.tested = 0
        self.rejected = 0
        norm = sum(1.0 / (i * np.log(i + 1) ** 2) for i in range(1, 100_000))
        self._gamma = lambda i: 1.0 / (i * np.log(i + 1) ** 2) / norm

    def test(self, p: float) -> bool:
        self.tested += 1
        alpha = self.q * self._gamma(self.tested) * (self.rejected + 1)
        hit = p <= alpha
        self.rejected += int(hit)
        return hit


# ---------------------------------------------------------------------- splits


def temporal_halves(years: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    years = np.sort(np.asarray(years))
    mid = (years[0] + years[-1]) / 2
    return years[years <= mid], years[years > mid]


def spatial_halves(places: np.ndarray, region_of: dict[int, str], seed_text: str = "spatial-halves-v1"
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Places split by immediate region, half of the regions of each state on each side (fixed seed).
    Side B is the agents' confirmation reserve."""
    regions = sorted({region_of[int(u)] for u in places})
    by_state: dict[str, list[str]] = {}
    for r in regions:
        by_state.setdefault(str(r)[:2], []).append(r)
    rng = np.random.default_rng(config.seed(seed_text))
    side_a: set[str] = set()
    for state in sorted(by_state):
        rs = by_state[state]
        pick = rng.permutation(len(rs))[: (len(rs) + 1) // 2]
        side_a.update(rs[i] for i in pick)
    in_a = np.array([region_of[int(u)] in side_a for u in places])
    return places[in_a], places[~in_a]


def replicates(effect_full: float, effect: float, p: float, alpha: float = 0.05) -> bool:
    """One split replicates the full-data effect: same sign, at least half its size, one-sided p below alpha."""
    return bool(np.isfinite(effect) and np.sign(effect) == np.sign(effect_full)
                and abs(effect) >= abs(effect_full) / 2 and p < alpha)


#: The event sides (ARCHITECTURE §8.3): A explores, selects and fits the expectation; B is the scheduled
#: survey's one test of what A selected; R is the confirmation reserve, spent by claims under LOND.
SIDES: dict[str, float] = {"A": 0.5, "B": 0.3, "R": 0.2}


def event_sides(y: np.ndarray, seed_text: str, fractions: dict[str, float] | None = None) -> dict[str, np.ndarray]:
    """Deal the events of every cell row to the sides by multinomial thinning (fixed seed): stratified by
    cell, a cell's events landing in each side in proportion to its fraction. Under a Poisson count the
    sides are independent given the rate, and under a negative binomial their sizes stay the same
    (a thinned NB(n, p) is an NB with the same n), so a side's expectation is the fraction times the whole's."""
    fractions = fractions or SIDES
    rng = np.random.default_rng(config.seed(seed_text))
    left = np.rint(y).astype(np.int64)
    out: dict[str, np.ndarray] = {}
    remaining = 1.0
    names = list(fractions)
    for name in names[:-1]:
        take = rng.binomial(left, min(fractions[name] / remaining, 1.0))
        out[name] = take
        left = left - take
        remaining -= fractions[name]
    out[names[-1]] = left
    return out


class Reserve:
    """The confirmation reserve: side R of the events, spent only by claims, each under one LOND stream.

    What it holds is the fraction ``SIDES["R"]`` of every cell's events, which no scan, no refit and no
    agent's exploration has read. A claim is one fixed locus tested on those events; its p-value enters
    the stream, whose state (tests so far, rejections so far) is read back from the ledger, so the budget is
    the ledger's, not a session's. The stream is ordered by the caller, and the order must be fixed before
    the p-values are seen (e.g. by the A-side evidence)."""

    SPLIT = "event:R"

    def __init__(self, ledger: Ledger, q: float = 0.05):
        self.ledger, self.q = ledger, q

    def state(self) -> tuple[int, int]:
        """(tests, rejections) spent so far."""
        tested = rejected = 0
        for r in self.ledger.table().to_pylist():
            if r["kind"] == "result" and r.get("result") and '"lond"' in r["result"]:
                tested += 1
                rejected += int(json.loads(r["result"]).get("rejected", False))
        return tested, rejected

    def spend(self, claims: list[tuple[Hypothesis, float, float | None, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Test the claims in the order given: (hypothesis, p on side R, effect, detail) → level and verdict."""
        lond = LOND(self.q)
        lond.tested, lond.rejected = self.state()
        ids = self.ledger.register_many([Hypothesis(h.family, h.actor, h.spec, self.SPLIT) for h, *_ in claims])
        out, done = [], []
        for i, (_, p, effect, detail) in zip(ids, claims, strict=True):
            level = self.q * lond._gamma(lond.tested + 1) * (lond.rejected + 1)
            hit = lond.test(p)
            done.append((i, p, effect, {**detail, "lond": True, "rejected": hit, "level": level}))
            out.append({"p": p, "level": level, "rejected": hit})
        self.ledger.complete_many(done)
        return out


def replication_tier(kinds: set[str]) -> str:
    """The tier of a lead from the independent confirmations it has (ARCHITECTURE §8.3). R0 passes §8.2 on
    all data. Every higher tier needs R1, the honest split: selected on side A, tested on side B. R2 adds the
    recurrence of the effect in the temporal half it does not touch; R3 adds corroboration by an independent
    field (a one-off event cannot recur, so this is its way up). Recurrence and corroboration are not ordered
    by the other; the tier is the highest reached."""
    if "split" not in kinds:
        return "R0"
    if "corroborated" in kinds:
        return "R3"
    return "R2" if "recurs" in kinds else "R1"
