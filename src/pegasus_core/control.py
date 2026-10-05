"""Error control: the ledger, FDR, the independent units of replication and the reserve (ARCHITECTURE §8, §9.2).

The ledger is the denominator of every error rate: a test is written before it
runs, with its family, and its result appended when it finishes. FDR is applied
to what the ledger holds, never to a hand-picked list.
"""

from __future__ import annotations

import contextlib
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
_PARTS: dict[Path, pa.Table] = {}      # Ledger part files already read


# ---------------------------------------------------------------------- ledger


@dataclass(frozen=True)
class Hypothesis:
    family: str             # lens or estimand × tier × field family × support (ARCHITECTURE §8.1)
    actor: str              # scan | agent | person
    spec: dict[str, Any]    # what is tested: fields, estimand, tier, scope, null
    split: str = "all"      # all | event:A (the selecting side) | period:reserve (ARCHITECTURE §8.3)


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
        """Every row. The part files are immutable, so each is read once per process (thousands of small files
        make a full read take minutes)."""
        files = sorted(self.path.glob("part-*.parquet"))
        for f in files:
            if f not in _PARTS:
                _PARTS[f] = pq.read_table(f)
        return pa.concat_tables([_PARTS[f] for f in files]) if files else pa.table({})

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
        hit = bool(p <= alpha)          # a Python bool: the ledger stores it as JSON
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


#: The event sides (ARCHITECTURE §8.3). They are **not** a test of anything: the sides of one cell share its
#: frailty. A selects (and fits, where `split-fit` ran); E estimates, a size that selection on A did not bias.
SIDES: dict[str, float] = {"A": 0.5, "E": 0.5}


def event_sides(y: np.ndarray, seed_text: str, fractions: dict[str, float] | None = None) -> dict[str, np.ndarray]:
    """Deal the events of every cell row to the sides by multinomial thinning (fixed seed): stratified by
    cell, a cell's events landing in each side in proportion to its fraction. Given the cell's rate the sides
    are independent Poisson counts, so a size read on E is unbiased for the rate whatever was selected on A."""
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


# ---------------------------------------------------------------------- the reserved periods


#: Periods that no fit, scan or exploration may read (ARCHITECTURE §8.3): the confirmation reserve, by dataset.
#: SIM.DO 2024 is the final file published in December 2025, after every fit and survey (years 2010-2023);
#: the later years are preliminary and incomplete (evaluation 2026-10-05, surveillance lags) and stay unreserved
#: until final. Extending the list is the only way to enlarge the reserve; shrinking it spends it.
RESERVED_PERIODS: dict[str, list[int]] = {"SIM.DO": [2024]}

_RESERVE = threading.local()


class ReservedPeriod(RuntimeError):
    """A fit, a scan or an assembly of events asked for a period held in the confirmation reserve."""


def reserved(dataset: str) -> list[int]:
    return list(RESERVED_PERIODS.get(dataset, []))


def check_reserved(dataset: str, years) -> None:
    """Raise `ReservedPeriod` if ``years`` touch the reserve of ``dataset`` and no claim is being tested. Called by
    the one reader of events (`monolith.assemble`) and by the sessions, so no fit and no scan can read the reserve."""
    hit = sorted({int(y) for y in years} & set(reserved(dataset)))
    if hit and not getattr(_RESERVE, "open", False):
        raise ReservedPeriod(f"{dataset} {hit} belong to the confirmation reserve: only a claim (`Session.confirm`) reads them")


@contextlib.contextmanager
def reserve_open():
    """The reserve is readable inside this block: `Session.confirm_many` uses it, nothing else does."""
    before = getattr(_RESERVE, "open", False)
    _RESERVE.open = True
    try:
        yield
    finally:
        _RESERVE.open = before


class Reserve:
    """The confirmation reserve: the reserved periods of a dataset, spent only by claims, each under one LOND stream.

    What it holds is data that no scan, no refit and no agent's exploration has read, and that did not exist when
    the leads were selected: a claim that a departure persists or recurs is tested on the later period with the
    expectation of a fit that ends before it (`Session.confirm_many`). The p-value of a claim enters the stream,
    whose state (tests so far, rejections so far) is read back from the ledger, so the budget is the ledger's, not
    a session's. The stream is ordered by the caller, and the order must be fixed before the p-values are seen
    (e.g. by the evidence of the selecting survey)."""

    SPLIT = "period:reserve"

    def __init__(self, ledger: Ledger, q: float = 0.05):
        self.ledger, self.q = ledger, q

    def state(self) -> tuple[int, int]:
        """(tests, rejections) spent so far."""
        tested = rejected = 0
        for r in self.ledger.table().to_pylist():
            if r["kind"] == "result" and r.get("result") and '"lond"' in r["result"]:
                tested += 1
                rejected += json.loads(r["result"]).get("rejected") in (True, "True")   # older rows: numpy bool as text
        return tested, rejected

    def level(self) -> float:
        """The level at which the next claim would be tested: q · γ(tests + 1) · (rejections + 1)."""
        lond = LOND(self.q)
        tested, rejected = self.state()
        return float(self.q * lond._gamma(tested + 1) * (rejected + 1))

    def previous(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        """The earlier spend of the same claim (``spec`` without the caller), with its result, or None. The
        reserve is read once per claim: asking again must not buy a second draw."""
        want = json.dumps({k: v for k, v in spec.items() if k != "caller"}, sort_keys=True, default=str)
        rows = self.ledger.table().to_pylist()
        done = {r["id"]: r for r in rows if r["kind"] == "result"}
        for r in rows:
            if r["kind"] == "pending" and r["split"] == self.SPLIT and r["id"] in done:
                have = json.loads(r["spec"])
                if json.dumps({k: v for k, v in have.items() if k != "caller"}, sort_keys=True, default=str) == want:
                    return {"id": r["id"], "at": r["at"], "caller": have.get("caller"), "actor": r["actor"],
                            "p": done[r["id"]]["p"], "result": json.loads(done[r["id"]]["result"])}
        return None

    def spend(self, claims: list[tuple[Hypothesis, float, float | None, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Test the claims in the order given: (hypothesis, p on the reserve, effect, detail) → level and verdict."""
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


#: The kinds of independent confirmation (ARCHITECTURE §8.3). Each is a test on units that took no part in the
#: selection: later years (``temporal``), other places (``spatial``), another record system (``corroborated``).
KINDS = ("temporal", "spatial", "corroborated")


def replication_tier(kinds: set[str]) -> str:
    """The tier of a lead: R0 passes §8.2 on all data, and R_k holds k of the independent confirmations
    (`KINDS`). A one-off event cannot recur and has no other place, so for it R1 is corroboration, and for a
    persistent departure R1 is the later years. The tiers count independent evidence, they are not a ladder of
    strength: which kinds a lead holds is in ``tools.explain_lead``."""
    return f"R{len(set(kinds) & set(KINDS))}"
