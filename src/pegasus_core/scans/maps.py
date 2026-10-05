"""Dependency maps: every field against every other, between places (ARCHITECTURE §7.6).

A map is a graph over fields. Its edges are the §7.5 pair test (E_b, the Moran-randomised null of ADR-0005 at the
calibrated δ_E) applied to all the pairs of a field set at once, in two layers:

- **marginal:** E_b for every testable pair;
- **conditional:** E_b|Z for every testable pair, Z the declared context fields other than the pair's own, with
  n_eff − dim(Z). An edge present in both layers is direct; one only in the marginal layer is explained by the
  context; one only in the conditional layer is suppressed by it.

A pair whose events overlap above 0.05 (measured, or unknown) is not tested (§8.5, §11.4). Contexts are not events and
overlap nothing. The error control covers the whole map, one layer at a time: the families are (estimand, field group ×
field group) and the tests are TreeBH over family → pair (Simes at each node), with Benjamini–Yekutieli over the layer
as the stricter alternative. Taxonomic structure (ICD chapters) enters no prior and no edge: the fields are chapters,
side by side.

The false-edge rate of a map is read off ``harness.map_negatives``: the whole map rerun on MSR surrogates of its fields.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pyarrow as pa

from .. import control, store
from . import pairs

MAX_OVERLAP = 0.05
GROUPS = ("SIM", "SIH", "SINASC", "context")


@dataclass
class MapInputs:
    """Place effects of F fields over U places: B, SD [U, F] (NaN where a field is missing), the group of each
    field, and the measured overlap [F, F] (NaN where unknown; 0 where the two cannot share an event)."""
    places: np.ndarray
    names: list[str]
    groups: list[str]
    labels: list[str]
    B: np.ndarray
    SD: np.ndarray
    overlap: np.ndarray
    meta: dict = field(default_factory=dict)

    def subset(self, keep: list[int]) -> MapInputs:
        return MapInputs(self.places, [self.names[i] for i in keep], [self.groups[i] for i in keep],
                         [self.labels[i] for i in keep], self.B[:, keep], self.SD[:, keep],
                         self.overlap[np.ix_(keep, keep)], self.meta)

    def effects(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        return {n: (self.B[:, i], self.SD[:, i]) for i, n in enumerate(self.names)}

    def context_index(self) -> list[int]:
        return [i for i, g in enumerate(self.groups) if g == "context"]

    def design(self, exclude: tuple[int, ...] = ()) -> np.ndarray:
        """The context fields as an adjustment design, a missing value at the field's mean (0, z-scored)."""
        cols = [i for i in self.context_index() if i not in exclude]
        return np.where(np.isfinite(self.B[:, cols]), self.B[:, cols], 0.0)

    def save(self, key: dict) -> None:
        store.put_arrays("maps", key, {"places": self.places, "names": np.array(self.names), "groups": np.array(self.groups),
                                       "labels": np.array(self.labels), "B": self.B, "SD": self.SD, "overlap": self.overlap},
                         {"meta": self.meta})

    @staticmethod
    def load(key: dict) -> MapInputs | None:
        a = store.get_arrays("maps", key)
        if a is None:
            return None
        return MapInputs(a["places"], a["names"].tolist(), a["groups"].tolist(), a["labels"].tolist(), a["B"], a["SD"],
                         a["overlap"], (store.manifest("maps", key) or {}).get("meta", {}))


@dataclass
class DependencyMap:
    edges: pa.Table                  # one row per tested pair, both layers
    tested: dict[str, int]           # pairs tested per layer
    excluded: int                    # pairs left out by overlap
    seconds: float
    controlled: dict[str, dict[str, int]] = field(default_factory=dict)   # layer → method → admitted edges

    def admitted(self, layer: str = "marginal", method: str = "treebh") -> list[dict]:
        col = {"marginal": "admitted", "conditional": "admitted_c"}[layer] if method == "treebh" else \
            {"marginal": "by", "conditional": "by_c"}[layer]
        return [r for r in self.edges.to_pylist() if r[col]]


def testable(inp: MapInputs) -> np.ndarray:
    """[F, F] True where a pair may be tested for dependence: overlap known and ≤ 0.05 (§8.5)."""
    with np.errstate(invalid="ignore"):
        ok = inp.overlap <= MAX_OVERLAP
    return ok & ~np.eye(len(inp.names), dtype=bool)


def _index_pairs(ok: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ii, jj = np.nonzero(np.triu(ok, 1))
    return ii, jj


def _conditional(inp: MapInputs, basis: pairs.MoranBasis, ii: np.ndarray, jj: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ρ̂, n_eff) of every pair given the declared contexts other than the pair's own, with n_eff − dim(Z). The pairs
    share their design in three classes, each one call of ``pairs.statistics``: health × health (all contexts in Z),
    health × context k (all but k), context × context (all but the two)."""
    F = len(inp.names)
    ctx = inp.context_index()
    ctxset = set(ctx)
    R = np.full((F, F), np.nan)
    N = np.full((F, F), np.nan)
    wanted = {(int(i), int(j)) for i, j in zip(ii, jj, strict=True)}
    eff = inp.effects()

    def put(names, Rm, Nm, Z):
        q = Z.shape[1]
        for a, na in enumerate(names):
            for b, nb in enumerate(names):
                i, j = inp.names.index(na), inp.names.index(nb)
                if (min(i, j), max(i, j)) in wanted and np.isfinite(Nm[a, b]):
                    R[i, j] = R[j, i] = Rm[a, b]
                    N[i, j] = N[j, i] = max(Nm[a, b] - q, 3.01)

    health = [i for i in range(F) if i not in ctxset]
    if health:                                                    # health × health
        names, Rm, Nm = pairs.statistics({inp.names[i]: eff[inp.names[i]] for i in health}, basis, inp.design())
        put(names, Rm, Nm, inp.design())
    for k in ctx:                                                 # health × context k
        if not any((min(i, k), max(i, k)) in wanted for i in health):
            continue
        Z = inp.design((k,))
        sub = [inp.names[i] for i in health] + [inp.names[k]]
        names, Rm, Nm = pairs.statistics({n: eff[n] for n in sub}, basis, Z, against=inp.names[k])
        put(names, Rm, Nm, Z)
    for a, k in enumerate(ctx):                                   # context × context
        for l in ctx[a + 1:]:
            if (min(k, l), max(k, l)) in wanted:
                Z = inp.design((k, l))
                sub = [inp.names[k], inp.names[l]]
                names, Rm, Nm = pairs.statistics({n: eff[n] for n in sub}, basis, Z)
                put(names, Rm, Nm, Z)
    return R[ii, jj], N[ii, jj]


def _control(p: np.ndarray, fam: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
    """(TreeBH, BY) admission masks over one layer. The tree is root → family → pair."""
    parent: dict[str, str | None] = {}
    leaf_p: dict[str, float] = {}
    for f in np.unique(fam):
        parent[f"F:{f}"] = None
    for n, (pp, f) in enumerate(zip(p, fam, strict=True)):
        parent[f"P:{n}"] = f"F:{f}"
        leaf_p[f"P:{n}"] = float(pp)
    won = control.tree_bh(leaf_p, parent, q)
    tree = np.array([f"P:{n}" in won for n in range(len(p))])
    return tree, control.bh(p, q, dependence="arbitrary")


def dependency_map(inp: MapInputs, basis: pairs.MoranBasis, ledger: control.Ledger | None = None, tag: str = "map",
                   q: float = 0.05, delta: float | None = None, delta_z: float | None = None,
                   conditional: bool = True) -> DependencyMap:
    """The map of ``inp``: both layers, controlled at q over the whole map. ``ledger``: the tests are registered
    before they run (a map's negatives pass None: they are the harness's, not claims)."""
    t0 = time.time()
    delta = pairs.MIN_EFFECT["E_b"] if delta is None else delta
    delta_z = pairs.MIN_EFFECT["E_b|Z"] if delta_z is None else delta_z
    F = len(inp.names)
    ii, jj = _index_pairs(testable(inp))
    excluded = F * (F - 1) // 2 - len(ii)
    if len(ii) == 0:
        raise ValueError("no testable pair")
    fam = np.array([f"{min(inp.groups[i], inp.groups[j])}x{max(inp.groups[i], inp.groups[j])}" for i, j in
                    zip(ii, jj, strict=True)])
    _, R, N = pairs.statistics(inp.effects(), basis)
    rho, ne = R[ii, jj], N[ii, jj]
    p = pairs.minimum_effect_p(rho, ne, delta)
    out = {"x": [inp.names[i] for i in ii], "y": [inp.names[j] for j in jj], "gx": [inp.groups[i] for i in ii],
           "gy": [inp.groups[j] for j in jj], "family": fam.tolist(), "rho": rho, "n_eff": ne, "p": p}
    tree, by = _control(p, fam, q)
    out |= {"admitted": tree, "by": by}
    controlled = {"marginal": {"treebh": int(tree.sum()), "by": int(by.sum()), "raw": int((p <= q).sum())}}
    if ledger is not None:
        _register(ledger, tag, "E_b", delta, inp, ii, jj, fam, p, rho, ne)
    if conditional:
        rc, nc = _conditional(inp, basis, ii, jj)
        pc = pairs.minimum_effect_p(rc, nc, delta_z)
        pc = np.where(np.isfinite(pc), pc, 1.0)
        tree_c, by_c = _control(pc, fam, q)
        out |= {"rho_c": rc, "n_eff_c": nc, "p_c": pc, "admitted_c": tree_c, "by_c": by_c}
        controlled["conditional"] = {"treebh": int(tree_c.sum()), "by": int(by_c.sum()), "raw": int((pc <= q).sum())}
        if ledger is not None:
            _register(ledger, tag, "E_b|Z", delta_z, inp, ii, jj, fam, pc, rc, nc)
        status = np.where(tree & tree_c, "direct", np.where(tree, "explained", np.where(tree_c, "suppressed", "")))
        out["status"] = status.tolist()
    return DependencyMap(pa.table(out), {"marginal": len(ii), "conditional": len(ii) if conditional else 0}, excluded,
                         time.time() - t0, controlled)


def _register(ledger, tag, estimand, delta, inp, ii, jj, fam, p, rho, ne) -> None:
    ids = ledger.register_many([control.Hypothesis(f"map:{tag}:{estimand}:{f}", "scan", {
        "estimand": estimand, "x": inp.names[i], "y": inp.names[j], "delta": delta})
        for i, j, f in zip(ii, jj, fam, strict=True)])
    ledger.complete_many([(t, float(pp), float(r) if np.isfinite(r) else None, {"n_eff": float(n) if np.isfinite(n) else None})
                          for t, pp, r, n in zip(ids, p, rho, ne, strict=True)])
