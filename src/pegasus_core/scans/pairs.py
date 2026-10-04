"""Pairs: dependence between fields at their common support (ARCHITECTURE §7.5).

All pairs of one estimand come from one weighted Gram matrix. Weights factor
per field (a = √w ⊙ (x − x̄_w)), so ρ_XY = aᵀb / (‖a‖‖b‖): the pair's weight is
√(w_X w_Y), the geometric mean of the two fields' information.

Effective sample sizes respect each field's own dependence:
- between places (E_b): Dutilleul's n_eff = 1 + n² / tr(R_X R_Y), with R from
  each field's correlogram over distance classes, so tr(R_X R_Y) = n +
  Σ_k n_k r_X(k) r_Y(k) for every pair at once;
- within places (E_w): AR(1) per field, n_eff,u = T (1 − a_X a_Y)/(1 + a_X a_Y),
  summed over places and divided by the design effect 1 + (U−1) ρ̄_space.

Every pair is tested against its minimum relevant effect: H0 |ρ| ≤ δ.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from scipy import special, stats

from .. import control, gateway

DELTA = 0.1  # provisional δ until the harness calibrates it (ARCHITECTURE §8.4)


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


# ---------------------------------------------------------------------- spatial correlogram


class Correlogram:
    """Distance classes over places: great-circle km between population centres, on fixed,
    roughly logarithmic edges. Equal-count classes were tried first and failed: with 5,570
    municipalities the first class spans 0–242 km, far beyond municipal autocorrelation."""

    EDGES_KM = (15, 30, 50, 75, 100, 150, 200, 300, 400, 600, 800, 1000, 1500, 2000, 3000)

    def __init__(self, places: np.ndarray, edges_km: tuple[float, ...] = EDGES_KM):
        pts = np.radians(gateway.municipality_points(places))
        lon, lat = (torch.as_tensor(pts[:, i], device=_device()) for i in (0, 1))
        n = len(places)
        D = torch.empty((n, n), dtype=torch.float32, device=_device())
        for a in range(0, n, 1024):
            dlat = lat[a:a + 1024, None] - lat[None, :]
            dlon = lon[a:a + 1024, None] - lon[None, :]
            h = torch.sin(dlat / 2) ** 2 + torch.cos(lat[a:a + 1024, None]) * torch.cos(lat[None, :]) * torch.sin(dlon / 2) ** 2
            D[a:a + 1024] = (2 * 6371.0 * torch.asin(torch.sqrt(torch.clamp(h, 0, 1)))).float()
        self.edges = np.asarray(edges_km, dtype=float)
        cls = torch.bucketize(D, torch.as_tensor(self.edges, device=_device(), dtype=torch.float32)).to(torch.int8)
        cls.fill_diagonal_(-1)
        self.cls = cls
        self.n = n
        self.counts = np.array([int((cls == k).sum()) for k in range(len(self.edges) + 1)], dtype=float)

    def coefficients(self, A: np.ndarray) -> np.ndarray:
        """r[f, k]: Moran-type autocorrelation of each (weighted, centred) column in each class."""
        t = torch.as_tensor(A, dtype=torch.float32, device=_device())
        var = (t ** 2).mean(0)
        out = []
        for k in range(len(self.counts)):
            if self.counts[k] == 0:
                out.append(np.zeros(t.shape[1]))
                continue
            C = (self.cls == k).float()
            out.append(((t * (C @ t)).sum(0) / self.counts[k] / torch.clamp(var, min=1e-30)).cpu().numpy())
        return np.clip(np.stack(out, axis=1), -1, 1)

    def n_eff(self, r: np.ndarray) -> np.ndarray:
        """Dutilleul's n_eff for every pair: 1 + n² / (n + Σ_k n_k r_X(k) r_Y(k))."""
        tr = self.n + (r * self.counts) @ r.T
        return np.clip(1 + self.n ** 2 / np.maximum(tr, self.n), 3.0, float(self.n))


# ---------------------------------------------------------------------- estimands


def between(effects: dict[str, tuple[np.ndarray, np.ndarray]], correlogram: Correlogram, ledger: control.Ledger,
            family: str, delta: float = DELTA, Z: np.ndarray | None = None, rank: bool = False,
            testable=None) -> list[Pair]:
    """E_b (or E_b|Z with an adjustment design Z [n, q]): place effects b̂(u) with their sd.
    ``testable(x, y)`` excludes pairs with overlap above 0.05 (or unknown)."""
    names = list(effects)
    B = np.stack([effects[k][0] for k in names], axis=1)
    W = np.stack([1.0 / np.maximum(effects[k][1], 1e-6) ** 2 for k in names], axis=1)
    if rank:
        B = np.apply_along_axis(stats.rankdata, 0, B)
    A = _weighted(B, W)
    q = 0
    if Z is not None:
        Zc = np.column_stack([np.ones(len(Z)), Z])
        q = Z.shape[1]
        for f in range(A.shape[1]):
            sw = np.sqrt(W[:, f])
            coef, *_ = np.linalg.lstsq(Zc * sw[:, None], A[:, f], rcond=None)
            A[:, f] = A[:, f] - (Zc * sw[:, None]) @ coef
    R = _gram(A)
    n_eff = correlogram.n_eff(correlogram.coefficients(A)) - q
    estimand = "E_b|Z" if Z is not None else "E_b"
    return _test(estimand, names, R, n_eff, delta, ledger, family, testable, 0)


def within(surprises: dict, ledger: control.Ledger, family: str, lag: int = 0, delta: float = DELTA,
           rank: bool = False, testable=None) -> list[Pair]:
    """E_w at lag ℓ (Y follows X by ℓ periods) on calibrated surprises z with their weights w."""
    names = list(surprises)
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
