"""Error control: the ledger, FDR, the independent units of replication and the reserve (ARCHITECTURE §8, §9.2).

The ledger is the denominator of every error rate: a test is written before it
runs, with its family, and its result appended when it finishes. FDR is applied
to what the ledger holds, never to a hand-picked list.
"""

from __future__ import annotations

import contextlib
import functools
import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
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
        self.path = path or config.home() / f"ledger{config.area_suffix()}"
        self.path.mkdir(parents=True, exist_ok=True)
        self._table: tuple[tuple, pa.Table] | None = None     # (the part files it was made of, the table)

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
        # lanes write and compact one ledger at once: a part listed and then merged away by another process is read
        # from the new listing (an area slice's items failed on it, FileNotFoundError and PermissionError, 2026-10-13)
        for attempt in range(5):
            files = sorted(self.path.glob("part-*.parquet"))
            try:
                for f in files:
                    if f not in _PARTS:
                        _PARTS[f] = pq.read_table(f)
                break
            except (FileNotFoundError, PermissionError):
                if attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))
        if not files:
            return pa.table({})
        if self._table is not None and self._table[0] == tuple(files):
            return self._table[1]            # the parts are immutable: the same listing is the same table
        t = pa.concat_tables([_PARTS[f] for f in files])
        # a row is unique by (id, kind): a part merged by `compact` and not yet removed is read once
        key = pc.binary_join_element_wise(t.column("id"), t.column("kind"), "|").to_numpy(zero_copy_only=False)
        _, first = np.unique(key, return_index=True)
        t = t if len(first) == t.num_rows else t.take(np.sort(first))
        self._table = (tuple(files), t)
        return t

    def compact(self) -> int:
        """Merge the part files into one (the rows unchanged): stage E writes a part per batch, and a field's triage
        left tens of thousands of small files whose full read took minutes (89,361 parts, 2026-10-08). A part that
        cannot be removed (open elsewhere) stays, and `table` reads its rows once. Returns the parts merged."""
        from filelock import FileLock, Timeout

        try:
            lock = FileLock(str(self.path / ".compact.lock"))
            lock.acquire(timeout=0)
        except Timeout:
            return 0                       # another process is compacting
        try:
            files = sorted(self.path.glob("part-*.parquet"))
            if len(files) < 2:
                return 0
            try:
                merged = pa.concat_tables([_PARTS.get(f) or pq.read_table(f) for f in files])
            except (FileNotFoundError, PermissionError):
                return 0                   # the listing changed under it: the next compaction merges it
            name = self.path / f"part-{time.strftime('%Y%m%d%H%M%S')}-compact-{uuid.uuid4().hex[:8]}.parquet"
            tmp = name.with_suffix(".tmp")
            pq.write_table(merged, tmp)
            tmp.replace(name)
            for f in files:
                _PARTS.pop(f, None)
                with contextlib.suppress(OSError):
                    f.unlink()
            return len(files)
        finally:
            lock.release()

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
            # whole or not there: a reader in another lane opened a part being written (PermissionError on Windows)
            tmp = name.with_suffix(".tmp")
            pq.write_table(pa.Table.from_pylist(rows, schema=schema), tmp)
            tmp.replace(name)


# ---------------------------------------------------------------------- FDR


def bh(p: np.ndarray, q: float = 0.05, dependence: str = "positive", weights: np.ndarray | None = None) -> np.ndarray:
    """Benjamini–Hochberg (or Benjamini–Yekutieli for arbitrary dependence): a boolean rejection mask. ``weights``
    (a priori, independent of the p-values under the null; normalised here to mean 1) make it the weighted BH of
    Genovese, Roeder & Wasserman (2006): BH on p / w, which keeps FDR ≤ q. A hypothesis of weight 0 is never rejected
    and gives its share of q to the others (ARCHITECTURE §8.4: weights from the power surface, no exclusion)."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return np.zeros(0, dtype=bool)
    if weights is not None:
        w = np.asarray(weights, dtype=float)
        w = w * (m / w.sum()) if w.sum() > 0 else np.ones(m)
        p = np.divide(p, w, out=np.full(m, np.inf), where=w > 0)
    c = 1.0 if dependence == "positive" else float(np.sum(1.0 / np.arange(1, m + 1)))
    order = np.argsort(p)
    passed = p[order] <= q * np.arange(1, m + 1) / (m * c)
    k = int(np.max(np.nonzero(passed)[0])) + 1 if passed.any() else 0
    out = np.zeros(m, dtype=bool)
    out[order[:k]] = True
    return out


def optimal_weights(xi: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Roeder & Wasserman (2009) optimal weights for one-sided tests whose alternatives sit ``xi`` standard errors
    from the null: w_i = (1/α) Φ̄(ξ_i/2 + c/ξ_i), c chosen so the weights average 1. A hypothesis with ξ ≤ 0 (nothing to
    see) takes weight 0. Each ξ comes from the hypothesis's expectation and dispersion at a reference effect, never from
    its count, so the weights are independent of the p-values under the null (ARCHITECTURE §8.4)."""
    from scipy import optimize, special

    xi = np.asarray(xi, dtype=float)
    live = np.isfinite(xi) & (xi > 1e-9)
    w = np.zeros(len(xi))
    if not live.any():
        return np.ones(len(xi))
    x = xi[live]

    def mean_w(c: float) -> float:
        return float(special.ndtr(-(x / 2 + c / x)).sum() / alpha / len(xi) - 1.0)

    lo, hi = -50.0 * x.max() ** 2, 50.0 * x.max() ** 2
    if mean_w(lo) < 0:            # even the most generous c cannot spend the budget: the live ones share it evenly
        w[live] = len(xi) / live.sum()
        return w
    c = optimize.brentq(mean_w, lo, hi)
    w[live] = special.ndtr(-(x / 2 + c / x)) / alpha
    return w


def adjusted(p: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """BH-adjusted p-values (q-values): the smallest level at which `bh` (with the same ``weights``) rejects a
    hypothesis. Their minimum is the field's Simes p-value."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    if weights is not None:
        w = np.asarray(weights, dtype=float)
        w = w * (m / w.sum()) if w.sum() > 0 else np.ones(m)
        p = np.divide(p, w, out=np.full(m, np.inf), where=w > 0)
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


def bogomolov(field_p: np.ndarray, q: float = 0.05) -> tuple[np.ndarray, float, np.ndarray]:
    """Benjamini–Bogomolov selective inference (ARCHITECTURE §8.2) for one family of fields, ``field_p`` each field's
    p-value (its Simes p-value over everything it tested, 1 for a field that tested nothing: the number of fields
    asked, not of those with a finding, is the family). Fields are selected by BH at q; inside a selected field the
    hypotheses are tested by BH at q · |selected| / |fields|. Returns the selection, that level and each field's
    BH-adjusted p."""
    field_p = np.asarray(field_p, dtype=float)
    selected = bh(field_p, q)
    return selected, (q * selected.sum() / len(field_p) if len(field_p) else 0.0), adjusted(field_p)


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


@functools.cache
def _lond_norm() -> float:
    """The normaliser of LOND's gamma sequence, summed once per process (a hundred thousand logarithms each time)."""
    return sum(1.0 / (i * np.log(i + 1) ** 2) for i in range(1, 100_000))


class LOND:
    """Online FDR for a stream of claims (Javanmard & Montanari 2018): the i-th test
    is run at α_i = q · γ_i · (rejections so far + 1), γ_i ∝ 1/(i (log i)²)."""

    def __init__(self, q: float = 0.05):
        self.q = q
        self.tested = 0
        self.rejected = 0
        norm = _lond_norm()
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
#: Reserved years read before any claim, and how: a confirmation on them is not on unseen data, and its record says so.
#: SIM.DO 2024 was read by fits, fields, corroboration and SIM-SIH link runs of studies that spelled it SIM-DO, which
#: the reserve did not recognise until 2026-10-11 (178 store entries quarantined, 80 leads retired).
RESERVE_SEEN: dict[str, dict[int, str]] = {"SIM.DO": {2024: "read during selection by SIM-DO studies before 2026-10-11"}}

_RESERVE = threading.local()


class ReservedPeriod(RuntimeError):
    """A fit, a scan or an assembly of events asked for a period held in the confirmation reserve."""


def reserved(dataset: str) -> list[int]:
    """The reserved years of ``dataset``, whatever its spelling: keyed by spelling, the reserve of SIM.DO did not stop
    the studies, which spell it SIM-DO, from reading 2024 (2026-10-11)."""
    from pegasus_data._request import parse_dataset

    def canon(name: str) -> tuple:
        try:
            return parse_dataset(name)
        except Exception:  # noqa: BLE001 - a name pegasus_data does not parse is compared as written
            return (name, None)

    want = canon(dataset)
    return sorted({y for name, ys in RESERVED_PERIODS.items() if canon(name) == want for y in ys})


def reserve_seen(dataset: str) -> dict[int, str]:
    """The reserved years of ``dataset`` that were read before any claim (`RESERVE_SEEN`), with how."""
    from pegasus_data._request import parse_dataset

    want = parse_dataset(dataset)
    return {y: why for name, ys in RESERVE_SEEN.items() if parse_dataset(name) == want for y, why in ys.items()}


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


_RESERVE_PARTS: dict[Path, tuple[list[tuple[str, float, str]], list[dict[str, Any]]]] = {}   # a part's reserve rows
_RESERVE_GUARD = threading.Lock()
_RESERVE_LOCKS: dict[str, tuple[Any, Any]] = {}


def _reserve_part(f: Path, split: str) -> tuple[list[tuple[str, float, str]], list[dict[str, Any]]]:
    """What one ledger part holds of the reserve, read once (a part is immutable): its LOND results (claim id, p,
    result JSON: the rows whose result names "lond", found by a substring match on the column) and its claims (the
    pending rows of ``split``: id, when, actor, spec). Only the columns a match needs are read; the spec's column only
    for a part that holds a claim."""
    got = _RESERVE_PARTS.get(f)
    if got is None:
        t = _PARTS[f] if f in _PARTS else pq.read_table(f, columns=["id", "kind", "split", "p", "result"])
        is_lond = pc.fill_null(pc.and_(pc.equal(t.column("kind"), "result"),
                                       pc.match_substring(t.column("result"), '"lond"')), False)
        rows = t.filter(is_lond)
        results = list(zip(rows.column("id").to_pylist(), rows.column("p").to_pylist(),
                           rows.column("result").to_pylist(), strict=True))
        is_claim = pc.fill_null(pc.and_(pc.equal(t.column("kind"), "pending"), pc.equal(t.column("split"), split)), False)
        claims: list[dict[str, Any]] = []
        if pc.any(is_claim).as_py():
            full = _PARTS[f] if f in _PARTS else pq.read_table(f, columns=["id", "kind", "split", "at", "actor", "spec"])
            claims = full.filter(is_claim).select(["id", "at", "actor", "spec"]).to_pylist()
        got = _RESERVE_PARTS[f] = (results, claims)
    return got


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

    def ledgers(self) -> list[Path]:
        """The ledgers the reserve is counted over: the one given, the home's own (`ledger`) and every area's
        (`ledger_area_*`). The reserve is one finite resource of the home, not of an area: each area's ledger had
        started its own LOND stream on it, at full wealth, and a claim spent in one was unknown to the others."""
        home = config.home()
        found = {self.ledger.path.resolve()}
        found |= {p.resolve() for p in [home / "ledger", *home.glob("ledger_area_*")] if p.is_dir()}
        return sorted(found)

    @contextlib.contextmanager
    def locked(self):
        """The reserve's state is read, a claim registered and its verdict written under one lock (a file lock on the
        home, across processes, and a thread lock): two lanes spending at once had read the same state and tested at
        the same gamma_i."""
        from filelock import FileLock

        key = str(config.home() / "reserve.lock")
        with _RESERVE_GUARD:
            thread_lock, file_lock = _RESERVE_LOCKS.setdefault(key, (threading.RLock(), FileLock(key)))
        with thread_lock, file_lock:
            yield

    def _read(self) -> tuple[dict[str, tuple[float, str]], dict[str, dict[str, Any]]]:
        """(the LOND results by claim id: p and result JSON, the claims' pending rows by id) over the reserve's ledgers.
        Arrow-side and per part: a part is read once per process (`_reserve_part`), and only the rows of a claim reach
        Python (the whole ledger's rows as Python objects took most of the 72.7 s of a state read, 83 MB, 2026-10-14)."""
        for attempt in range(5):
            results: dict[str, tuple[float, str]] = {}
            claims: dict[str, dict[str, Any]] = {}
            try:
                for path in self.ledgers():
                    for f in sorted(path.glob("part-*.parquet")):
                        part_results, part_claims = _reserve_part(f, self.SPLIT)
                        for i, p, r in part_results:
                            results.setdefault(i, (p, r))
                        for c in part_claims:
                            claims.setdefault(c["id"], c)
                return results, claims
            except (FileNotFoundError, PermissionError):        # a part merged away by `compact` while listed
                if attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))
        raise AssertionError("unreachable")

    def state(self) -> tuple[int, int]:
        """(tests, rejections) spent so far, over every ledger of the reserve."""
        results, _ = self._read()
        # older rows hold a numpy bool as text
        return len(results), sum(json.loads(r).get("rejected") in (True, "True") for _, r in results.values())

    def level(self) -> float:
        """The level at which the next claim would be tested: q * gamma(tests + 1) * (rejections + 1)."""
        return self.status()["next_level"]

    def status(self) -> dict[str, Any]:
        """{spent, rejections, next_level} from one read of the reserve."""
        tested, rejected = self.state()
        return {"spent": tested, "rejections": rejected,
                "next_level": float(self.q * LOND(self.q)._gamma(tested + 1) * (rejected + 1))}

    @staticmethod
    def _spec_key(spec: dict[str, Any]) -> str:
        """A claim's identity: its spec without the caller (who asked does not make another claim)."""
        return json.dumps({k: v for k, v in spec.items() if k != "caller"}, sort_keys=True, default=str)

    def _spent(self) -> dict[str, dict[str, Any]]:
        """The claims already spent, by identity (the first of a repeated claim): id, when, caller, actor, p, result."""
        results, claims = self._read()
        out: dict[str, dict[str, Any]] = {}
        for i, c in claims.items():
            if i in results:
                have = json.loads(c["spec"])
                out.setdefault(self._spec_key(have), {"id": i, "at": c["at"], "caller": have.get("caller"),
                                                      "actor": c["actor"], "p": results[i][0],
                                                      "result": json.loads(results[i][1])})
        return out

    def previous(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        """The earlier spend of the same claim (``spec`` without the caller), with its result, or None. The
        reserve is read once per claim: asking again must not buy a second draw."""
        return self._spent().get(self._spec_key(spec))

    def spend(self, claims: list[tuple[Hypothesis, float, float | None, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Test the claims in the order given: (hypothesis, p on the reserve, effect, detail) -> level and verdict. All
        under the reserve's lock, state read to verdict written: a claim already spent (by anyone, in any ledger of the
        reserve) is not tested again, its earlier verdict is returned with ``repeated`` True."""
        with self.locked():
            lond = LOND(self.q)
            lond.tested, lond.rejected = self.state()
            earlier = self._spent()
            keys = [self._spec_key(h.spec) for h, *_ in claims]
            fresh = [(k, c) for j, (k, c) in enumerate(zip(keys, claims, strict=True))
                     if k not in earlier and k not in keys[:j]]
            ids = self.ledger.register_many([Hypothesis(h.family, h.actor, h.spec, self.SPLIT) for _, (h, *_) in fresh])
            verdicts, done = {}, []
            for i, (k, (_, p, effect, detail)) in zip(ids, fresh, strict=True):
                level = self.q * lond._gamma(lond.tested + 1) * (lond.rejected + 1)
                hit = lond.test(p)
                done.append((i, p, effect, {**detail, "lond": True, "rejected": hit, "level": level}))
                verdicts[k] = {"p": p, "level": level, "rejected": hit}
            self.ledger.complete_many(done)
        out, given = [], set()
        for k in keys:
            if k in verdicts and k not in given:
                out.append(verdicts[k])
            elif k in verdicts:
                out.append({**verdicts[k], "repeated": True})
            else:
                prev = earlier[k]
                out.append({"p": prev["p"], "level": prev["result"].get("level"),
                            "rejected": prev["result"].get("rejected"), "repeated": True})
            given.add(k)
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
