"""Pairs: dependence between fields at their common support (ARCHITECTURE §7.5).

All pairs of one estimand come from one weighted Gram matrix. Weights factor
per field (a = √w ⊙ (x − x̄_w)), so ρ_XY = aᵀb / (‖a‖‖b‖): the pair's weight is
√(w_X w_Y), the geometric mean of the two fields' information.

Effective sample sizes respect each field's own dependence:
- between places (E_b): Moran spectral randomisation, in closed form. The Moran eigenvectors of the
  place graph are those of the doubly-centred symmetric-normalised adjacency D^-½ W D^-½ (a graph
  Fourier basis ordered by scale). Under H0 one field's place effects e_Y (the weighted-least-squares
  residual on the adjustment design Z) have random signs on their coordinates c_k; the weights come
  afterwards, so the numerator a_Xᵀ(√w_Y ⊙ e*_Y) = Σ_k s_k c_k (Vᵀh)_k with h = √w_Y ⊙ Q_Y a_X (Q_Y
  projects off √w_Y ⊙ Z). Its variance is σ² = Σ_k c_k² (Vᵀh)_k² / (‖a_X‖²‖a_Y‖²), the larger of
  the two orders of (X, Y), and n_eff = 3 + 1/σ². Randomising the weighted field a_Y instead would
  treat the weights as part of the spatial pattern, and with concentrated weights (the effective
  sample size of √(w_X w_Y) is 385 of 5,570) it understates σ two- to fivefold: 0.019 against a true
  0.092 for two outcomes (evaluation 2026-10-05);
- within places (E_w): AR(1) per field, n_eff,u = T (1 − a_X a_Y)/(1 + a_X a_Y),
  summed over places and divided by the design effect 1 + (U−1) ρ̄_space.

Every pair is tested against its minimum relevant effect: H0 |ρ| ≤ δ, with δ_E from the harness
(ARCHITECTURE §8.4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import torch
from scipy import special, stats

from .. import config, control, graphs, store

# Minimum effects δ_E (ARCHITECTURE §8.4): H0 is |ρ| ≤ δ_E. E_b and E_b|Z are the smallest δ at which the false-lead
# rate on the harness's negative controls is ≤ q (evaluation 2026-10-05); E_w is provisional.
MIN_EFFECT = {"E_b": 0.03, "E_b|Z": 0.05, "E_w": 0.1}
BASIS_GRAPH = "contiguity01"  # the place graph whose Moran basis tests E_b


@dataclass
class Pair:
    estimand: str
    x: str
    y: str
    rho: float
    n_eff: float
    p: float
    delta: float
    lag: int = 0


def minimum_effect_p(rho: np.ndarray, n_eff: np.ndarray, delta: float) -> np.ndarray:
    """H0: |ρ| ≤ δ.  z = (atanh|ρ̂| − atanh δ)·√(n_eff − 3),  p = 1 − Φ(z)."""
    r = np.clip(np.abs(rho), 0, 1 - 1e-12)
    z = (np.arctanh(r) - np.arctanh(delta)) * np.sqrt(np.maximum(n_eff - 3, 1e-9))
    return special.ndtr(-z)


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _gram(A: np.ndarray) -> np.ndarray:
    """Correlation of factorised-weighted columns: A [n, F] already centred and weighted."""
    t = torch.as_tensor(A, dtype=torch.float32, device=_device())
    G = t.T @ t
    d = torch.sqrt(torch.clamp(torch.diag(G), min=1e-30))
    return (G / d[:, None] / d[None, :]).double().cpu().numpy()


def _weighted(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """√w ⊙ (x − x̄_w), column by column; non-finite entries carry no weight."""
    w = np.where(np.isfinite(x) & np.isfinite(w), w, 0.0)
    x = np.where(np.isfinite(x), x, 0.0)
    mean = (w * x).sum(0) / np.maximum(w.sum(0), 1e-300)
    return np.sqrt(w) * (x - mean)


# ---------------------------------------------------------------------- the Moran basis


class MoranBasis:
    """Moran eigenvectors of a place graph: the eigenvectors of H D^-½ W D^-½ H (H centres). The
    symmetric normalisation makes them scale-ordered graph Fourier modes; the raw weight matrix W
    does not (its top eigenvectors localise on hubs, and sign randomisation on them keeps almost no
    long-range structure: evaluation 2026-10-05). Computed once per graph and cached."""

    def __init__(self, places: np.ndarray, kind: str = BASIS_GRAPH):
        self.kind, self.n = kind, len(places)
        key = {"what": "moran_basis", "kind": kind, "places": self.n, "first": int(places[0]), "last": int(places[-1]),
               "sum": int(np.sum(places)), "resource": config.resource_version("proximity.parquet"), "v": 1}
        hit = store.get_arrays("graphs", key)
        if hit is None:
            hit = self._decompose(places, kind)
            store.put_arrays("graphs", key, hit)
        self.values, self.vectors = hit["values"], hit["vectors"]
        self._gpu = None

    @staticmethod
    def _decompose(places: np.ndarray, kind: str) -> dict[str, np.ndarray]:
        edges, weights = graphs.graph(places, kind)
        n = len(places)
        e = torch.as_tensor(edges, device=_device())
        W = torch.zeros((n, n), dtype=torch.float64, device=_device())
        W[e[:, 0], e[:, 1]] = torch.as_tensor(weights, dtype=torch.float64, device=_device())
        W = torch.maximum(W, W.T)
        d = W.sum(1).clamp(min=1e-12).sqrt()
        M = W / d[:, None] / d[None, :]
        M = M - M.mean(0, keepdim=True) - M.mean(1, keepdim=True) + M.mean()      # H M H
        for attempt in range(4):
            try:
                vals, vecs = torch.linalg.eigh(M)
                break
            except RuntimeError:           # the GPU is shared: a transient allocation failure
                torch.cuda.empty_cache()
                time.sleep(5 * (attempt + 1))
        else:
            vals, vecs = (torch.as_tensor(a) for a in np.linalg.eigh(M.cpu().numpy()))
        return {"values": vals.cpu().numpy(), "vectors": vecs.cpu().numpy().astype(np.float32)}

    def _v(self) -> torch.Tensor:
        if self._gpu is None:
            self._gpu = torch.as_tensor(self.vectors, device=_device())
        return self._gpu

    def randomise(self, x: np.ndarray, rng: np.random.Generator, shared: bool = False) -> np.ndarray:
        """MSR (Wagner & Dray 2015): random signs on the Moran-eigenvector coordinates of x [n] or [n, R].
        ``shared``: one sign vector for all R columns, so the columns' dependence (a field's years) is kept."""
        x2 = x[:, None] if x.ndim == 1 else x
        mean = x2.mean(0)
        t = torch.as_tensor(x2 - mean, dtype=torch.float32, device=_device())
        size = (t.shape[0], 1) if shared else t.shape
        signs = torch.as_tensor(rng.choice([-1.0, 1.0], size=size), dtype=torch.float32, device=_device())
        out = (self._v() @ ((self._v().T @ t) * signs)).double().cpu().numpy() + mean
        return out[:, 0] if x.ndim == 1 else out


# ---------------------------------------------------------------------- estimands


def statistics(effects: dict[str, tuple[np.ndarray, np.ndarray]], basis: MoranBasis, Z: np.ndarray | None = None,
               rank: bool = False, against: str | None = None) -> tuple[list[str], np.ndarray, np.ndarray]:
    """(names, ρ̂, n_eff) for every pair of E_b place effects b̂(u) with their sd, optionally adjusted for a design
    Z [n, q]: each field is residualised on [1, Z] under its own weights. ``against`` restricts the n_eff to the pairs
    that contain that field (the others are NaN): the harness's negative controls need nothing else."""
    names = list(effects)
    B = np.stack([effects[k][0] for k in names], axis=1)
    W = np.stack([1.0 / np.maximum(effects[k][1], 1e-6) ** 2 for k in names], axis=1)
    if rank:
        B = np.apply_along_axis(stats.rankdata, 0, B)
    W = np.where(np.isfinite(B) & np.isfinite(W), W, 0.0)          # a missing value carries no weight
    B = np.where(np.isfinite(B), B, 0.0)
    n, F = B.shape
    Zc = np.ones((n, 1)) if Z is None else np.column_stack([np.ones(n), Z])
    E, A = np.empty_like(B), np.empty_like(B)
    for f in range(F):
        sw = np.sqrt(W[:, f])
        coef, *_ = np.linalg.lstsq(Zc * sw[:, None], sw * B[:, f], rcond=None)
        E[:, f] = B[:, f] - Zc @ coef                              # the field net of Z, weighted-least-squares
        A[:, f] = sw * E[:, f]
    return names, _gram(A), _n_eff(A, E, np.sqrt(W), Zc, basis, None if against is None else names.index(against))


def _n_eff(A: np.ndarray, E: np.ndarray, SW: np.ndarray, Zc: np.ndarray, basis: MoranBasis,
           target: int | None) -> np.ndarray:
    """n_eff = 3 + 1/σ² for pairs of columns (see the module docstring), on the GPU, one randomised field Y at a time."""
    dev = _device()
    n, F = A.shape
    V = basis._v()
    At = torch.as_tensor(A, dtype=torch.float32, device=dev)
    Et = torch.as_tensor(E - E.mean(0), dtype=torch.float32, device=dev)
    c2 = (V.T @ Et) ** 2                                           # [k, F]: energy of each field per eigenvector
    norm = (At ** 2).sum(0).clamp(min=1e-30)
    SWt = torch.as_tensor(SW, dtype=torch.float32, device=dev)
    Zt = torch.as_tensor(Zc, dtype=torch.float64, device=dev)
    sigma2 = torch.full((F, F), float("nan"), dtype=torch.float64, device=dev)
    for y in range(F):
        xs = list(range(F)) if target is None or y == target else [target]
        T = (SWt[:, y:y + 1].double() * Zt)                        # √w_Y ⊙ Z, the span Q_Y projects off
        Xs = At[:, xs].double()
        QX = (Xs - T @ torch.linalg.solve(T.T @ T + 1e-12 * torch.eye(T.shape[1], dtype=torch.float64, device=dev),
                                          T.T @ Xs)).float()
        PH = V.T @ (SWt[:, y:y + 1] * QX)                          # [k, len(xs)]
        sigma2[xs, y] = ((c2[:, y:y + 1] * PH ** 2).sum(0) / (norm[xs] * norm[y])).double()
    s2 = torch.fmax(sigma2, sigma2.T).cpu().numpy()                # the larger of the two orders
    return np.clip(3 + 1 / np.maximum(s2, 1e-12), 3.0, float(n))


def between(effects: dict[str, tuple[np.ndarray, np.ndarray]], basis: MoranBasis, ledger: control.Ledger,
            family: str, delta: float | None = None, Z: np.ndarray | None = None, rank: bool = False,
            testable=None) -> list[Pair]:
    """E_b (or E_b|Z with an adjustment design Z [n, q]). ``testable(x, y)`` excludes pairs with
    overlap above 0.05 (or unknown)."""
    names, R, n_eff = statistics(effects, basis, Z, rank)
    estimand = "E_b|Z" if Z is not None else "E_b"
    return _test(estimand, names, R, n_eff, MIN_EFFECT[estimand] if delta is None else delta, ledger, family, testable, 0)


def within(surprises: dict, ledger: control.Ledger, family: str, lag: int = 0, delta: float = MIN_EFFECT["E_w"],
           rank: bool = False, testable=None, excluded: dict | None = None) -> list[Pair]:
    """E_w at lag ℓ (Y follows X by ℓ periods) on calibrated surprises z with their weights w. A surprise whose
    calibration failed at its tier is left out (ARCHITECTURE §11.4) and named in ``excluded`` (name → KS record)."""
    failed = {k: {"tier": v.tier, "ks": v.calibration.get("ks"),
                   "worst_region": max(v.calibration.get("ks_by_macroregion", {}).values(), default=None)}
              for k, v in surprises.items() if v.calibration.get("calibrated") is False}
    if excluded is not None:
        excluded.update(failed)
    surprises = {k: v for k, v in surprises.items() if k not in failed}
    names = list(surprises)
    if len(names) < 2:
        return []
    first = surprises[names[0]]
    U, T = first.z.shape
    Tl = T - lag
    if Tl < 3:
        raise ValueError(f"lag {lag} leaves {Tl} periods")
    Zx = np.stack([surprises[k].z[:, :Tl].ravel() for k in names], axis=1)
    Zy = np.stack([surprises[k].z[:, lag:].ravel() for k in names], axis=1)
    Wx = np.stack([surprises[k].w[:, :Tl].ravel() for k in names], axis=1)
    Wy = np.stack([surprises[k].w[:, lag:].ravel() for k in names], axis=1)
    if rank:
        Zx, Zy = (np.apply_along_axis(stats.rankdata, 0, z) for z in (Zx, Zy))
    Ax, Ay = _weighted(Zx, Wx), _weighted(Zy, Wy)
    tx = torch.as_tensor(Ax, dtype=torch.float32, device=_device())
    ty = torch.as_tensor(Ay, dtype=torch.float32, device=_device())
    R = ((tx.T @ ty) / torch.outer(torch.linalg.norm(tx, dim=0), torch.linalg.norm(ty, dim=0)).clamp(min=1e-30)
         ).double().cpu().numpy()
    # AR(1) per field (pooled over places) and cross-place correlation at equal t
    a1 = np.array([_lag1(surprises[k].z) for k in names])
    rho_space = np.array([_space(surprises[k].z) for k in names])
    per_place = Tl * (1 - np.outer(a1, a1)) / (1 + np.outer(a1, a1))
    deff = 1 + (U - 1) * np.clip((rho_space[:, None] + rho_space[None, :]) / 2, 0, 1)
    n_eff = np.clip(U * per_place / deff, 3.0, U * Tl)
    return _test("E_w", names, R, n_eff, delta, ledger, family, testable, lag, symmetric=(lag == 0))


def _lag1(z: np.ndarray) -> float:
    a, b = z[:, :-1].ravel(), z[:, 1:].ravel()
    ok = np.isfinite(a) & np.isfinite(b)
    return float(np.clip(np.corrcoef(a[ok], b[ok])[0, 1], -0.99, 0.99)) if ok.sum() > 10 else 0.0


def _space(z: np.ndarray) -> float:
    """ρ̄_space from the variance of the year means: Var(z̄_t) = σ²(1 + (U−1)ρ̄)/U."""
    U = z.shape[0]
    zz = np.where(np.isfinite(z), z, 0)
    s2 = zz.var()
    vbar = zz.mean(0).var()
    return float(max((vbar * U / max(s2, 1e-12) - 1) / (U - 1), 0.0))


def _test(estimand: str, names: list[str], R: np.ndarray, n_eff: np.ndarray, delta: float, ledger: control.Ledger,
          family: str, testable, lag: int, symmetric: bool = True) -> list[Pair]:
    F = len(names)
    idx = [(i, j) for i in range(F) for j in (range(i + 1, F) if symmetric else range(F)) if i != j]
    if testable is not None:
        idx = [(i, j) for i, j in idx if testable(names[i], names[j])]
    if not idx:
        return []
    ii, jj = np.array(idx).T
    rho, ne = R[ii, jj], n_eff[ii, jj]
    p = minimum_effect_p(rho, ne, delta)
    ids = ledger.register_many([control.Hypothesis(family, "scan", {"estimand": estimand, "x": names[i],
                                                                    "y": names[j], "lag": lag, "delta": delta})
                                for i, j in idx])
    ledger.complete_many([(t, float(pp), float(r), {"n_eff": float(n)}) for t, pp, r, n in zip(ids, p, rho, ne,
                                                                                               strict=True)])
    return [Pair(estimand, names[i], names[j], float(r), float(n), float(pp), delta, lag)
            for (i, j), r, n, pp in zip(idx, rho, ne, p, strict=True)]
