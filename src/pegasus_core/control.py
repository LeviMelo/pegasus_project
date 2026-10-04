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
    split: str = "all"      # all | temporal:first | temporal:second | spatial:A | spatial:B (reserve)


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


def replication_tier(effect_full: float, p_other: dict[str, tuple[float, float]], alpha: float = 0.05) -> str:
    """The highest tier reached: R1 temporal, R2 spatial, R3 system (ARCHITECTURE §8.3).
    ``p_other`` maps split name → (effect, one-sided p) in that split."""
    def ok(name: str) -> bool:
        if name not in p_other:
            return False
        eff, p = p_other[name]
        return np.sign(eff) == np.sign(effect_full) and abs(eff) >= abs(effect_full) / 2 and p < alpha

    tier = "R0"
    for name, label in (("temporal", "R1"), ("spatial", "R2"), ("system", "R3")):
        if ok(name):
            tier = label
        else:
            break
    return tier
